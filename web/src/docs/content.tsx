import { Fragment, type ReactNode } from "react";
import { FRESH_VERIFIED_CITATIONS, FRESH_VERIFIERS, SYSTEMS } from "../data/benchmarks";
import { BROKEN, PATHS, SNIPPETS, type SnippetTab } from "../data/install";
import type { LinkStatus, Verdict } from "../lib/report";
import { GITHUB_URL } from "../lib/site";
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
  archived: "Up, but blocked, timed out, a server error or a block page, so upheld read the Wayback Machine's newest copy instead and judged claims against it. The report gives the copy's date.",
  link_rot: "Dead now (404, 410 or no such domain), but the Wayback Machine has a copy. upheld reads it and judges claims against it, as for archived; if the copy can't be read either, claims citing it are unverifiable.",
  likely_fabricated: "Dead and never archived, so it probably never existed. Claims citing it are source_missing.",
  unreachable: "Blocked, timed out or under 300 characters of text (a cookie wall, bot check or JavaScript shell), with no readable archived copy. Or a scanned PDF, a PDF over 5 MB, or a file type upheld can't read, which an archived copy wouldn't change.",
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
      <p>There are four ways to run it, all on the same engine:</p>
      <Table
        mono={false}
        head={["Surface", "Use it for"]}
        rows={[
          ["Python library", <>Checking answers in an eval suite, a test or a pipeline: an answer with its sources, or an OpenAI, Anthropic, Perplexity or Gemini response as the API returned it.</>],
          ["Command line", <>Spot-checking an answer you copied from ChatGPT, Perplexity, Gemini or your own tool, or a provider's response saved as JSON.</>],
          ["HTTP API", <>Gating answers before they reach a user, from any language. You run the server.</>],
          ["MCP server", <>Letting Claude Code, Cursor, Codex or another agent check the citations in its own answer before it shows you.</>],
        ]}
      />
      <Note>
        There's no hosted version: you run upheld on your own machine. It needs no API key and sends nothing
        anywhere except requests for the cited pages (and the Wayback Machine, for pages that are dead or can't be read).
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
        You need Python 3.12 or newer. A CPU is enough; Apple silicon and NVIDIA GPUs are used automatically when present and are several times faster.
      </p>
      <Code>{`pip install "upheld[models]"`}</Code>
      <p>
        The first audit downloads about 4 GB of models from Hugging Face into its usual cache. Pick the install that matches the verifier you want (see{" "}
        <A href="#verifiers">Pick a verifier</A>):
      </p>
      <Table
        head={["Command", "What it installs", "Download on first use"]}
        rows={[
          ["pip install upheld", <>The core only: the <C>lexical</C> verifier and BM25 retrieval. Good for trying the pipeline.</>, "none"],
          ['pip install "upheld[models]"', <>The default <C>ensemble</C> verifier and hybrid retrieval.</>, "about 4 GB"],
          ['pip install "upheld[models,judge]"', <>Adds the Granite Guardian judge for <C>ensemble+judge</C> and <C>judge</C>. Builds llama.cpp from source.</>, "8.7 GB more"],
          ['pip install "upheld[models,api]"', <>Adds FastAPI and uvicorn for <C>upheld serve</C>, the HTTP API and the website.</>, "none"],
          ['pip install "upheld[models,mcp]"', <>Adds the MCP SDK for <C>upheld mcp</C>, the server for AI agents (see <A href="#mcp">Check answers from an AI agent</A>).</>, "none"],
        ]}
      />
      <p>
        The minimum versions are as old as upheld works with (pydantic 2.0, httpx 0.21; torch 2.6 and transformers 4.48 for the models), so it installs into an
        existing project without forcing upgrades.
      </p>
      <p>
        With uv, <C>uv add "upheld[models]"</C>. To run the repo's examples, evals and tests, clone it instead: <C>git clone {GITHUB_URL} && cd upheld && uv sync --extra models</C>,
        or <C>--all-extras</C> for the judge.
      </p>
    </>
  ),
};

const quickstart: DocPage = {
  id: "quickstart",
  title: "Quickstart",
  body: (
    <>
      <p>Give <C>upheld.audit</C> an answer with <C>[1]</C>-style markers and the sources it cites, in order:</p>
      <Code label="python">{`import upheld

report = upheld.audit("The Eiffel Tower is 330 metres tall [1]. It was designed by Frank Lloyd Wright [1].", ["https://en.wikipedia.org/wiki/Eiffel_Tower"])
for claim in report.claims:
    print(claim.verdict, claim.text)`}</Code>
      <Code label="output">{`supported The Eiffel Tower is 330 metres tall.
unsupported It was designed by Frank Lloyd Wright.`}</Code>
      <p>
        A source is a URL to fetch, or the source's text itself. The report has a verdict, a support score and the evidence for every claim (see{" "}
        <A href="#report">Report format</A>). To audit what OpenAI, Anthropic, Perplexity or Gemini returned, pass the response itself: see{" "}
        <A href="#providers">Audit a provider's response</A>.
      </p>
      <p>From the command line, with an answer saved as markdown:</p>
      <Code>{`upheld audit answer.md

# the full report as JSON
upheld audit answer.md --json`}</Code>
      <p>
        The first line of the output names the verifier and retrieval, then counts how many cited claims are supported. Below that, a table lists each claim with its
        verdict, and for each citation its own verdict, support score, any names missing from the source and the flagged words. A second table lists each source
        and whether it could be read.
      </p>
      <p>
        The repo ships two examples. <C>examples/eiffel.md</C> plants two errors. The claim that Frank Lloyd Wright led the design comes back <C>unsupported</C>, with
        his name listed as missing from the source. The citation to a repainting-schedule page comes back <C>source_missing</C>: the URL is a 404 that was never
        archived. It also flags one true claim, that the tower was meant to stand for only 20 years, because the page never says 20 years; that's one of the{" "}
        <A href="/#limits">known failure modes</A>.
      </p>
    </>
  ),
};

const providers: DocPage = {
  id: "providers",
  title: "Audit a provider's response",
  body: (
    <>
      <p>
        Hand upheld the response your code already gets from OpenAI, Anthropic, Perplexity or Gemini with web search on. It reads the provider's own citation data, so
        there's nothing to reformat:
      </p>
      <Code label="python">{`import upheld
from openai import OpenAI

question = "How tall is the Eiffel Tower?"
response = OpenAI().responses.create(model="gpt-6-astra", tools=[{"type": "web_search"}], input=question)
report = upheld.audit(response, question=question)
print(f"{report.summary.supported_claims} of {report.summary.cited_claims} cited claims supported")`}</Code>
      <p>The other providers' responses go in the same way:</p>
      <Code label="python">{`import anthropic
from google import genai
from perplexity import Perplexity

# Anthropic: Messages with the web search tool
message = anthropic.Anthropic().messages.create(
    model="claude-sonnet-5-5",
    max_tokens=2048,
    messages=[{"role": "user", "content": question}],
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
)
report = upheld.audit(message, question=question)

# Gemini: Google Search grounding, from the Interactions API or generate_content
interaction = genai.Client().interactions.create(model="gemini-3.8-flash", input=question, tools=[{"type": "google_search"}])
report = upheld.audit(interaction, question=question)

# Perplexity: the Agent API, or Sonar
response = Perplexity().responses.create(effort="low", input=question)
report = upheld.audit(response, question=question)`}</Code>
      <p>
        A response can be the SDK's object, its JSON as a dict, or a JSON string. upheld tells the provider from its shape; <C>provider="gemini"</C> names it.{" "}
        <C>upheld.from_openai(response)</C>, and likewise <C>from_anthropic</C>, <C>from_perplexity</C> and <C>from_gemini</C>, return the <C>AuditRequest</C> upheld
        builds, so you can see the claims and sources before auditing.
      </p>
      <Table
        mono={false}
        head={["Response", "What upheld reads", "What it checks as a claim"]}
        rows={[
          [
            "OpenAI Responses API, or Chat Completions with web search",
            <><C>url_citation</C> annotations: the URL, its title, and the range of the link the model wrote.</>,
            <>Sentences. OpenAI's range covers the link after a claim, not the claim, so the link becomes a <C>[n]</C> marker. <C>utm_source=openai</C> is dropped from the URLs so the Wayback Machine can find them.</>,
          ],
          [
            "Anthropic Messages with web search",
            <>Text blocks whose <C>citations</C> hold <C>web_search_result_location</C> entries.</>,
            <>Each cited block. Claude's narration of its searches, before the first cited block, is left out.</>,
          ],
          [
            "Perplexity Agent API or Sonar",
            <><C>[1]</C> or <C>[web:1]</C> markers, numbered into <C>search_results</C> (or Sonar's older <C>citations</C>).</>,
            <>Sentences, split at the markers.</>,
          ],
          [
            "Gemini generate_content with Google Search",
            <><C>groundingSupports</C>: byte ranges of the text, each with indices into <C>groundingChunks</C>.</>,
            <>Each range. The chunks' URLs are Google redirects, which upheld follows; the source's <C>resolved_url</C> is the page each led to.</>,
          ],
          ["Gemini Interactions API", <><C>url_citation</C> annotations over the cited text.</>, <>Each annotated range.</>],
        ]}
      />
      <p>
        A cited range too short to be a claim on its own, such as a name, is widened to the sentence it's in. Sentences outside every cited range are still reported,
        as <C>uncited</C> when they read as claims. Claim offsets refer to the answer text upheld assembled, <C>upheld.from_…(response).answer</C>.
      </p>
      <Note>
        Gemini's redirect links stop working after a while, so audit a Gemini response soon after you get it. An expired link is reported <C>unverifiable</C>, since
        the page it pointed to is unknown.
      </Note>
      <H3>From the command line and over HTTP</H3>
      <Code>{`# a response saved as JSON; --from auto (the default) tells the providers apart
upheld audit response.json --from openai

# with upheld serve running
curl -s localhost:8000/audit/auto -H 'content-type: application/json' -d @response.json`}</Code>
      <p>
        <C>--from</C> takes <C>openai</C>, <C>anthropic</C>, <C>perplexity</C>, <C>gemini</C> or <C>auto</C>, and so does the path of <C>POST /audit/{"{provider}"}</C>.
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
      <Code>{`upheld audit answer.md --question "How tall is the Eiffel Tower?"

# or straight from the clipboard on macOS
pbpaste | upheld audit -`}</Code>
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
        If your pipeline already has the retrieved documents, pass their text as the sources, so the audit is fast, repeatable and offline: a source given as text is
        never fetched. The answer's <C>[1]</C>, <C>[2]</C> markers cite the documents in order.
      </p>
      <Code label="python">{`import upheld
from upheld import Verdict

# Loads the models once; keep it and reuse it.
auditor = upheld.Auditor()  # verifier="ensemble", retrieval="auto"


def unsupported_claims(answer: str, docs: list[str]) -> list[str]:
    report = auditor.audit(answer, docs)
    return [c.text for c in report.claims if c.cited and c.verdict != Verdict.SUPPORTED]


bad = unsupported_claims(
    "Semaglutide led to an average weight loss of 14.9% [1].",
    ["In the STEP 1 trial, the mean change in body weight was -14.9% ..."],
)
print(bad)`}</Code>
      <p>
        <C>auditor.audit</C> returns an <C>AuditReport</C> (a pydantic model, see <A href="#report">Report format</A>). In async code, such as a web server, use{" "}
        <C>await auditor.audit_async(...)</C>. <C>upheld.audit()</C> does the same in one call and keeps the models from its last call loaded. A source can also be a{" "}
        <C>Source</C> or a dict, and a string starting with <C>http://</C> or <C>https://</C> is a URL to fetch.
      </p>
      <p>
        <C>run_audit(request, verifier, embedder=...)</C>, the async function underneath, takes an <A href="#input">AuditRequest</A> and a verifier from{" "}
        <C>make_verifier()</C>, for full control.
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
        <C>upheld serve</C> runs a small API that loads the models once and keeps them warm. Call it from any language. It needs the <C>api</C> extra.
      </p>
      <Code>{`pip install "upheld[models,api]"
upheld serve --port 8000

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
          [
            "POST /audit/{provider}",
            <>Takes an OpenAI, Anthropic, Perplexity or Gemini response as its body, with <C>auto</C> or the provider's name in the path and an optional <C>?question=</C>. See <A href="#providers">Audit a provider's response</A>.</>,
          ],
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

const mcp: DocPage = {
  id: "mcp",
  title: "Check answers from an AI agent",
  body: (
    <>
      <p>
        <C>upheld mcp</C> is an <A href="https://modelcontextprotocol.io">MCP</A> server, so Claude Code, Cursor, Codex and other agents can check the citations in an
        answer they've drafted before they show it to you. It runs on your machine over stdio.
      </p>
      <p>
        With <A href="https://docs.astral.sh/uv/">uv</A>, run it once in a terminal first. The first run installs torch and the rest, which takes a few minutes, and
        clients give up on a server that slow to start.
      </p>
      <Code>{`uvx --from "upheld[models,mcp]" upheld mcp --help`}</Code>
      <p>Then add it to your client.</p>
      <H3>Claude Code</H3>
      <Code>{`claude mcp add --scope user upheld -- uvx --from "upheld[models,mcp]" upheld mcp`}</Code>
      <p>
        <C>--scope user</C> makes it available in all your projects. Leave it out for the current project only, or use <C>--scope project</C> to share it with the
        project through <C>.mcp.json</C>. <C>claude mcp list</C> should show it as connected.
      </p>
      <H3>Cursor</H3>
      <p>
        Add it to <C>~/.cursor/mcp.json</C>, or to <C>.cursor/mcp.json</C> in a project:
      </p>
      <Code label="json">{`{
  "mcpServers": {
    "upheld": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "upheld[models,mcp]", "upheld", "mcp"]
    }
  }
}`}</Code>
      <H3>Codex CLI</H3>
      <p>
        Add it to <C>~/.codex/config.toml</C>:
      </p>
      <Code label="toml">{`[mcp_servers.upheld]
command = "uvx"
args = ["--from", "upheld[models,mcp]", "upheld", "mcp"]
startup_timeout_sec = 60
tool_timeout_sec = 600`}</Code>
      <p>
        <C>codex mcp add upheld -- uvx --from "upheld[models,mcp]" upheld mcp</C> writes the first three lines. Add the timeouts by hand: Codex gives up on a tool
        call after 60 seconds by default, and the first call waits for the models to load.
      </p>
      <H3>Any other client</H3>
      <p>
        A stdio server with the command <C>uvx</C> and the arguments <C>--from upheld[models,mcp] upheld mcp</C>. Clients configured with JSON mostly take the Cursor
        entry above. Without uv, <C>pip install "upheld[models,mcp]"</C> and use the command <C>upheld</C> with the argument <C>mcp</C>.
      </p>
      <H3>The tools</H3>
      <Table
        head={["Tool", "Takes", "Returns"]}
        rows={[
          [
            "audit_citations",
            <>
              An answer with <C>[1]</C>-style markers or inline links, and its sources in order: URLs, the sources' text, or <C>{"{id, url, title, text}"}</C> objects.
              Or a provider's response, as for <C>upheld.audit</C>. Optionally the question.
            </>,
            <>
              Counts of each verdict, and for each claim that isn't supported its verdict, the cited URL, the score, the closest passage and a note, such as "checked
              against the Wayback Machine copy of 2026-10-02". <C>full_report: true</C> adds the whole <A href="#report">report</A>.
            </>,
          ],
          ["check_claim", <>One statement, and one source's URL or text.</>, <>The verdict, score and closest passage, whether or not the source backs it.</>],
        ]}
      />
      <p>For an answer that says the Eiffel Tower "was designed by Frank Lloyd Wright [1]", citing Wikipedia, the agent gets this (the passage is shortened here):</p>
      <Code label="json">{`{
  "summary": "1 of 2 cited claims supported",
  "verdicts": {"supported": 1, "unsupported": 1},
  "problems": [
    {
      "claim": "It was designed by Frank Lloyd Wright.",
      "verdict": "unsupported",
      "citations": [
        {
          "source": "1",
          "url": "https://en.wikipedia.org/wiki/Eiffel_Tower",
          "verdict": "unsupported",
          "score": 0.209,
          "closest_passage": "... It is named after the engineer Gustave Eiffel, whose company designed and built the tower from 1887 to 1889. ...",
          "not_in_source": ["Frank Lloyd Wright"],
          "flagged": ["It was designed by Frank Lloyd Wright"]
        }
      ]
    }
  ],
  "verifier": "ensemble:minicheck+lexical+lettuce@0.5",
  "retrieval": "hybrid:bm25+bge-small-en-v1.5"
}`}</Code>
      <H3>Options</H3>
      <p>
        The models load on the first call, in about half a minute once they're downloaded, and stay loaded. Later calls take a few seconds, mostly fetching pages.
        Audits run one at a time, report progress while they run, and stop after 300 seconds. Each client session starts its own server, which holds about 4 GB once it
        has loaded the models. Options go after <C>upheld mcp</C>, or in the server's environment:
      </p>
      <Table
        head={["Option", "Variable", "Default"]}
        rows={[
          [
            "--verifier",
            <C>UPHELD_VERIFIER</C>,
            <>
              <C>ensemble</C>. <C>lexical</C> with <C>--retrieval bm25</C> needs no models (just <C>upheld[mcp]</C>) but is much weaker; <C>ensemble+judge</C> needs{" "}
              <C>upheld[models,judge,mcp]</C>. See <A href="#verifiers">Pick a verifier</A>.
            </>,
          ],
          ["--retrieval", <C>UPHELD_RETRIEVAL</C>, <C>auto</C>],
          ["--threshold", <C>UPHELD_THRESHOLD</C>, <>the verifier's</>],
          ["--timeout", <C>UPHELD_TIMEOUT</C>, <>300 seconds per call, model loading included</>],
          ["--allow-private", <C>UPHELD_ALLOW_PRIVATE</C>, <>off, so localhost and private-network URLs are refused</>],
        ]}
      />
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
        with <C>verifier=</C> in <C>upheld.audit()</C> and <C>upheld.Auditor()</C>, or by name with <C>make_verifier()</C>. Scores are macro-F1 on AttributionBench's in-distribution test sets, for the verifier alone (the entity check
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
        the full comparison, including GPT-4 and fine-tuned models, see the <A href="/#quality">benchmarks</A>.
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
      <Code>{`upheld eval labels.jsonl --verifier ensemble`}</Code>
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
        The <C>Dockerfile</C> in the repo builds one image with the API and this website. It bakes the
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
        The CLI reads a <C>.json</C> file as an <C>AuditRequest</C> or a <A href="#providers">provider's response</A>, and anything else as the answer text.{" "}
        <C>POST /audit</C>, <C>upheld.audit()</C> and <C>run_audit()</C> take the same request.
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
          ["sources[].url", "string, optional", "Fetched when there's no text. Capped at 5 MB. A page that's dead or can't be read is read from its newest Wayback Machine copy instead."],
          ["sources[].title", "string, optional", "For your own reference."],
          [
            "cited_spans",
            "list, optional",
            <>Character ranges of the answer marked as cited, <C>{'{"start": 0, "end": 40, "cited": ["1"]}'}</C>. Each is checked as one claim, in place of the sentences it overlaps. Filled in from a provider's response; up to 500.</>,
          ],
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
        <C>--json</C>, <C>POST /audit</C>, <C>upheld.audit()</C> and <C>run_audit()</C> all return the same report. This one is from the Eiffel Tower answer on the{" "}
        <A href="/#report">home page</A>, trimmed to one claim:
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
    {"id": "1", "url": "https://en.wikipedia.org/wiki/Eiffel_Tower", "resolved_url": null, "status": "live", "http_status": 200, "chars": 65753,
     "note": null, "archived_at": null, "archive_url": null},
    {"id": "2", "url": "https://en.wikipedia.org/wiki/Eiffel_Tower_repainting_schedule", "resolved_url": null, "status": "likely_fabricated",
     "http_status": 404, "chars": 0, "note": "HTTP 404; never archived", "archived_at": null, "archive_url": null}
  ]
}`}</Code>
      <Table
        head={["Field", "Meaning"]}
        rows={[
          ["verifier, retrieval", "What produced this report, threshold included. Scores aren't comparable across verifiers."],
          ["claims[].start, end", "Character offsets of the claim in the answer, for highlighting. For a provider's response, in the answer text upheld assembled from it."],
          ["claims[].verdict", <>The best verdict among the claim's citations. A claim whose citations each fail is re-checked against them together, for facts that span two sources.</>],
          ["checks[]", "One per citation: that source's verdict, the support score (0 to 1), and the passages it was judged against."],
          ["unsupported_spans", "Character offsets within the claim text of the words the source doesn't back."],
          ["missing_entities", <>Names in the claim that appear nowhere in the source. When the score would otherwise pass, they make the verdict <C>wrong_entity</C>.</>],
          ["sources[].status", <>Whether each cited source could be read. See <A href="#verdicts">link statuses</A>.</>],
          ["sources[].resolved_url", "Where the URL redirected to, if it did. Gemini cites pages through Google redirect links, and this is the page."],
          ["sources[].archived_at, archive_url", <>Set when the text came from a Wayback Machine copy: when the copy was taken, and where to see it. Each check against that source says so in its <C>note</C>.</>],
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
  unverifiable: "The source exists but couldn't be read, and neither could an archived copy: blocked, or no readable text (a scanned PDF, say).",
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
        Run <C>upheld</C> wherever it's installed, or <C>uv run upheld</C> from a clone. <C>--help</C> on any command lists the same options.
      </p>
      <H3>upheld audit PATH</H3>
      <p>
        Audit one answer. <C>PATH</C> is a <C>.json</C> request or provider response, a markdown or text answer, or <C>-</C> for stdin.
      </p>
      <Table
        head={["Option", "Default", "Does"]}
        rows={[
          ["--question TEXT", <>none</>, "The question the answer responds to."],
          [
            "--from NAME",
            <C>auto</C>,
            <>Whose API response the JSON is: <C>openai</C>, <C>anthropic</C>, <C>perplexity</C> or <C>gemini</C>. <C>auto</C> tells them apart, and reads JSON with an <C>answer</C> as an AuditRequest.</>,
          ],
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
        Run the HTTP API, plus the website when <C>web/dist</C> is built. Takes <C>--host</C> (default{" "}
        <C>127.0.0.1</C>), <C>--port</C> (default <C>8000</C>), <C>--verifier</C> and <C>--retrieval</C>. Needs the <C>api</C> extra:{" "}
        <C>pip install "upheld[api]"</C>.
      </p>
      <H3>upheld mcp</H3>
      <p>
        Run the MCP server over stdio, for AI agents. Takes <C>--verifier</C>, <C>--retrieval</C>, <C>--threshold</C>, <C>--timeout</C> (default 300 seconds) and{" "}
        <C>--allow-private</C>, each also read from an <C>UPHELD_</C> environment variable. Needs the <C>mcp</C> extra. See{" "}
        <A href="#mcp">Check answers from an AI agent</A>.
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
          Machine: archived means link rot, never archived means likely fabricated. 403, 429, 5xx and timeouts only mean it couldn't be read, and so does a page with
          under 300 characters of text: a cookie wall, bot check or JavaScript shell, not the article. Either way, upheld then reads the Wayback Machine's newest copy of
          the page, if it has one, and the report says so and gives the copy's date.
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
          ["A source is unverifiable but opens fine in your browser.", <>The site blocked the fetch, or builds its text with JavaScript, and the Wayback Machine has no readable copy. Paste the page's text into the source's <C>text</C> field.</>],
          ["A source was read from an archived copy.", <>upheld couldn't read the live page. The copy can be older than the page the answer cited: check <C>archived_at</C>, and paste the current text into the source's <C>text</C> field if the page has changed.</>],
          ["Wikipedia or another site returns 403.", <>Some sites reject generic user agents. Set <C>UPHELD_USER_AGENT</C> to a string with your project's URL.</>],
          ["A localhost URL is refused.", <>Private addresses are blocked by default. Pass <C>--allow-private</C> on the CLI.</>],
          ["An MCP client can't start upheld.", <>Run <C>uvx --from "upheld[models,mcp]" upheld mcp --help</C> in a terminal once. The first run installs torch and takes longer than clients wait.</>],
          ["Codex says the upheld tool timed out.", <>Set <C>tool_timeout_sec = 600</C> under <C>[mcp_servers.upheld]</C>. Codex's default is 60 seconds, and the first call loads the models.</>],
          ["The agent's first audit stopped while the models loaded.", <>The first run downloads about 4 GB. The download carries on in the background, so ask the agent to try again in a minute or two.</>],
          ["It's too slow on CPU.", <>Try <C>--verifier minicheck</C>, or <C>--verifier lexical --retrieval bm25</C> to skip the models entirely.</>],
          ["A true claim is flagged.", <>Usually a one-step inference ("-14.9% change" vs "14.9% loss") or retrieval picking the wrong part of a long page. <C>--verifier ensemble+judge</C> handles both better: it reads 10 passages per claim and flags about half as many good citations.</>],
          ["A Gemini source says its redirect link no longer resolves.", <>Gemini's source links are redirects that expire. Audit Gemini responses soon after you get them.</>],
          ["Every claim is source_missing.", <>The reference list didn't survive the copy. Check that the markers' numbers match a list at the end, or pass the sources in JSON.</>],
        ]}
      />
      <p>
        Something else? <A href={`${GITHUB_URL}/issues`}>Open an issue</A>.
      </p>
    </>
  ),
};

const CODE_LABEL: Record<SnippetTab, string> = { CLI: "shell", Python: "python", HTTP: "shell", MCP: "shell" };

const setup: DocPage = {
  id: "setup",
  title: "Set up and first run",
  body: (
    <>
      <p>
        Three paths on the same engine: check one answer from the command line, audit a pipeline from Python or over HTTP, or let an AI agent check its own
        citations over MCP. Each block below runs as it stands.
      </p>
      <p>
        The first audit downloads about 4 GB of models into <C>~/.cache/huggingface</C>, which takes minutes. After that, loading the models takes about half a
        minute, and each later audit takes seconds.
      </p>
      {PATHS.map((p) => (
        <Fragment key={p.tab}>
          <H3>{p.name}</H3>
          {p.text.map((t) => (
            <p key={t}>{t}</p>
          ))}
          <Code label={CODE_LABEL[p.tab]}>{SNIPPETS[p.tab]}</Code>
        </Fragment>
      ))}
      <H3>Choosing a verifier</H3>
      <p>
        Agreement and flags are on the {FRESH_VERIFIED_CITATIONS} labeled 2026 citations, with the verifier alone. Bad means partial or unsupported.
        The judge needs the <C>judge</C> extra, which builds llama.cpp and downloads 8.7 GB.
      </p>
      <Table
        head={["Verifier", "Passages per claim", "Agreement", "Bad citations flagged", "Good citations flagged", "Time per claim", "Memory"]}
        rows={FRESH_VERIFIERS.map((v) => [
          <C>{v.verifier}</C>,
          String(v.passages),
          `${v.agreement}%`,
          `${v.badFlagged}%`,
          `${v.goodFlagged}%`,
          v.time,
          v.memory,
        ])}
      />
      <p>
        Pick <C>ensemble</C> for speed, <C>ensemble+judge</C> if you'll act on the flags.
      </p>
      <H3>When it looks broken</H3>
      <Table mono={false} head={["What you see", "What's going on"]} rows={BROKEN.map(([problem, fix]) => [problem, fix])} />
    </>
  ),
};

export const DOCS: { group: string; pages: DocPage[] }[] = [
  { group: "Getting started", pages: [overview, install, setup, quickstart] },
  { group: "Guides", pages: [providers, auditAnswer, python, http, mcp, verifiers, evaluate, selfHost] },
  { group: "Reference", pages: [input, report, verdicts, cli, howItWorks, troubleshooting] },
];
