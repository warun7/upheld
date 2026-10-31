# upheld

Checks whether an AI answer's citations actually support its claims.

AI search tools and deep-research agents now mostly cite real, working links, but the cited page often doesn't say what the answer claims: [one 2026 study](https://arxiv.org/abs/2605.06635) of 14 models found only 39–77% of cited facts were actually in the source. Link checkers can't see it. upheld splits an answer into claims, finds the relevant passage in each cited source, and says which claims the sources really back.

## How it's meant to be used

One engine, several ways in. They all call the same `run_audit()`.

| Surface | Who it's for | Status |
|---|---|---|
| **Python library + CLI** | Developers checking answers locally. Runs on a laptop (CPU, Apple or NVIDIA GPU), no API key, nothing leaves your machine except fetching the cited pages. | Working |
| **HTTP API** (`upheld serve`) | RAG builders: audit your pipeline's outputs in CI or as a guardrail before showing an answer. Also the reward server for phase 2. | Working |
| **Web app** | Anyone: paste an answer from Perplexity/ChatGPT/Gemini with its sources and see each claim highlighted. The public demo. | Next |
| **Browser extension** | Overlays verdicts directly on AI search answers. Calls the hosted API. Most visible, but brittle (each site's page structure changes). | Later |

## What it reports

Each citation gets one verdict, and each claim gets the best verdict among its citations:

| Verdict | Meaning |
|---|---|
| `supported` | The cited source backs the claim |
| `unsupported` | The source is real and readable, but doesn't back the claim. Flagged spans show which part. |
| `wrong_entity` | The evidence reads as supporting, but a named entity in the claim appears nowhere in the source (e.g. drug Y's trial cited for drug X) |
| `source_missing` | Cited source isn't listed, or the URL is dead and was never archived (likely fabricated) |
| `unverifiable` | The source exists but couldn't be read (blocked, link rot, PDF, no text) |
| `uncited` | A factual-looking sentence with no citation |

Every report names its verifier and threshold, because measured citation accuracy swings widely with the verifier (3% to 18% on identical outputs in one study).

## Quickstart

```bash
git clone https://github.com/warun7/upheld && cd upheld
uv sync --all-extras                               # base deps + MiniCheck + LettuceDetect + embedding model (torch)
uv run upheld audit examples/glp1.json             # inline source text
uv run upheld audit examples/eiffel.md             # markdown answer with a reference list; fetches URLs
uv run upheld audit examples/eiffel.md --json      # full report
uv run upheld eval evals/smoke.jsonl               # verifier vs labels, with a threshold sweep
uv run upheld serve                                # POST /audit on http://127.0.0.1:8000
uv run pytest
```

The first run downloads about 4 GB of models from Hugging Face: the two that the default ensemble verifier combines (`lytang/MiniCheck-Flan-T5-Large`, `KRLabsOrg/lettucedect-base-modernbert-en-v1`) and the retrieval embedder (`BAAI/bge-small-en-v1.5`). `--verifier minicheck` uses one model, and `--verifier lexical --retrieval bm25` runs with none.

### Input

- **JSON** (`AuditRequest`): `{"question": "...", "answer": "...", "sources": [{"id": "1", "url": "...", "text": "..."}]}`. A source with `text` is used as-is; otherwise its `url` is fetched.
- **Markdown/text**: an answer with `[1]`-style markers or inline `[text](url)` links, optionally ending in a reference list (`[1] Title - https://...`). Use `-` to read from stdin.

## How it works

1. **Parse**: split the answer into sentences, map `[1]`, `[1, 2]`, `[^1]` and inline links to sources, and pull out a trailing reference list. Lead-ins and questions aren't treated as claims.
2. **Fetch**: download cited URLs (5 MB cap, main-content extraction with trafilatura). A 404/410 or unresolvable domain is checked against the Wayback Machine: archived means link rot, never archived means likely fabricated. 403/429/5xx only mean "couldn't read".
3. **Retrieve evidence**: chunk each source into ~120-word windows and pick the top 3 per claim. Hybrid mode (the default when the `dense` extra is installed) ranks passages with both BM25 and `bge-small-en-v1.5` embeddings and merges the rankings with reciprocal rank fusion, so paraphrases aren't missed. `--retrieval bm25` uses keywords only.
4. **Verify**: the default verifier combines three signals with a logistic regression whose four numbers were fit on 2,000 AttributionBench training rows:
   - [MiniCheck-Flan-T5-Large](https://arxiv.org/abs/2404.10774) (770M), trained to judge whether a document supports every part of a claim. Long sources are split into ~500-word chunks and the claim takes its best chunk.
   - Word overlap, with every number in the claim required to appear in the evidence.
   - LettuceDetect, run once per source over the **whole answer** (it was trained on full responses; scored as isolated sentences it flagged true claims with 0.89 hallucination probability). Its flagged tokens, or else the mismatched numbers, become the highlighted spans.
5. **Entity check**: flag named entities in the claim that appear nowhere in the source. This gets its own verdict, `wrong_entity`, because it's a heuristic with a known false-alarm rate (see [How good is it](#how-good-is-it)).
6. **Combine**: a claim citing several sources that individually fail is re-checked against them together (multi-hop claims).

Fetching is guarded against SSRF (no private, loopback or metadata addresses, checked on every redirect) since a hosted API fetches URLs taken from untrusted text. `--allow-private` lifts this for local use.

## How good is it

Two kinds of test: a public benchmark of human-labeled citations, and edited claims aimed at each failure upheld exists to catch. Both give the verifier the evidence directly, so parsing, fetching and retrieval aren't exercised. The fresh benchmark under [Evals](#evals) is for that.

### AttributionBench

[AttributionBench](https://arxiv.org/abs/2402.15089) (Li et al., 2024): 3,296 test claims, each with the evidence it cited and a human label for whether that evidence fully supports it, from seven datasets. Stanford-GenSearch and AttrScore-GenSearch are real answers from Bing Chat, Perplexity, YouChat and NeevaAI. Classes are balanced, and the metric is macro-F1 averaged over subsets, as in the paper. Every upheld threshold below was picked on the dev split, never on test.

| System | ID avg | ExpertQA | Stanford-GenSearch | OOD avg | Fit to AttributionBench |
|---|---|---|---|---|---|
| **upheld `ensemble`** (default) | **74.4** | 57.8 | 71.8 | **83.1** | 4 numbers, on 2,000 train rows |
| upheld `ensemble` + entity check (as shipped) | 72.2 | 55.2 | 69.5 | 80.9 | same |
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
- **ExpertQA is still the hard part.** Expert-written claims against long technical evidence: 57.8, below GPT-4's 59.2. Every model in the paper scores below 62.
- **The entity check costs about 2 points here.** It turns 6% of the supported test claims into false alarms (names the source writes differently: abbreviations, partial names, translations), and AttributionBench has few wrong-entity errors to make up for it. The edited claims below show what it buys.

### Edited claims

`evals/perturbations.py` takes AttributionBench claims that humans labeled as supported, edits each one so its evidence no longer supports it, and checks whether upheld notices. 150 edits per type. Catch rates count only claims whose unedited version passes, so a verifier that flags everything earns nothing.

| Verifier | Unedited claims that pass | Wrong number | Wrong name, not in source | same, with entity check | Wrong name that is in source | Two claims joined, cited to both sources |
|---|---|---|---|---|---|---|
| `ensemble` | 73–76% | **100%** | 87% | **98%** | 35% | **83% supported**, 0% by one source alone |
| `minicheck` | 71–74% | 92% | **90%** | 97% | **57%** | 68%, 4% |
| `lettuce` | 68–72% | 95% | 82% | 97% | 38% | 86% (59 pairs), 0% |
| `lexical` | 76–87% | 100% | 40% | 97% | 1% | 95%, 6% |

What this says:

- **Wrong numbers are solved.** The ensemble catches every one, because the word-overlap signal requires each number in the claim to appear in the evidence.
- **A name the source never mentions** is caught 87% of the time by the ensemble alone and 98% with the entity check. That's why the check stays on despite its benchmark cost, but reports its own verdict, `wrong_entity`: treat it as a prompt to look, not proof.
- **Pinning a fact on the wrong party is the weak spot.** When the swapped-in name also appears in the evidence (a claim credits a result to another drug, person or study the same page mentions), the ensemble catches only 35%. MiniCheck alone catches 57%; the ensemble loses ground because word overlap finds every word of the edited claim in the source. This is the clearest target for an LLM judge or fine-tuning.
- **Combining sources works.** Two supported claims joined into one sentence and cited `[1][2]` aren't fully supported by either source. Re-checking against both together marks 83% of them supported; without that step all of them would be flagged. No single source ever passed one on its own, except with word overlap (6%).

The edits are synthetic and the claims come from AttributionBench, so these numbers say whether each check does its job, not how often each failure happens in real answers.

## Evals

```bash
uv run python evals/attributionbench.py score minicheck --device mps   # cache one score per example, per split
uv run python evals/attributionbench.py report                         # dev-split thresholds, the ensemble, the tables above
uv run python evals/perturbations.py ensemble                          # the edited-claim tests
```

`score` runs `lexical`, `lettuce` or `minicheck` over AttributionBench's train sample, dev and both test splits and caches the scores in `evals/results/scores/`, so `report` can compare and combine verifiers without rerunning them. `report` also prints the ensemble weights that `EnsembleVerifier` hard-codes.

**Fresh 2026 benchmark** (`evals/fresh/`, built but not yet run). AttributionBench's search-engine answers are from 2023. This collects answers to 50 current questions from Perplexity, ChatGPT search, Gemini and Claude, converts every provider's citation format to `[n]` markers, and has a person label each citation blind, with the provider and upheld's verdict hidden:

```bash
uv sync --extra collect
uv run python evals/fresh/collect.py perplexity openai gemini claude --limit 25   # needs API keys; costs money
uv run python evals/fresh/label.py prepare      # audit every answer, fetching the cited pages
uv run python evals/fresh/label.py label        # s/p/u/x per citation, resumable
uv run python evals/fresh/label.py scoreboard   # per-provider table + upheld's agreement with the labels
```

The output, `scoreboard.md`, answers both "how often do each tool's citations hold up?" and "how often does upheld agree with a person?", on 2026 answers with real fetching and retrieval.

`upheld eval` scores any verifier against a JSONL of hand labels (`claim`, `evidence`, `label`, and ideally the full `answer`), with a threshold sweep. `evals/smoke.jsonl` is 8 rows that check the command works; it is not a benchmark.

`evals/retrieval_check.py` checks retrieval: for 10 paraphrased claims against the live Eiffel Tower Wikipedia article, it reports where the supporting passage ranks. BM25 puts it in the top 3 for 9/10 claims, hybrid for 10/10. The claims are hand-written, so this is a regression check, not a benchmark.

## Known limitations

- **One-step inferences fail.** In `examples/glp1.json` the source reports "the mean change in body weight ... was -14.9%" and the answer says "an average weight loss of 14.9%". MiniCheck scores that 0.08 and the claim is marked unsupported, as is the matching placebo claim. Likewise `examples/eiffel.md` marks the true claim "intended to stand for only 20 years" unsupported (0.46): retrieval finds "slated for dismantling in 1909", but nothing connects that to 20 years. An LLM judge for uncertain claims is the planned fix.
- **Wrong-party claims slip through** about two times in three when the wrong name is also in the source (see [Edited claims](#edited-claims)).
- **ExpertQA-style claims** (long, technical, expert-written) score 57.8 macro-F1, so expect more mistakes on specialist content.
- **Entity check is a heuristic** (capitalized phrases + word frequency), not NER. It false-alarms on names the source writes differently and misses lowercase entities.
- **Speed.** The ensemble takes roughly 0.3–1 s per claim per source on an Apple M5 Pro and is several times slower on CPU. MiniCheck dominates. `--verifier lexical` is instant but much weaker.
- **No PDF support yet**; PDF sources come back `unverifiable`.
- **Sentence-level claims.** A sentence with two facts is judged as one unit.
- Some sites reject generic user agents. The default names this repo; set `UPHELD_USER_AGENT` to your own project URL if you deploy upheld (Wikipedia returns 403 instead of 404 for missing pages without one).

## Roadmap

**Phase 1: auditor**
- ~~Hybrid retrieval (BM25 + a small embedding model)~~ done
- ~~Benchmark the verifiers on AttributionBench~~ done
- ~~Stronger verifier, threshold calibrated on a held-out split~~ done: MiniCheck + ensemble, 64.4 → 74.4 ID macro-F1
- ~~Edited-claim tests for each failure type~~ done
- **Run the fresh 2026 benchmark.** The tooling is built; it needs API keys for the four providers and a few hours of labeling.
- **Close the gap on hard claims**: an LLM judge for claims the ensemble is unsure about, or fine-tuning MiniCheck on AttributionBench's train split (the paper's best fine-tuned model reaches 78.5 ID). Targets: ExpertQA, wrong-party swaps, one-step inferences.
- Speed: MiniCheck in bf16, and batching claims across sources
- PDF sources
- Web app and hosted API; browser extension after that

**Phase 2: train a search agent to cite honestly**
- Qwen3-4B + LoRA, GRPO, BM25 over Wikipedia, NQ + HotpotQA
- Baseline outcome-only reward → measure citation faithfulness with this auditor
- Add a faithfulness reward from this verifier; watch for reward hacking (copying, refusals); fix with sentence-level credit or grounding-gated accuracy
