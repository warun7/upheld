# Fresh benchmark scoreboard

How often each AI search tool's citations back the claim they're attached to. Labeled 2 by hand and 639 by Claude Sonnet 5.5 subagents blinded to the provider (see labeling-guide.md).

| Provider | Model | Citations labeled | Supported | Partial | Unsupported | Can't judge | Dead links (all citations) |
|---|---|---|---|---|---|---|---|
| claude | claude-sonnet-5-5 (Claude Code subagent, WebSearch tool) | 255 | 47% | 25% | 17% | 11% | 6/255 |
| gemini | gemini-3.8-flash-medium (Antigravity CLI, search_web tool) | 257 | 41% | 45% | 7% | 7% | 0/257 |
| openai | gpt-6-luna (Codex CLI, web search) | 125 | 51% | 28% | 14% | 6% | 1/125 |
| perplexity | perplexity/sonar-pro (OpenRouter, Sonar's own search) | 4 | 50% | 0% | 0% | 50% | 0/4 |

upheld vs these labels (476 citations it could read): agreement 75%, precision 0.70 and recall 0.91 on unsupported citations.

Claude's labels match the hand labels on 1 of 2 citations labeled both ways.

GPT and Gemini relabeled a sample of these citations to check Claude's labels: see crosscheck.md.
