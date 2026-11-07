// The setup guide's copy, shared by the landing page's Install section and the docs' Setup page.
// Every fact is from the root README.md. The verifier numbers are in benchmarks.ts (FRESH_VERIFIERS).

export const SNIPPETS = {
  CLI: `pip install "upheld[models]"

# an answer with [1]-style markers and a reference list
upheld audit answer.md

# or a provider's response, saved as JSON
upheld audit response.json --from openai`,
  Python: `import upheld

report = upheld.audit("The Eiffel Tower is 330 metres tall [1]. It was designed by Frank Lloyd Wright [1].", ["https://en.wikipedia.org/wiki/Eiffel_Tower"])
for claim in report.claims:
    print(claim.verdict, claim.text)`,
  HTTP: `pip install "upheld[models,api]"
upheld serve        # the API on :8000

curl -s localhost:8000/audit -H 'content-type: application/json' -d '{
  "answer": "The Eiffel Tower is 330 metres tall [1].",
  "sources": [{"id": "1", "url": "https://en.wikipedia.org/wiki/Eiffel_Tower"}]
}'`,
  MCP: `# once, in a terminal: installs torch and the rest
uvx --from "upheld[models,mcp]" upheld mcp --help

# then add it to Claude Code (Cursor and Codex: see the docs)
claude mcp add --scope user upheld -- uvx --from "upheld[models,mcp]" upheld mcp`,
} as const;

export type SnippetTab = keyof typeof SNIPPETS;

/** Three paths, four tabs: Python and HTTP are both "audit a pipeline". */
export const PATHS: { tab: SnippetTab; name: string; text: string[] }[] = [
  {
    tab: "CLI",
    name: "Check one answer",
    text: [
      "Save the answer as answer.md, with its reference list at the end, and run the first line. The first run downloads about 4 GB of models into ~/.cache/huggingface, which takes minutes. Later runs take seconds.",
      "It prints the verifier and the retrieval it used, then how many cited claims are supported, then a table with one row per claim: its verdict, its score, and the words the source doesn't back. A second table lists the sources and their status.",
    ],
  },
  {
    tab: "Python",
    name: "Audit a pipeline in Python",
    text: [
      "upheld.audit takes the answer and its sources, as text or URLs in the order the answer cites them, and returns a verdict and a support score for each claim, with the evidence behind it.",
      "Pass a provider's response as it came back from the API, and upheld reads the sources from it. To audit many answers, make an upheld.Auditor once and keep the models loaded.",
    ],
  },
  {
    tab: "HTTP",
    name: "Audit a pipeline over HTTP",
    text: [
      "upheld serve runs the API on port 8000. POST /audit takes an answer and its sources. POST /audit/{provider} takes a provider's response as it is. Both return the report as JSON, so any language can call them, including a CI job.",
    ],
  },
  {
    tab: "MCP",
    name: "Let your agent check itself",
    text: [
      "Warning: this pulls torch and the models, and the first call loads them. Run the first line once in a terminal, because clients give up on a server that starts slowly.",
      "Each client session starts its own server, which holds about 4 GB once the models are loaded. The agent can then check a draft answer's citations before it shows the answer, or check one claim against one page.",
    ],
  },
];

/** Problem, then what to do. Verdict names are the report's own. */
export const BROKEN: [string, string][] = [
  [
    "A page blocks bots, or answers 401, 403 or 429.",
    "It's reported unverifiable. upheld reads the Wayback Machine's copy instead when there is one.",
  ],
  [
    "A page returns 404 to bots but works in a browser.",
    "If it was never archived, upheld reports it as likely fabricated. That's wrong here: the page exists and the bot was refused. Open the link yourself to check.",
  ],
  ["A scanned PDF.", "It's reported unverifiable, because it has no text layer. upheld doesn't OCR."],
  [
    "A Gemini source link.",
    "Gemini's source links are redirects that expire. Once one has, its claims are reported unverifiable. Audit a Gemini answer soon after you get it.",
  ],
  ["The judge runs out of memory.", "It needs about 9 GB of free memory. Pass --verifier ensemble instead."],
  [
    "You used --verifier lexical --retrieval bm25.",
    "It needs no models and is instant, but it's much weaker: it checks word overlap. Use it when you can't spare the memory or the download.",
  ],
];
