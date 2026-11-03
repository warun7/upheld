# upheld

Checks whether an AI answer's citations actually support its claims.

AI search tools and deep-research agents now mostly cite real, working links, but the cited page often doesn't say what the answer claims: [one 2026 study](https://arxiv.org/abs/2605.06635) of 14 models found only 39–77% of cited facts were actually in the source. Link checkers can't see it. upheld splits an answer into claims, finds the relevant passage in each cited source, and says which claims the sources really back.

## How it's meant to be used

One engine, several ways in. They all call the same `run_audit()`.

| Surface | Who it's for | Status |
|---|---|---|
| **Python library + CLI** | Developers checking answers locally. Runs on a laptop (CPU, Apple or NVIDIA GPU), no API key, nothing leaves your machine except fetching the cited pages. | Working |
| **HTTP API** (`upheld serve`) | RAG builders: audit your pipeline's outputs in CI or as a guardrail before showing an answer. Also the reward server for phase 2. | Working |
| **Website + playground** (`web/`) | Anyone: paste an answer from Perplexity/ChatGPT/Gemini with its sources and see each claim highlighted. `upheld serve` hosts it next to the API. See [web/README.md](web/README.md). | Working, not yet deployed |
| **Browser extension** | Overlays verdicts directly on AI search answers. Calls the hosted API. Most visible, but brittle (each site's page structure changes). | Later |

## What it reports

Each citation gets one verdict, and each claim gets the best verdict among its citations:

| Verdict | Meaning |
|---|---|
| `supported` | The cited source backs the claim |
| `unsupported` | The source is real and readable, but doesn't back the claim. Flagged spans show which part. |
| `wrong_entity` | The evidence reads as supporting, but a named entity in the claim appears nowhere in the source (e.g. drug Y's trial cited for drug X) |
| `source_missing` | Cited source isn't listed, or the URL is dead and was never archived (likely fabricated) |
| `unverifiable` | The source exists but couldn't be read (blocked, link rot, no text) |
| `uncited` | A factual-looking sentence with no citation |

Every report names its verifier and threshold, because measured citation accuracy swings widely with the verifier (3% to 18% on identical outputs in one study).

## Quickstart

```bash
git clone https://github.com/warun7/upheld && cd upheld
uv sync --extra models                             # base deps + MiniCheck + LettuceDetect + embedding model (torch)
uv run upheld audit examples/glp1.json             # inline source text
uv run upheld audit examples/eiffel.md             # markdown answer with a reference list; fetches URLs
uv run upheld audit examples/eiffel.md --json      # full report
uv run upheld eval evals/smoke.jsonl               # verifier vs labels, with a threshold sweep
uv run upheld serve                                # POST /audit on http://127.0.0.1:8000
(cd web && npm ci && npm run build)                # optional: then `upheld serve` also hosts the site at /
uv run pytest
```

The first run downloads about 4 GB of models from Hugging Face: the two that the default ensemble verifier combines (`lytang/MiniCheck-Flan-T5-Large`, `KRLabsOrg/lettucedect-base-modernbert-en-v1`) and the retrieval embedder (`BAAI/bge-small-en-v1.5`). `--verifier minicheck` uses one model, and `--verifier lexical --retrieval bm25` runs with none. The most accurate verifier, `--verifier ensemble+judge`, also needs `uv sync --all-extras`, which builds llama.cpp from source, and downloads the 8.7 GB Granite Guardian GGUF on first use.

### Input

- **JSON** (`AuditRequest`): `{"question": "...", "answer": "...", "sources": [{"id": "1", "url": "...", "text": "..."}]}`. A source with `text` is used as-is; otherwise its `url` is fetched.
- **Markdown/text**: an answer with `[1]`-style markers or inline `[text](url)` links, optionally ending in a reference list (`[1] Title - https://...`). Use `-` to read from stdin.

## How it works

1. **Parse**: split the answer into sentences, map `[1]`, `[1, 2]`, `[^1]` and inline links to sources, and pull out a trailing reference list. Lead-ins and questions aren't treated as claims.
2. **Fetch**: download cited URLs (5 MB cap) and extract the main text: trafilatura for web pages, pypdf for PDFs, with a PDF's wrapped lines and words hyphenated across lines joined back up. A 404/410 or unresolvable domain is checked against the Wayback Machine: archived means link rot, never archived means likely fabricated. 403/429/5xx only mean "couldn't read", and so does a page with under 300 characters of text, which is a cookie wall, bot check or JavaScript shell rather than the article, or a scanned PDF with no text layer.
3. **Retrieve evidence**: chunk each source into ~120-word windows and pick the top 3 per claim, or the top 10 for the judge ensemble, which turns more of the page into fewer false alarms (see [Fresh 2026 benchmark](#fresh-2026-benchmark)). Hybrid mode (the default when the `dense` extra is installed) ranks passages with both BM25 and `bge-small-en-v1.5` embeddings and merges the rankings with reciprocal rank fusion, so paraphrases aren't missed. `--retrieval bm25` uses keywords only.
4. **Verify**: the default verifier combines three signals with a logistic regression whose four numbers were fit on 2,000 AttributionBench training rows:
   - [MiniCheck-Flan-T5-Large](https://arxiv.org/abs/2404.10774) (770M), trained to judge whether a document supports every part of a claim. Long sources are split into ~500-word chunks and the claim takes its best chunk.
   - Word overlap, with every number in the claim required to appear in the evidence.
   - LettuceDetect, run once per source over the **whole answer** (it was trained on full responses; scored as isolated sentences it flagged true claims with 0.89 hallucination probability). Its flagged tokens, or else the mismatched numbers, become the highlighted spans.

   `--verifier ensemble+judge` adds a fourth signal, refit with the other three: [Granite Guardian 3.3 8B](https://huggingface.co/ibm-granite/granite-guardian-3.3-8b), an LLM trained to judge whether a response is grounded in its documents, run locally with llama.cpp. It reads the claim against each ~1,500-word chunk of the evidence and takes the best.
5. **Entity check**: flag named entities in the claim that appear nowhere in the source. This gets its own verdict, `wrong_entity`, because it's a heuristic with a known false-alarm rate (see [How good is it](#how-good-is-it)).
6. **Combine**: a claim citing several sources that individually fail is re-checked against them together (multi-hop claims).

Fetching is guarded against SSRF (no private, loopback or metadata addresses, checked on every redirect) since a hosted API fetches URLs taken from untrusted text. `--allow-private` lifts this for local use.

## How good is it

Three kinds of test: a public benchmark of human-labeled citations, edited claims aimed at each failure upheld exists to catch, and a fresh benchmark of 2026 answers. The first two give the verifier the evidence directly, so parsing, fetching and retrieval aren't exercised. The fresh benchmark runs the whole pipeline on real pages.

### AttributionBench

[AttributionBench](https://arxiv.org/abs/2402.15089) (Li et al., 2024): 3,296 test claims, each with the evidence it cited and a human label for whether that evidence fully supports it, from seven datasets. Stanford-GenSearch and AttrScore-GenSearch are real answers from Bing Chat, Perplexity, YouChat and NeevaAI. Classes are balanced, and the metric is macro-F1 averaged over subsets, as in the paper. Every upheld threshold below was picked on the dev split, never on test.

| System | ID avg | ExpertQA | Stanford-GenSearch | OOD avg | Fit to AttributionBench |
|---|---|---|---|---|---|
| **upheld `ensemble+judge`** (opt-in) | **76.7** | **59.3** | **78.6** | 82.3 | 5 numbers, on 2,000 train rows |
| upheld `ensemble+judge` + entity check (as shipped) | 74.8 | 57.8 | 75.5 | 81.0 | same |
| **upheld `ensemble`** (default) | 74.4 | 57.8 | 71.8 | **83.1** | 4 numbers, on 2,000 train rows |
| upheld `ensemble` + entity check (as shipped) | 72.2 | 55.2 | 69.5 | 80.9 | same |
| upheld `judge` (Granite Guardian 3.3, 8B) | 74.2 | 59.1 | 77.3 | 80.3 | threshold only |
| upheld `minicheck` (MiniCheck-Flan-T5-Large, 770M) | 73.9 | 58.9 | 71.5 | 79.3 | threshold only |
| upheld `lettuce` (LettuceDetect-base, 150M) | 67.3 | 57.8 | 68.3 | 74.1 | threshold only |
| upheld `lexical` (word overlap) | 67.6 | 53.2 | 68.6 | 81.7 | threshold only |
| GPT-4 + chain of thought, zero-shot | 73.3 | 59.2 | 71.7 | 78.9 | no |
| FLAN-UL2 (20B), zero-shot | 73.6 | – | – | 81.3 | no |
| T5-XXL-TRUE (11B NLI), zero-shot | 72.2 | 54.5 | 68.5 | 80.5 | no |
| Best fine-tuned in the paper (per column) | 78.5 | 61.8 | 82.8 | 84.2 | fully fine-tuned |

ID = in-distribution subsets (ExpertQA, Stanford-GenSearch, AttributedQA, LFQA); OOD = BEGIN, AttrScore-GenSearch, HAGRID. Every subset is in `evals/results/attributionbench.json`.

What this says:

- **The default verifier went from 64.4 to 74.4 ID macro-F1**, above every zero-shot system in the paper and 4 points below the best fine-tuned one. On OOD it's within about a point of the best fine-tuned model. It runs locally in roughly 0.3–1 s per claim on an Apple M5 Pro.
- **The ensemble is lightly supervised, not zero-shot.** Its three weights and bias were fit on 2,000 rows of AttributionBench's train split: different rows from the test sets, but the same datasets. The clean zero-shot comparison is MiniCheck alone at its default threshold of 0.5: 73.3 ID and 79.6 OOD, level with GPT-4 on ID from a 770M model.
- **Most of the ensemble's gain over MiniCheck is on OOD** (+3.8), where answers mostly copy wording from their evidence and word overlap is a strong signal. On ID it adds 0.5, which is within noise.
- **An LLM judge closes more than half of the remaining ID gap.** Adding [Granite Guardian 3.3 8B](https://huggingface.co/ibm-granite/granite-guardian-3.3-8b) (IBM, Apache 2.0) as a fourth signal lifts ID from 74.4 to 76.7, 1.8 below the best fine-tuned model. Most of the gain is on real search-engine answers: Stanford-GenSearch goes from 71.8 to 78.6. OOD dips 0.8, all of it on BEGIN, where answers copy their evidence and word overlap already did the work. The judge costs an 8.7 GB model and, since its ensemble reads 10 passages per claim, about 2.5–3 s per claim in all, so it's opt-in: `--verifier ensemble+judge`.
- **The judge alone is about as good as MiniCheck on ID and better on search-engine answers** : 74.2 ID at the threshold picked on dev, and 75.6 at its default of 0.5, which involves no fitting at all. It reads the claim without the user's question: shown the question, it also judged whether the claim answered it, and its AUC on 300 dev rows fell from 0.85 to 0.76.
- **ExpertQA is still the hard part.** Expert-written claims against long technical evidence: 59.3 with the judge, level with GPT-4's 59.2. Every model in the paper scores below 62.
- **The entity check costs about 2 points here.** It turns 6% of the supported test claims into false alarms (names the source writes differently: abbreviations, partial names, translations), and AttributionBench has few wrong-entity errors to make up for it. The edited claims below show what it buys.

### Edited claims

`evals/perturbations.py` takes AttributionBench claims that humans labeled as supported, edits each one so its evidence no longer supports it, and checks whether upheld notices. 150 edits per type. Catch rates count only claims whose unedited version passes, so a verifier that flags everything earns nothing.

| Verifier | Unedited claims that pass | Wrong number | Wrong name, not in source | same, with entity check | Wrong name that is in source | Two claims joined, cited to both sources |
|---|---|---|---|---|---|---|
| `ensemble` | 73–76% | **100%** | 87% | **98%** | 35% | **83% supported**, 0% by one source alone |
| `ensemble+judge` | 73–77% | **100%** | 92% | 97% | **64%** | 77%, 0% |
| `judge` | 75–80% | **100%** | **95%** | 97% | 63% | 78%, 3% |
| `minicheck` | 71–74% | 92% | 90% | 97% | 57% | 68%, 4% |
| `lettuce` | 68–72% | 95% | 82% | 97% | 38% | 86% (59 pairs), 0% |
| `lexical` | 76–87% | 100% | 40% | 97% | 1% | 95%, 6% |

What this says:

- **Wrong numbers are solved.** The ensemble catches every one, because the word-overlap signal requires each number in the claim to appear in the evidence.
- **A name the source never mentions** is caught 87% of the time by the ensemble alone and 98% with the entity check. That's why the check stays on despite its benchmark cost, but reports its own verdict, `wrong_entity`: treat it as a prompt to look, not proof.
- **Pinning a fact on the wrong party is the weak spot.** When the swapped-in name also appears in the evidence (a claim credits a result to another drug, person or study the same page mentions), the default ensemble catches only 35%. MiniCheck alone catches 57%; the ensemble loses ground because word overlap finds every word of the edited claim in the source. The judge nearly doubles the ensemble's rate, to 64%, but this is still the case upheld handles worst.
- **Combining sources works.** Two supported claims joined into one sentence and cited `[1][2]` aren't fully supported by either source. Re-checking against both together marks 83% of them supported; without that step all of them would be flagged. No single source ever passed one on its own, except with word overlap (6%).

The edits are synthetic and the claims come from AttributionBench, so these numbers say whether each check does its job, not how often each failure happens in real answers.

### Fresh 2026 benchmark

25 current questions, answered on 31 October and 1 November 2026 by Claude, OpenAI and Gemini agents with their own web search (how, under [Evals](#evals)). upheld split each answer into claims and found 641 pairs of a claim and a page it cites. Each pair is labeled supported, partial, unsupported or can't judge: 639 by Claude Sonnet 5.5 subagents following [`labeling-guide.md`](evals/fresh/labeling-guide.md), 2 by hand. The labelers saw the question, the claim, the cited URL and upheld's retrieved passages, but not which agent wrote the answer or upheld's verdict, and read the full page whenever the passages didn't settle it. GPT and Gemini relabeled a sample of 150 to check Claude's labels ([below](#checking-claudes-labels)).

| Agent | Citations | Supported | Partial | Unsupported | Can't judge | Dead links |
|---|---|---|---|---|---|---|
| OpenAI `gpt-6-luna`, Codex CLI | 125 | **51%** | 28% | 14% | 6% | 1 |
| Claude Sonnet 5.5, Claude Code | 255 | **47%** | 25% | 17% | 11% | 6 |
| Gemini 3.8 Flash, Antigravity CLI | 257 | **41%** | 45% | 7% | 7% | 0 |

Perplexity has one answer (4 citations) so far and isn't ranked. The full table is [`evals/fresh/scoreboard.md`](evals/fresh/scoreboard.md). Its dead-link counts come from a re-audit on 3 November and differ in two places: Gemini shows 7, all one FDA label PDF that answers upheld with a 404 on most tries but serves the file to a browser, and Claude shows 5, because the Wayback Machine check failed for one of its dead links that day.

**upheld against these labels**: re-audited on 3 November, on the 492 citations whose page it could read, the default pipeline agreed with the label 76% of the time. It flagged 91% of the citations labeled partial or unsupported, and 70% of its flags were right. 18 of those citations are to PDFs, which upheld now reads; it agreed with the label on 14 of them.

**With the judge**: each verifier on the 499 labeled citations whose page upheld can read, with the page fetched and the passages retrieved the way upheld does it ([`evals/fresh/verifiers.py`](evals/fresh/verifiers.py), without the entity check, pages fetched on 3 November):

| Verifier | Passages per claim | Agreement | Macro-F1 | Bad citations flagged | Good citations flagged |
|---|---|---|---|---|---|
| `ensemble` (default) | 3 | 78% | 77.2 | **91%** | 36% |
| `ensemble+judge` | 10 | **84%** | **83.9** | 85% | **18%** |
| `judge` alone | 3 | 83% | 82.7 | 84% | 18% |
| `minicheck` | 3 | 72% | 71.6 | 81% | 38% |

The judge ensemble halves the false alarms on good citations and catches a few fewer bad ones. Part of that comes from reading more of the page:

| Passages per claim | 3 | 6 | 10 |
|---|---|---|---|
| `ensemble`: macro-F1, good citations flagged | **77.2**, 36% | 76.6, 30% | 76.8, 28% |
| `ensemble+judge`: macro-F1, good citations flagged | 81.5, 28% | 83.1, 21% | **83.9**, **18%** |

With more passages the default ensemble flags fewer good citations, but it misses bad ones at the same pace (91% caught at 3 passages, 82% at 10), so it keeps 3. The judge ensemble at 10 still catches 85% and flags a third fewer good citations, so it takes 10. The judge alone does best at 3. The settings were compared on these labels, so 83.9 is a little optimistic; all three are shown. The judge's lead holds when GPT or Gemini does the labeling instead of Claude ([below](#checking-claudes-labels)), but all three labelers are LLMs, so some of the gain may still be LLMs agreeing with each other rather than the judge being right.

What this says:

- **About half of each agent's citations fully back their sentence.** Most of the rest are partial: the page has part of the sentence but not a figure, a second fact or a conclusion drawn from it. Citations that back nothing at all are 7–17%.
- **No clear winner.** Each agent's share has a margin of roughly ±6–9 points, so OpenAI and Claude are level. Gemini's lower share is almost all partial: it is rarely flat wrong, but its sentences often say more than the cited page does.
- **Dead links are rare**: 7 of 641 citations, 6 of them Claude's.
- **upheld works as a first filter on real answers.** The default ensemble misses few bad citations, but about 3 in 10 of its flags are false alarms. The judge ensemble halves the false alarms on good citations, from 36% to 18%, and 83% of its flags are right. Two causes are fixed: block pages (cookie walls, VPN and bot checks, JavaScript shells) were judged as if they were the page, which made 7 good citations false alarms, and the supporting sentence often wasn't among the 3 passages retrieved. Of the judge ensemble's 43 remaining false alarms, 39 had the supporting sentence among their 10 passages, so what's left is mostly the verifier: a number restated in other units (4,310 mg of sodium as 10.8 g of salt), a sentence that leans on the one before it ("It also held in June and July."), or several facts in one sentence.

#### Checking Claude's labels

GPT (`gpt-6-luna` through the Codex CLI) and Gemini (Gemini 4 Argon through the Antigravity CLI) relabeled 150 citations, sampled in proportion to each agent and each of Claude's labels, under the same guide and the same blinding, and without seeing Claude's labels. Both got the passages plus the cited page's text, fetched once so that both read the same document. Full results: [`evals/fresh/crosscheck.md`](evals/fresh/crosscheck.md).

| Labelers | Same label | Same verdict (supported or not) | Cohen's κ (verdict) |
|---|---|---|---|
| Claude vs GPT | 85% | 93% | 0.86 |
| Claude vs Gemini | 86% | 92% | 0.85 |
| GPT vs Gemini | 89% | 92% | 0.84 |

- **Claude agrees with each of them as often as they agree with each other.** Where GPT and Gemini give the same verdict, Claude matches on 118 of 128 citations, and couldn't read the page for 6 more. The other 4 are citations Claude passed and both others called partial, all claims that say a little more than the page: "the DOJ argued" where the page says the court found, or "2.4 to 2.5 ppm" where the page gives 2.4.
- **No sign that Claude favors its own answers.** Claude's citations get 47% supported from Claude, 45% from GPT and 47% from Gemini. GPT is the strictest labeler on each ranked agent (40% supported overall, against 45% from Claude and from Gemini), and Gemini's citations rank last under all three labelers.
- **upheld's numbers hold.** On the 115 sampled citations whose page upheld can read, the judge ensemble scores 84.3, 84.3 and 85.2 macro-F1 against Claude's, GPT's and Gemini's labels, and the default ensemble scores 78.9, 80.2 and 76.1.

Caveats: the labels come from LLMs, not people. The cross-check rules out a bias peculiar to Claude, not one that all three models share, and only 2 citations have hand labels (Claude matched one; on the other it couldn't read the paywalled page). 57 citations (9%) are can't judge, mostly pages that block automated fetches; some blocked pages were read through an archived copy or the paper's abstract and others weren't. And these are agents with search following the same instructions, not the consumer search products.

## Evals

```bash
uv run python evals/attributionbench.py score minicheck --device mps   # cache one score per example, per split
uv run python evals/attributionbench.py report                         # dev-split thresholds, the ensemble, the tables above
uv run python evals/perturbations.py ensemble                          # the edited-claim tests
```

`score` runs `lexical`, `lettuce`, `minicheck` or `judge` over AttributionBench's train sample, dev and both test splits and caches the scores in `evals/results/scores/`, so `report` can compare and combine verifiers without rerunning them. `report` also prints the weights that `EnsembleVerifier` hard-codes for both ensembles, with and without the judge.

**Fresh 2026 benchmark** (`evals/fresh/`, results under [How good is it](#fresh-2026-benchmark)). AttributionBench's search-engine answers are from 2023. This collects answers to 25 current questions, converts them to `[n]` markers, and labels each citation blind, with the provider and upheld's verdict hidden.

Each answer comes from a vendor's own agent using that vendor's own web search, with the same instructions: answer as a search assistant would, cite with `[n]` markers, use nothing but search.

- **Claude:** Claude Sonnet 5.5, as Claude Code subagents with the WebSearch tool.
- **OpenAI:** `gpt-6-luna` through the Codex CLI with OpenAI's web search. It runs in an empty read-only sandbox, without the user's MCP servers.
- **Gemini:** Gemini 3.8 Flash through the Antigravity CLI (`agy`) with its `search_web` tool. Google's redirect links are resolved to the real URLs when the answer is collected.

The OpenAI and Gemini answers run on a ChatGPT or Google subscription, not a paid API. The collector rejects any answer whose agent used a tool other than search, or cited a source it didn't list. Answers that come back in their own citation format (a provider's API, say) don't measure quite the same thing, so these rows compare agents with search rather than the consumer search products. Perplexity has no subscription CLI. It goes through OpenRouter at about a cent per question, and only its first answer is collected so far.

```bash
uv run python evals/fresh/collect.py openai gemini --limit 25   # needs codex and agy, logged in
uv run python evals/fresh/label.py prepare      # audit every answer, fetching the cited pages; resumable
uv run python evals/fresh/label.py label        # label by hand, s/p/u/x per citation; resumable
uv run python evals/fresh/label.py scoreboard   # per-provider table + upheld's agreement with the labels
uv run python evals/fresh/verifiers.py pages     # fetch each labeled citation's page once, as upheld does
uv run python evals/fresh/verifiers.py score judge && uv run python evals/fresh/verifiers.py report   # each verifier vs the labels, at 3, 6 and 10 passages
uv run python evals/fresh/crosscheck.py sample && uv run python evals/fresh/crosscheck.py pages    # 150 citations, their pages fetched once
uv run python evals/fresh/crosscheck.py label gpt && uv run python evals/fresh/crosscheck.py label gemini && uv run python evals/fresh/crosscheck.py report
```

The labels in `labels-claude.jsonl` came from Claude subagents given `labeling-guide.md` and one blinded batch of items each; each "supported" or "partial" label carries a quote from the page. Hand labels in `labels.jsonl` override them. The output, `scoreboard.md`, answers both "how often do each tool's citations hold up?" and "how often does upheld agree with the labels?", on 2026 answers with real fetching and retrieval. `items.jsonl`, the pairs with their retrieved passages, holds text copied from the cited pages, so it isn't committed; `prepare` rebuilds it.

`verifiers.py` scores each verifier against the labels without the rest of the pipeline. It fetches each labeled citation's page once, the way upheld does, retrieves the top 3, 6 and 10 passages per claim, and caches every member's score for each setting in `scores/`, so the ensembles and settings can be compared without rerunning the models. The fetched pages, in `sources/`, aren't committed.

`crosscheck.py` checks the Claude labels. GPT and Gemini relabel a stratified sample of 150 citations through their subscription CLIs, with no tools at all. Antigravity can't open a URL, so each cited page is fetched once and both labelers get the same text in the prompt. A page that can't be read is taken from the Wayback Machine, then from the copy Claude read; text under 300 characters counts as a block page. A batch is rejected and retried if its labeler used a tool or skipped an item. The labels are in `labels-gpt.jsonl` and `labels-gemini.jsonl`, and the report is `crosscheck.md`. The fetched pages, in `pages/`, aren't committed either.

`upheld eval` scores any verifier against a JSONL of hand labels (`claim`, `evidence`, `label`, and ideally the full `answer`), with a threshold sweep. `evals/smoke.jsonl` is 8 rows that check the command works; it is not a benchmark.

`evals/retrieval_check.py` checks retrieval: for 10 paraphrased claims against the live Eiffel Tower Wikipedia article, it reports where the supporting passage ranks. BM25 puts it in the top 3 for 9/10 claims, hybrid for 10/10. The claims are hand-written, so this is a regression check, not a benchmark.

## Known limitations

- **One-step inferences fail without the judge.** In `examples/glp1.json` the source reports "the mean change in body weight ... was -14.9%" and the answer says "an average weight loss of 14.9%". The default ensemble scores that 0.42 and marks it unsupported, as is the matching placebo claim. `--verifier ensemble+judge` passes both (0.70 and 0.71). `examples/eiffel.md` still marks the true claim "intended to stand for only 20 years" unsupported with the judge (0.44): retrieval finds "slated for dismantling in 1909", but nothing connects that to 20 years.
- **Wrong-party claims slip through** about two times in three when the wrong name is also in the source, and about one time in three with the judge (see [Edited claims](#edited-claims)).
- **Contradictions in the source's own words can pass without the judge.** "The Great Wall of China is visible from the Moon with the naked eye", cited to its Wikipedia article, scores 0.57 and is marked supported, though the retrieved passage says it cannot be seen: word overlap and LettuceDetect outvote MiniCheck. The judge ensemble marks it unsupported (0.45).
- **Numbers are matched as digits, not quantities.** "It stands 410 metres tall" passes against the Eiffel Tower article (0.64) because the page gives the base as 410 ft. It passes with the judge too (0.52).
- **ExpertQA-style claims** (long, technical, expert-written) score 57.8 macro-F1, or 59.3 with the judge, so expect more mistakes on specialist content.
- **Entity check is a heuristic** (capitalized phrases + word frequency), not NER. It false-alarms on names the source writes differently and misses lowercase entities.
- **Speed.** The ensemble takes roughly 0.3–1 s per claim per source on an Apple M5 Pro and is several times slower on CPU. MiniCheck dominates. The judge ensemble reads 10 passages per claim, so it takes about 2.5–3 s per claim per source with Metal (the judge about 2 s of that, against 0.75 s on 3 passages), and needs about 9 GB of free memory. `--verifier lexical` is instant but much weaker.
- **No OCR.** A scanned PDF with no text layer comes back `unverifiable`, and so does a PDF over the 5 MB cap.
- **Only short block pages are caught.** A page with under 300 characters of readable text is reported as unreadable rather than judged: in the fresh benchmark those were all cookie walls, VPN or bot checks, or JavaScript apps whose text loads in the browser. A longer stand-in, such as a paywall teaser with the article's first paragraph, is still read as the page.
- **Sentence-level claims.** A sentence with two facts is judged as one unit.
- **Some servers answer 404 to anything that isn't a browser**, so upheld can call a live page a dead link. In the fresh benchmark an FDA label PDF did this on most tries, which made 7 of Gemini's citations look dead.
- Some sites reject generic user agents. The default names this repo; set `UPHELD_USER_AGENT` to your own project URL if you deploy upheld (Wikipedia returns 403 instead of 404 for missing pages without one).

## Roadmap

**Phase 1: auditor**
- ~~Hybrid retrieval (BM25 + a small embedding model)~~ done
- ~~Benchmark the verifiers on AttributionBench~~ done
- ~~Stronger verifier, threshold calibrated on a held-out split~~ done: MiniCheck + ensemble, 64.4 → 74.4 ID macro-F1
- ~~Edited-claim tests for each failure type~~ done
- ~~Run the fresh 2026 benchmark~~ done: 641 citations from Claude, OpenAI and Gemini agents, 41–51% fully supported, and upheld flags 91% of the rest. GPT and Gemini relabeled a 150-citation sample and agree with Claude on 92–93% of verdicts, with no sign of self-preference. Next: Perplexity (about $0.25 of OpenRouter credit), and hand labels on the citations the labelers disagree on
- ~~Cut false alarms on real pages~~ done: block pages are reported unreadable, and the judge ensemble reads 10 passages per claim, flagging 18% of good citations against the default's 36%
- ~~LLM judge for hard claims~~ done: Granite Guardian 3.3 8B as an opt-in fourth signal, 74.4 → 76.7 ID macro-F1, wrong-party swaps caught 35% → 64%, fresh-label agreement 78% → 84% with 10 passages per claim. Next: fine-tuning MiniCheck on AttributionBench's train split (the paper's best fine-tuned model reaches 78.5 ID), and a faster judge so it can be the default
- Speed: MiniCheck in bf16, and batching claims across sources
- ~~PDF sources~~ done: read with pypdf, which made 9 of the 10 PDFs cited in the fresh benchmark readable. Next: OCR for scans
- ~~Web app~~ done: landing page and playground in `web/`. Next: deploy it with the hosted API, then a browser extension

**Phase 2: train a search agent to cite honestly**
- Qwen3-4B + LoRA, GRPO, BM25 over Wikipedia, NQ + HotpotQA
- Baseline outcome-only reward → measure citation faithfulness with this auditor
- Add a faithfulness reward from this verifier; watch for reward hacking (copying, refusals); fix with sentence-level credit or grounding-gated accuracy
