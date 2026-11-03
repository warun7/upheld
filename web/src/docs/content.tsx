import type { ReactNode } from "react";
import { SYSTEMS } from "../data/benchmarks";
import type { LinkStatus, Verdict } from "../lib/api";
import { GITHUB_URL, HAS_PLAYGROUND, PLAYGROUND_URL } from "../lib/site";
import { LINK_STATUS, VERDICT_ORDER, VerdictLabel } from "../lib/verdicts";
import { A, C, Code, H3, Note, Table } from "./prose";

export interface DocPage {
  id: string;
  title: string;
  body: ReactNode;
}

/** AttributionBench in-distribution macro-F1 for one upheld verifier, from the landing page's benchmark data. */
const idScore = (name: string) => SYSTEMS.find((s) => s.name === name)?.scores.id?.toFixed(1) ?? "–";

const LINK_STATUS_NOTE: Record<LinkStatus, string> = {
  provided: "You supplied the source's text, so nothing was fetched.",
  live: "Fetched and read.",
  link_rot: "Dead now (404, 410 or no such domain), but the Wayback Machine has a copy. Claims citing it are unverifiable.",
  likely_fabricated: "Dead and never archived, so it probably never existed. Claims citing it are source_missing.",
  unreachable: "Blocked, timed out, under 300 characters of text (a cookie wall, bot check, JavaScript shell or scanned PDF), a PDF over 5 MB, or a file type upheld can't read.",
  missing: "The answer cites an id that has no matching source.",
};

const overview: DocPage = {
  id: "overview",
  title: "Overview",
  body: (
    <>
      <p>
        upheld checks whether an AI answer's citations actually support its claims. You give it an answer with <C>[1]</C>-style markers or inline links, plus the
        sources it cites. It splits the answer into claims, reads every cited page, finds the passages that bear on each claim, and has a verifier model decide
        whether those passages back it.
      </p>
      <p>
        Each claim comes back with a verdict, a support score between 0 and 1, the evidence it was judged against and, when it fails, the words the source doesn't
        back. Every report names its verifier and threshold, because the numbers depend on them.
      </p>
      <p>There are three ways to run it, all on the same engine:</p>
      <Table
        mono={false}
        head={["Surface", "Use it for"]}
        rows={[
          ["Command line", <>Spot-checking an answer you copied from ChatGPT, Perplexity, Gemini or your own tool.</>],
          ["Python library", <>Checking a RAG pipeline's outputs in an eval suite or a test.</>],
          ["HTTP API", <>Gating answers before they reach a user, from any language. You run the server.</>],
        ]}
      />
      <Note>
        There's no hosted version yet{HAS_PLAYGROUND ? " apart from the playground" : ""}: you run upheld on your own machine. It needs no API key and sends nothing
        anywhere except requests for the cited pages (and the Wayback Machine, for dead links).
      </Note>
    </>
  ),
};

const install: DocPage = {
  id: "install",
  title: "Install",
  body: (
    <>
      <p>
        You need Python 3.12 or newer, <A href="https://docs.astral.sh/uv/">uv</A> and git. A CPU is enough; Apple silicon and NVIDIA GPUs are used automatically when
        present and are several times faster.
      </p>
      <Code>{`git clone ${GITHUB_URL} && cd upheld
uv sync --extra models`}</Code>
      <p>
        The first audit downloads about 4 GB of models from Hugging Face into its usual cache. Pick the install that matches the verifier you want (see{" "}
        <A href="#verifiers">Pick a verifier</A>):
      </p>
      <Table
        head={["Command", "What it installs", "Download on first use"]}
        rows={[
          ["uv sync", <>The core only: the <C>lexical</C> verifier and BM25 retrieval. Good for trying the pipeline.</>, "none"],
          ["uv sync --extra models", <>The default <C>ensemble</C> verifier and hybrid retrieval.</>, "about 4 GB"],
          ["uv sync --all-extras", <>Adds the Granite Guardian judge for <C>ensemble+judge</C> and <C>judge</C>. Builds llama.cpp from source.</>, "8.7 GB more"],
        ]}
      />
      <p>
        To use upheld as a library from another project, add it straight from GitHub: <C>uv add "upheld[models] @ git+{GITHUB_URL}"</C>.
      </p>
    </>
  ),
};

const quickstart: DocPage = {
  id: "quickstart",
  title: "Quickstart",
  body: (
    <>
      <p>The repo ships two example answers. From the clone:</p>
      <Code>{`# source text included in the file, so nothing is fetched
uv run upheld audit examples/glp1.json

# a markdown answer with a reference list; fetches the cited Wikipedia pages
uv run upheld audit examples/eiffel.md

# the full report as JSON
uv run upheld audit examples/eiffel.md --json`}</Code>
      <p>
        The first line of the output names the verifier and retrieval, then counts how many cited claims are supported. Below that, a table lists each claim with its
        verdict, and for each citation its own verdict, support score, any names missing from the source and the flagged words. A second table lists each source
        and whether it could be read.
      </p>
      <p>
        <C>examples/eiffel.md</C> plants two errors. The claim that Frank Lloyd Wright led the design comes back <C>unsupported</C>, with his name listed as missing
        from the source. The citation to a repainting-schedule page comes back <C>source_missing</C>: the URL is a 404 that was never archived. It also flags one
        true claim, that the tower was meant to stand for only 20 years, because the page never says 20 years; that's one of the{" "}
        <A href="/#limits">known failure modes</A>.
      </p>
    </>
  ),
};

const auditAnswer: DocPage = {
  id: "audit-an-answer",
  title: "Audit an answer from an AI search tool",
  body: (
    <>
      <p>
        Copy the answer with its citations into a text or markdown file. Most tools' copy button keeps them, either as markdown links or as numbered markers with a
        list of sources at the end. upheld understands:
      </p>
      <ul className="list-disc space-y-1.5 pl-5">
        <li>
          numeric markers: <C>[1]</C>, <C>[1, 2]</C>, <C>[1][2]</C>, <C>[^1]</C>, <C>【1】</C>
        </li>
        <li>
          inline markdown links: <C>[text](https://...)</C>
        </li>
        <li>
          a reference list at the end: <C>[1] Title - https://...</C> or <C>1. https://...</C>, optionally under a heading such as Sources or References
        </li>
      </ul>
      <Code label="answer.md">{`The Eiffel Tower is 330 metres tall [1]. It was built for the 1889 World's Fair [1][2].

Sources:
[1] Eiffel Tower - https://en.wikipedia.org/wiki/Eiffel_Tower
[2] Exposition Universelle (1889) - https://en.wikipedia.org/wiki/Exposition_Universelle_(1889)`}</Code>
      <Code>{`uv run upheld audit answer.md --question "How tall is the Eiffel Tower?"

# or straight from the clipboard on macOS
pbpaste | uv run upheld audit -`}</Code>
      <p>
        <C>--question</C> is optional. LettuceDetect, one of the default verifier's three signals, reads it as context.
      </p>
      <H3>When a page can't be read</H3>
      <p>
        Paywalls, bot checks, scanned PDFs and pages that only render in a browser come back <C>unverifiable</C> rather than guessed at. If you can open the page yourself,
        paste its text into a JSON request instead (see <A href="#input">Input format</A>): a source with <C>text</C> is used as given and never fetched.
      </p>
    </>
  ),
};

const python: DocPage = {
  id: "python",
  title: "Check a RAG pipeline from Python",
  body: (
    <>
      <p>
        If your pipeline already has the retrieved documents, pass their text in and turn fetching off, so the audit is fast, repeatable and offline. The answer's
        markers must match the source ids.
      </p>
      <Code label="python">{`import asyncio
from upheld import AuditRequest, Source, Verdict, make_verifier, run_audit
from upheld.evidence import make_embedder

# Load once and reuse: these hold the models.
verifier = make_verifier("ensemble")
embedder = make_embedder("auto")  # hybrid retrieval if installed, else BM25


async def unsupported_claims(answer: str, docs: list[str]) -> list[str]:
    req = AuditRequest(
        answer=answer,
        sources=[Source(id=str(i + 1), text=d) for i, d in enumerate(docs)],
    )
    report = await run_audit(req, verifier, embedder=embedder, fetch=False)
    return [c.text for c in report.claims if c.cited and c.verdict != Verdict.SUPPORTED]


bad = asyncio.run(unsupported_claims(
    "Semaglutide led to an average weight loss of 14.9% [1].",
    ["In the STEP 1 trial, the mean change in body weight was -14.9% ..."],
))
print(bad)`}</Code>
      <p>
        <C>run_audit</C> returns an <C>AuditReport</C> (a pydantic model, see <A href="#report">Report format</A>). Without an <C>embedder</C> it ranks passages
        with BM25 alone, which misses paraphrases more often.
      </p>
      <H3>Using it as a test</H3>
      <p>
        A simple gate is to fail when any cited claim isn't <C>supported</C>, or when the share of supported claims drops below what you measured on a known-good set.
        Uncited claims show up with the verdict <C>uncited</C>; whether those should fail is up to you. Expect some false alarms on good answers and decide on a
        threshold with <A href="#eval">your own labels</A> before you block on it.
      </p>
    </>
  ),
};

const http: DocPage = {
  id: "http-api",
  title: "Gate answers over HTTP",
  body: (
    <>
      <p>
        <C>upheld serve</C> runs a small API that loads the models once and keeps them warm. Call it from any language.
      </p>
      <Code>{`uv run upheld serve --port 8000

curl -s localhost:8000/health

curl -s localhost:8000/audit -H 'content-type: application/json' -d '{
  "answer": "The Eiffel Tower is 330 metres tall [1].",
  "sources": [{"id": "1", "url": "https://en.wikipedia.org/wiki/Eiffel_Tower"}]
}'`}</Code>
      <Table
        head={["Endpoint", "Does"]}
        rows={[
          ["GET /health", <>Returns <C>status</C>, <C>verifier</C> and <C>retrieval</C> once the models are loaded.</>],
          ["POST /audit", <>Takes an <A href="#input">AuditRequest</A> and returns an <A href="#report">AuditReport</A>. Invalid input gets a 422 with the reason.</>],
          ["GET /openapi.json", <>The schema, for generating a client. <C>/redoc</C> renders it.</>],
        ]}
      />
      <p>
        One request audits one answer, and takes about as long as the CLI would: roughly a second per claim per source on a laptop GPU, several times that on CPU.
        Requests run side by side unless <C>UPHELD_MAX_CONCURRENT</C> caps them.
      </p>
      <Note>
        The API fetches whatever URLs a request cites. It refuses private, loopback and cloud-metadata addresses, but it has no authentication or rate limit. Keep it
        on a private network, or put it behind something that adds both, before exposing it.
      </Note>
    </>
  ),
};

const verifiers: DocPage = {
  id: "verifiers",
  title: "Pick a verifier",
  body: (
    <>
      <p>
        The verifier decides whether the passages retrieved for a claim back it. Choose one with <C>--verifier</C> on <C>audit</C>, <C>eval</C> and <C>serve</C>,
        or by name with <C>make_verifier()</C>. Scores are macro-F1 on AttributionBench's in-distribution test sets, for the verifier alone (the entity check
        costs about two points there and catches swapped names elsewhere).
      </p>
      <Table
        head={["Verifier", "What it runs", "Score", "Use it when"]}
        rows={[
          [
            "ensemble",
            <>MiniCheck-Flan-T5-Large (770M), word overlap with exact number matching, and LettuceDetect-base (150M), combined by a fitted logistic regression.</>,
            idScore("upheld ensemble"),
            <>The default. Catches every wrong number in the edited-claim tests.</>,
          ],
          [
            "ensemble+judge",
            <>The ensemble plus Granite Guardian 3.3 8B, run locally with llama.cpp. Needs about 9 GB of free memory.</>,
            idScore("upheld ensemble + judge"),
            <>Accuracy matters more than speed. Fewer false alarms, and much better at claims credited to the wrong party.</>,
          ],
          ["judge", <>Granite Guardian alone.</>, idScore("upheld judge"), <>Comparing against the ensemble.</>],
          ["minicheck", <>MiniCheck alone.</>, idScore("upheld minicheck"), <>One model, simplest to reason about.</>],
          ["lettuce", <>LettuceDetect alone. Flags the unsupported words.</>, idScore("upheld lettuce"), <>Studying span-level flags.</>],
          ["lexical", <>Word overlap and exact numbers. No model.</>, idScore("upheld lexical"), <>Trying the pipeline, or CI without a GPU.</>],
        ]}
      />
      <p>
        The ensemble takes roughly 0.3 to 1 second per claim per source on an Apple M5 Pro and is several times slower on CPU; the judge ensemble reads 10 passages per claim and takes about 2.5 to 3 seconds. For
        the full comparison, including GPT-4 and fine-tuned models, see the <A href="/#benchmarks">benchmarks</A>.
      </p>
      <H3>Thresholds</H3>
      <p>
        Each verifier turns a support score into a verdict at a threshold that's part of its name in the report, such as <C>@0.5</C>. Lower it with{" "}
        <C>--threshold</C> to flag less, raise it to flag more. The defaults were picked on AttributionBench's dev split; on your own content, measure first.
      </p>
      <H3>Retrieval</H3>
      <p>
        <C>--retrieval auto</C> (the default) uses hybrid search, BM25 plus <C>bge-small-en-v1.5</C> embeddings, when the models extra is installed, and BM25
        otherwise. <C>hybrid</C> and <C>bm25</C> force one or the other.
      </p>
    </>
  ),
};

const evaluate: DocPage = {
  id: "eval",
  title: "Measure it on your own labels",
  body: (
    <>
      <p>
        Accuracy on a benchmark says little about your content. Label a few dozen claims from your own answers and score the verifier against them. One JSON object
        per line:
      </p>
      <Code label="labels.jsonl">{`{"claim": "It opened in 1889.", "evidence": "The tower opened on 31 March 1889 ...", "label": "supported"}
{"claim": "It is 410 metres tall.", "evidence": ["passage one ...", "passage two ..."], "label": "unsupported", "answer": "The tower is in Paris. It is 410 metres tall."}`}</Code>
      <p>
        <C>evidence</C> is a passage or a list of them. <C>label</C> is <C>supported</C> or <C>unsupported</C>. <C>answer</C>, if given, must contain the claim
        word for word; LettuceDetect reads the whole answer, so it does better with it. <C>question</C> is optional.
      </p>
      <Code>{`uv run upheld eval labels.jsonl --verifier ensemble`}</Code>
      <p>
        The output is a threshold sweep: precision, recall and F1 for flagging unsupported claims, macro-F1, accuracy and the share flagged at each threshold, with the
        verifier's default in bold. Pick the row that suits you and pass it as <C>--threshold</C>.
      </p>
    </>
  ),
};

const selfHost: DocPage = {
  id: "self-host",
  title: "Self-host the API",
  body: (
    <>
      <p>
        The <C>Dockerfile</C> in the repo builds one image with the API{HAS_PLAYGROUND ? ", this website and the playground" : " and this website"}. It bakes the
        default models in, so a cold start doesn't download them. The judge isn't included.
      </p>
      <Code>{`docker build -t upheld .
docker run -p 7860:7860 upheld   # http://localhost:7860`}</Code>
      <p>
        It's built for a Hugging Face Docker Space on the free CPU tier (16 GB of memory) but runs anywhere. Expect a few seconds per claim on CPU. Settings come from
        environment variables:
      </p>
      <Table
        head={["Variable", "Default", "Does"]}
        rows={[
          ["UPHELD_VERIFIER", <C>ensemble</C>, <>Which verifier the API loads. <C>upheld serve --verifier</C> sets it.</>],
          ["UPHELD_RETRIEVAL", <C>auto</C>, <><C>auto</C>, <C>hybrid</C> or <C>bm25</C>. <C>upheld serve --retrieval</C> sets it.</>],
          ["UPHELD_MAX_CONCURRENT", <>unlimited</>, <>Audits allowed at once; the rest queue. The image sets 1.</>],
          ["UPHELD_CORS_ORIGINS", <>none</>, <>Comma-separated origins allowed to call the API from a browser, for a website hosted elsewhere.</>],
          ["UPHELD_USER_AGENT", <>names this repo</>, <>The user agent for fetching pages. Set it to your own project's URL when you deploy.</>],
          ["UPHELD_SITE_DIR", <C>web/dist</C>, <>The built website to serve at <C>/</C>, if it exists.</>],
        ]}
      />
    </>
  ),
};

const input: DocPage = {
  id: "input",
  title: "Input format",
  body: (
    <>
      <p>
        The CLI reads a <C>.json</C> file as an <C>AuditRequest</C>, and anything else as the answer text. <C>POST /audit</C> and <C>run_audit()</C> take the same
        request.
      </p>
      <Code label="json">{`{
  "question": "How much weight do people lose on Ozempic?",
  "answer": "In a 68-week trial, semaglutide led to an average weight loss of 14.9% [1].",
  "sources": [
    {"id": "1", "title": "STEP 1 trial", "text": "In the STEP 1 trial, 1,961 adults ..."},
    {"id": "2", "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2032183"}
  ]
}`}</Code>
      <Table
        head={["Field", "Type", "Notes"]}
        rows={[
          ["question", "string, optional", "Up to 2,000 characters."],
          ["answer", "string", <>Up to 50,000 characters. Markers, inline links and a trailing reference list are parsed as in <A href="#audit-an-answer">the guide</A>.</>],
          ["sources", "list, optional", "Up to 50. Sources in the answer's own reference list or links are added; one listed here wins over one with the same id."],
          ["sources[].id", "string", <>What the answer cites: <C>"1"</C> for <C>[1]</C>.</>],
          ["sources[].text", "string, optional", "The source's text. When present, it's used as given and the URL isn't fetched."],
          ["sources[].url", "string, optional", "Fetched when there's no text. Capped at 5 MB; dead links are looked up in the Wayback Machine."],
          ["sources[].title", "string, optional", "For your own reference."],
        ]}
      />
    </>
  ),
};

const report: DocPage = {
  id: "report",
  title: "Report format",
  body: (
    <>
      <p>
        <C>--json</C>, <C>POST /audit</C> and <C>run_audit()</C> all return the same report. This one is from the Eiffel Tower answer on the{" "}
        <A href="/#demo">home page</A>, trimmed to one claim:
      </p>
      <Code label="json">{`{
  "verifier": "ensemble:minicheck+lexical+lettuce@0.5",
  "retrieval": "hybrid:bm25+bge-small-en-v1.5",
  "summary": {
    "claims": 6, "cited_claims": 5, "supported_claims": 2, "citations_checked": 5,
    "citation_verdicts": {"supported": 2, "unsupported": 2, "source_missing": 1},
    "claim_verdicts": {"supported": 2, "unsupported": 2, "source_missing": 1, "uncited": 1}
  },
  "claims": [
    {
      "index": 3, "text": "Its design was led by the architect Frank Lloyd Wright.",
      "start": 250, "end": 309, "cited": ["1"], "verdict": "unsupported",
      "checks": [{
        "source_id": "1", "verdict": "unsupported", "support_score": 0.268,
        "unsupported_spans": [{"start": 0, "end": 54, "text": "Its design was led by the architect Frank Lloyd Wright", "confidence": 1.0}],
        "missing_entities": ["Frank Lloyd Wright"],
        "evidence": [{"source_id": "1", "passage": "...", "score": 1.0}],
        "note": null
      }],
      "note": null
    }
  ],
  "sources": [
    {"id": "1", "url": "https://en.wikipedia.org/wiki/Eiffel_Tower", "status": "live", "http_status": 200, "chars": 65753, "note": null},
    {"id": "2", "url": "https://en.wikipedia.org/wiki/Eiffel_Tower_repainting_schedule", "status": "likely_fabricated", "http_status": 404, "chars": 0, "note": "HTTP 404; never archived"}
  ]
}`}</Code>
      <Table
        head={["Field", "Meaning"]}
        rows={[
          ["verifier, retrieval", "What produced this report, threshold included. Scores aren't comparable across verifiers."],
          ["claims[].start, end", "Character offsets of the claim's sentence in the original answer, for highlighting."],
          ["claims[].verdict", <>The best verdict among the claim's citations. A claim whose citations each fail is re-checked against them together, for facts that span two sources.</>],
          ["checks[]", "One per citation: that source's verdict, the support score (0 to 1), and the passages it was judged against."],
          ["unsupported_spans", "Character offsets within the claim text of the words the source doesn't back."],
          ["missing_entities", <>Names in the claim that appear nowhere in the source. When the score would otherwise pass, they make the verdict <C>wrong_entity</C>.</>],
          ["sources[].status", <>Whether each cited source could be read. See <A href="#verdicts">link statuses</A>.</>],
        ]}
      />
    </>
  ),
};

const VERDICT_NOTE: Record<Verdict, ReactNode> = {
  supported: "The cited source backs the claim.",
  unsupported: "The source is real and readable but doesn't back the claim. Flagged spans show which part.",
  wrong_entity: (
    <>
      The evidence reads as supporting, but a name in the claim appears nowhere in the source: drug Y's trial cited for drug X. It's a heuristic with a known
      false-alarm rate (abbreviations, partial names), so treat it as a prompt to look.
    </>
  ),
  source_missing: "The cited source isn't listed, or its URL is dead and was never archived: likely made up.",
  unverifiable: "The source exists but couldn't be read: blocked, no readable text (a scanned PDF, say), or a dead link with only an archived copy.",
  uncited: "A factual-looking sentence with no citation. Questions and lead-ins aren't counted.",
};

const verdicts: DocPage = {
  id: "verdicts",
  title: "Verdicts and link statuses",
  body: (
    <>
      <p>Each citation gets one verdict, and each claim gets the best verdict among its citations.</p>
      <Table
        mono={false}
        head={["Verdict", "Code", "Meaning"]}
        rows={VERDICT_ORDER.map((v) => [<VerdictLabel verdict={v} />, <C>{v}</C>, VERDICT_NOTE[v]])}
      />
      <p>Each source in the report gets a link status:</p>
      <Table
        head={["Status", "Meaning"]}
        rows={(Object.keys(LINK_STATUS) as LinkStatus[]).map((s) => [s, <>{LINK_STATUS_NOTE[s]}</>])}
      />
    </>
  ),
};

const cli: DocPage = {
  id: "cli",
  title: "CLI reference",
  body: (
    <>
      <p>
        Run with <C>uv run upheld</C> from the clone, or <C>upheld</C> wherever it's installed. <C>--help</C> on any command lists the same options.
      </p>
      <H3>upheld audit PATH</H3>
      <p>
        Audit one answer. <C>PATH</C> is a <C>.json</C> request, a markdown or text answer, or <C>-</C> for stdin.
      </p>
      <Table
        head={["Option", "Default", "Does"]}
        rows={[
          ["--question TEXT", <>none</>, "The question the answer responds to, for text input."],
          ["--verifier NAME", <C>ensemble</C>, <>See <A href="#verifiers">Pick a verifier</A>.</>],
          ["--threshold FLOAT", <>the verifier's</>, "Support score below this counts as unsupported."],
          ["--retrieval NAME", <C>auto</C>, <><C>auto</C>, <C>hybrid</C> or <C>bm25</C>.</>],
          ["--no-fetch", <>fetching on</>, "Use only source text given inline; never request a URL."],
          ["--allow-private", <>off</>, "Allow fetching localhost and private-network URLs, for testing your own pages."],
          ["--json", <>off</>, "Print the full report as JSON instead of tables."],
        ]}
      />
      <H3>upheld eval PATH</H3>
      <p>
        Score a verifier against labeled JSONL, with a threshold sweep. Takes <C>--verifier</C> and <C>--threshold</C>. See{" "}
        <A href="#eval">Measure it on your own labels</A>.
      </p>
      <H3>upheld serve</H3>
      <p>
        Run the HTTP API, plus the website{HAS_PLAYGROUND ? " and playground" : ""} when <C>web/dist</C> is built. Takes <C>--host</C> (default{" "}
        <C>127.0.0.1</C>), <C>--port</C> (default <C>8000</C>), <C>--verifier</C> and <C>--retrieval</C>.
      </p>
    </>
  ),
};

const howItWorks: DocPage = {
  id: "how-it-works",
  title: "How it works",
  body: (
    <>
      <ol className="list-decimal space-y-3 pl-5">
        <li>
          <span className="text-ink">Parse.</span> Split the answer into sentences and map each marker or link to its source. Questions and lead-ins aren't claims.
        </li>
        <li>
          <span className="text-ink">Fetch.</span> Download each cited page and extract its main text, or a PDF's text. A 404, 410 or unknown domain is checked against the Wayback
          Machine: archived means link rot, never archived means likely fabricated. 403, 429 and 5xx only mean it couldn't be read, and so does a page with under
          300 characters of text: a cookie wall, bot check or JavaScript shell, not the article.
        </li>
        <li>
          <span className="text-ink">Retrieve.</span> Cut each source into windows of about 120 words and keep the 3 that best match the claim (10 for the judge ensemble), ranked by BM25 and
          embeddings merged with reciprocal rank fusion.
        </li>
        <li>
          <span className="text-ink">Verify.</span> Score whether those passages support the claim, and mark the words they don't.
        </li>
        <li>
          <span className="text-ink">Entity check.</span> Flag names in the claim that appear nowhere in the source.
        </li>
        <li>
          <span className="text-ink">Combine.</span> Re-check a claim against all its sources together when each one fails alone.
        </li>
      </ol>
      <p>
        Fetching is guarded against server-side request forgery: private, loopback and metadata addresses are refused, and every redirect is checked again. The{" "}
        <A href={`${GITHUB_URL}#how-it-works`}>README</A> has the details, and the <A href="/#limits">known failure modes</A> are on the home page.
      </p>
    </>
  ),
};

const troubleshooting: DocPage = {
  id: "troubleshooting",
  title: "Troubleshooting",
  body: (
    <>
      <Table
        mono={false}
        head={["Problem", "What to do"]}
        rows={[
          ["The first run sits there for minutes.", "It's downloading about 4 GB of models from Hugging Face. Later runs load them from the cache."],
          ["A source is unverifiable but opens fine in your browser.", <>The site blocked the fetch, or builds its text with JavaScript. Paste the page's text into the source's <C>text</C> field.</>],
          ["Wikipedia or another site returns 403.", <>Some sites reject generic user agents. Set <C>UPHELD_USER_AGENT</C> to a string with your project's URL.</>],
          ["A localhost URL is refused.", <>Private addresses are blocked by default. Pass <C>--allow-private</C> on the CLI.</>],
          ["It's too slow on CPU.", <>Try <C>--verifier minicheck</C>, or <C>--verifier lexical --retrieval bm25</C> to skip the models entirely.</>],
          ["A true claim is flagged.", <>Usually a one-step inference ("-14.9% change" vs "14.9% loss") or retrieval picking the wrong part of a long page. <C>--verifier ensemble+judge</C> handles both better: it reads 10 passages per claim and flags about half as many good citations.</>],
          ["Every claim is source_missing.", <>The reference list didn't survive the copy. Check that the markers' numbers match a list at the end, or pass the sources in JSON.</>],
        ]}
      />
      <p>
        Something else? <A href={`${GITHUB_URL}/issues`}>Open an issue</A>.
        {HAS_PLAYGROUND && (
          <>
            {" "}
            Or try the answer in the <A href={PLAYGROUND_URL}>playground</A> first.
          </>
        )}
      </p>
    </>
  ),
};

export const DOCS: { group: string; pages: DocPage[] }[] = [
  { group: "Getting started", pages: [overview, install, quickstart] },
  { group: "Guides", pages: [auditAnswer, python, http, verifiers, evaluate, selfHost] },
  { group: "Reference", pages: [input, report, verdicts, cli, howItWorks, troubleshooting] },
];
