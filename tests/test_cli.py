import json
import re

from typer.testing import CliRunner

from upheld.cli import app
from upheld.htmlreport import SLOT

REQUEST = {
    "question": "Tell me about the Eiffel Tower </script><script>alert(1)</script>",
    "answer": "The Eiffel Tower in Paris is 330 metres tall [1]. The Eiffel Tower was completed in 1925 [1]. It is the most visited paid monument in the world.",
    "sources": [{"id": "1", "text": "The Eiffel Tower in Paris is 330 metres tall and was completed in 1889."}],
}
OFFLINE = ["--verifier", "lexical", "--retrieval", "bm25", "--no-fetch"]


def runner() -> CliRunner:
    # stdout and stderr apart, so a test can check that --json output stays clean. Click 8.2+ always keeps them
    # apart and dropped mix_stderr; older Click mixes them unless told not to.
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:
        return CliRunner()


def run(tmp_path, *args):
    path = tmp_path / "answer.json"
    path.write_text(json.dumps(REQUEST))
    return runner().invoke(app, ["audit", str(path), *OFFLINE, *args])


def test_fail_on_exits_1_only_when_a_claim_has_a_listed_verdict(tmp_path):
    # Claims: supported, unsupported (wrong year), uncited.
    assert run(tmp_path).exit_code == 0
    assert run(tmp_path, "--fail-on", "source_missing,wrong_entity").exit_code == 0

    result = run(tmp_path, "--fail-on", "flagged")
    assert result.exit_code == 1
    assert "1 of 3 claims failed (1 unsupported)" in result.stderr

    result = run(tmp_path, "--fail-on", "unsupported, uncited", "--json")
    assert result.exit_code == 1
    assert "2 of 3 claims failed" in result.stderr
    assert json.loads(result.stdout)["summary"]["claims"] == 3  # stdout stays pure JSON


def test_errors_exit_2_so_ci_can_tell_them_from_findings(tmp_path):
    result = run(tmp_path, "--fail-on", "supported")
    assert result.exit_code == 2 and "isn't a verdict to fail on" in result.stderr
    result = run(tmp_path, "--fail-on", "unsuported")
    assert result.exit_code == 2

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert runner().invoke(app, ["audit", str(bad), *OFFLINE, "--fail-on", "flagged"]).exit_code == 2
    assert runner().invoke(app, ["audit", str(tmp_path / "missing.md"), *OFFLINE]).exit_code == 2
    assert run(tmp_path, "--verifier", "nope").exit_code == 2


def test_html_report_is_one_file_with_the_audit_inside(tmp_path):
    out = tmp_path / "report.html"
    result = run(tmp_path, "--html", str(out), "--fail-on", "flagged")
    assert result.exit_code == 1  # written before failing, so CI can upload it
    html = out.read_text()

    # Nothing outside the file: no script or stylesheet by URL, and a policy that blocks fetching.
    assert not re.search(r"<(script|link)\b[^>]*\b(src|href)=", html)
    assert "default-src 'none'" in html

    # The audit's text can't close the data block early.
    data = re.search(r'<script id="upheld-data" type="application/json">(.*?)</script>', html, re.DOTALL).group(1)
    assert "</script" not in data
    payload = json.loads(data)
    assert payload["question"] == REQUEST["question"]
    assert payload["answer"] == REQUEST["answer"]
    assert [c["verdict"] for c in payload["report"]["claims"]] == ["supported", "unsupported", "uncited"]


def test_the_packaged_template_has_its_data_slot():
    from importlib import resources

    assert resources.files("upheld").joinpath("report.html").read_text("utf-8").count(SLOT) == 1


def test_doctor_says_what_auto_picks_and_why():
    result = runner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    assert "auto picks" in result.stdout and "extras" in result.stdout
