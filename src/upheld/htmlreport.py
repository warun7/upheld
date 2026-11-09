"""The report as one self-contained HTML file: the site's report viewer with the audit's data inside.

report.html is built from web/report.html (`npm run build` in web/ writes it here). It loads nothing from the network,
so it opens from disk, as an email attachment or as a CI artifact. Its content security policy stops it from fetching
anything, so the page text quoted in the report can't call out either.
"""

import json
from datetime import UTC, datetime
from importlib import metadata, resources

from upheld.models import AuditReport, AuditRequest

SLOT = '<script id="upheld-data" type="application/json">{}</script>'


def _escape(data: str) -> str:
    # Inside <script>, only "</script" or "<!--" would end the block early. Escaping every "<" rules out both;
    # JSON.parse reads \u003c back as "<". U+2028 and U+2029 are valid JSON but not always valid in a script.
    return data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render_html(req: AuditRequest, report: AuditReport) -> str:
    template = resources.files("upheld").joinpath("report.html").read_text("utf-8")
    if template.count(SLOT) != 1:
        raise RuntimeError("upheld's report.html template has no data slot; rebuild it with `npm run build` in web/")
    payload = {
        "question": req.question,
        "answer": req.answer,
        "report": report.model_dump(mode="json"),
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": metadata.version("upheld"),
    }
    data = _escape(json.dumps(payload, ensure_ascii=False))
    return template.replace(SLOT, SLOT.replace("{}", data))
