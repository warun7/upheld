# Cross-checking the fresh labels

150 of the 150 sampled citations (stratified by provider and Claude's label, out of 150 labeled) have labels from all three labelers. Each labeler followed labeling-guide.md, blind to the provider, upheld's verdict and the other labels.

- claude: Claude Sonnet 5.5 subagents, reading the passages and fetching the page themselves.
- gpt: gpt-6-luna (Codex CLI, reasoning effort high), given the same passages plus the page text fetched once by crosscheck.py.
- gemini: gemini-4-argon-high (Antigravity CLI), given the same passages plus the page text fetched once by crosscheck.py.

## Agreement

Binary means supported against partial or unsupported, as in the scoreboard, over the citations both labelers could judge.

| Labelers | Same label (4-way) | Cohen's κ (4-way) | Judged by both | Same verdict (binary) | Cohen's κ (binary) |
|---|---|---|---|---|---|
| claude vs gpt | 85% | 0.78 | 133 | 93% | 0.86 |
| claude vs gemini | 86% | 0.79 | 133 | 92% | 0.85 |
| gpt vs gemini | 89% | 0.83 | 139 | 92% | 0.84 |

Where GPT and Gemini give the same binary verdict, how often Claude agrees:

- both say supported: Claude agrees on 55 of 58 (95%); can't judge on 3
- both say not supported (partial or unsupported): Claude agrees on 63 of 70 (90%); can't judge on 3

## Confusion against Claude

Rows are Claude's label, columns gpt's.

| claude \ gpt | supported | partial | unsupported | cant_judge |
|---|---|---|---|---|
| supported | 57 | 9 | 0 | 2 |
| partial | 0 | 49 | 0 | 1 |
| unsupported | 0 | 4 | 14 | 0 |
| cant_judge | 3 | 2 | 1 | 8 |

Rows are Claude's label, columns gemini's.

| claude \ gemini | supported | partial | unsupported | cant_judge |
|---|---|---|---|---|
| supported | 60 | 6 | 0 | 2 |
| partial | 4 | 45 | 0 | 1 |
| unsupported | 0 | 2 | 16 | 0 |
| cant_judge | 3 | 2 | 1 | 8 |

## Scoreboard by labeler

Share of each provider's sampled citations labeled supported. A labeler that favors answers from its own vendor would rank that vendor higher.

| Provider | Citations | claude | gpt | gemini |
|---|---|---|---|---|
| claude | 60 | 47% | 45% | 47% |
| gemini | 60 | 42% | 32% | 40% |
| openai | 29 | 52% | 45% | 48% |
| perplexity | 1 | 0% | 100% | 100% |

## upheld against each labeler

Agreement and macro-F1 of each verifier on the sampled citations with passages, at its AttributionBench dev threshold. Majority is the binary verdict at least two labelers share (139 citations).

| Verifier | claude agree | claude macro-F1 | gpt agree | gpt macro-F1 | gemini agree | gemini macro-F1 | majority agree | majority macro-F1 |
|---|---|---|---|---|---|---|---|---|
| ensemble | 79% | 79.0 | 80% | 79.4 | 77% | 76.8 | 78% | 77.7 |
| ensemble+judge | 84% | 84.1 | 85% | 84.7 | 86% | 85.8 | 85% | 84.8 |
| judge | 88% | 87.8 | 85% | 84.8 | 86% | 85.8 | 87% | 86.8 |
| minicheck | 71% | 70.9 | 70% | 69.3 | 71% | 70.5 | 70% | 69.5 |
| lettuce | 73% | 72.4 | 74% | 72.6 | 71% | 70.2 | 72% | 71.0 |
| lexical | 72% | 71.8 | 75% | 74.0 | 75% | 75.3 | 75% | 74.3 |

## Quotes

Share of supported and partial labels whose quote appears verbatim in the passages or the fetched page (ignoring case, spacing and curly quotes; an ellipsis may join verbatim fragments).

- claude: 110 of 118 (93%)
- gpt: 104 of 124 (84%)
- gemini: 121 of 122 (99%)

Claude read some pages through its own fetcher or another copy of the document, so a quote it found there can be missing from this fetch.
