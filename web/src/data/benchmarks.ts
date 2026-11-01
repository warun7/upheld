// Numbers copied from evals/results/attributionbench.json, evals/results/perturbations-*.json
// and the AttributionBench paper (Li et al., 2024). Update them together with the README.

export type Metric = "id" | "ood" | "ExpertQA" | "Stanford-GenSearch";

export interface BenchSystem {
  name: string;
  detail: string;
  group: "upheld" | "paper";
  isDefault?: boolean;
  fit: string;
  scores: Partial<Record<Metric, number>>;
}

export const METRICS: { id: Metric; label: string; note: string }[] = [
  { id: "id", label: "In-distribution", note: "Average of ExpertQA, Stanford-GenSearch, AttributedQA and LFQA" },
  { id: "ood", label: "Out-of-distribution", note: "Average of BEGIN, AttrScore-GenSearch and HAGRID" },
  { id: "ExpertQA", label: "ExpertQA", note: "Expert-written claims against long technical evidence. The hardest subset." },
  { id: "Stanford-GenSearch", label: "Stanford-GenSearch", note: "Real answers from Bing Chat, Perplexity, YouChat and NeevaAI" },
];

export const SYSTEMS: BenchSystem[] = [
  {
    name: "upheld ensemble + judge",
    detail: "Adds the Granite Guardian 3.3 8B judge, opt-in",
    group: "upheld",
    fit: "5 numbers fit on 2,000 train rows",
    scores: { id: 76.7, ood: 82.3, ExpertQA: 59.3, "Stanford-GenSearch": 78.6 },
  },
  {
    name: "upheld ensemble",
    detail: "MiniCheck + word overlap + LettuceDetect, the default",
    group: "upheld",
    isDefault: true,
    fit: "4 numbers fit on 2,000 train rows",
    scores: { id: 74.4, ood: 83.1, ExpertQA: 57.8, "Stanford-GenSearch": 71.8 },
  },
  {
    name: "upheld ensemble + entity check",
    detail: "As shipped: adds the wrong_entity verdict",
    group: "upheld",
    fit: "same",
    scores: { id: 72.2, ood: 80.9, ExpertQA: 55.2, "Stanford-GenSearch": 69.5 },
  },
  {
    name: "upheld judge",
    detail: "Granite Guardian 3.3 8B alone, run with llama.cpp",
    group: "upheld",
    fit: "threshold only",
    scores: { id: 74.2, ood: 80.3, ExpertQA: 59.1, "Stanford-GenSearch": 77.3 },
  },
  {
    name: "upheld minicheck",
    detail: "MiniCheck-Flan-T5-Large alone, 770M",
    group: "upheld",
    fit: "threshold only",
    scores: { id: 73.9, ood: 79.3, ExpertQA: 58.9, "Stanford-GenSearch": 71.5 },
  },
  {
    name: "upheld lettuce",
    detail: "LettuceDetect-base alone, 150M",
    group: "upheld",
    fit: "threshold only",
    scores: { id: 67.3, ood: 74.1, ExpertQA: 57.8, "Stanford-GenSearch": 68.3 },
  },
  {
    name: "upheld lexical",
    detail: "Word overlap with exact number matching",
    group: "upheld",
    fit: "threshold only",
    scores: { id: 67.6, ood: 81.7, ExpertQA: 53.2, "Stanford-GenSearch": 68.6 },
  },
  {
    name: "GPT-4 + chain of thought",
    detail: "Zero-shot, from the paper",
    group: "paper",
    fit: "none",
    scores: { id: 73.3, ood: 78.9, ExpertQA: 59.2, "Stanford-GenSearch": 71.7 },
  },
  {
    name: "FLAN-UL2 (20B)",
    detail: "Zero-shot, from the paper",
    group: "paper",
    fit: "none",
    scores: { id: 73.6, ood: 81.3 },
  },
  {
    name: "T5-XXL-TRUE (11B NLI)",
    detail: "Zero-shot, from the paper",
    group: "paper",
    fit: "none",
    scores: { id: 72.2, ood: 80.5, ExpertQA: 54.5, "Stanford-GenSearch": 68.5 },
  },
  {
    name: "Best fine-tuned model",
    detail: "Best per column in the paper, fully fine-tuned",
    group: "paper",
    fit: "fully fine-tuned",
    scores: { id: 78.5, ood: 84.2, ExpertQA: 61.8, "Stanford-GenSearch": 82.8 },
  },
];

// Every subset for every upheld verifier (macro-F1, test split, dev-calibrated threshold).
export const SUBSETS = {
  id: ["ExpertQA", "Stanford-GenSearch", "AttributedQA", "LFQA"],
  ood: ["BEGIN", "AttrScore-GenSearch", "HAGRID"],
} as const;

export const SUBSET_TABLE: { name: string; threshold: number; id: Record<string, number>; ood: Record<string, number> }[] = [
  {
    name: "ensemble + judge",
    threshold: 0.48,
    id: { AttributedQA: 84.3, ExpertQA: 59.3, LFQA: 84.5, "Stanford-GenSearch": 78.6, avg: 76.7 },
    ood: { "AttrScore-GenSearch": 80.3, BEGIN: 86.6, HAGRID: 80.1, avg: 82.3 },
  },
  {
    name: "ensemble + judge + entity",
    threshold: 0.47,
    id: { AttributedQA: 82.2, ExpertQA: 57.8, LFQA: 83.9, "Stanford-GenSearch": 75.5, avg: 74.8 },
    ood: { "AttrScore-GenSearch": 77.5, BEGIN: 87.1, HAGRID: 78.4, avg: 81.0 },
  },
  {
    name: "ensemble",
    threshold: 0.5,
    id: { AttributedQA: 82.9, ExpertQA: 57.8, LFQA: 85.0, "Stanford-GenSearch": 71.8, avg: 74.4 },
    ood: { "AttrScore-GenSearch": 79.0, BEGIN: 90.8, HAGRID: 79.6, avg: 83.1 },
  },
  {
    name: "ensemble + entity",
    threshold: 0.5,
    id: { AttributedQA: 80.4, ExpertQA: 55.2, LFQA: 83.8, "Stanford-GenSearch": 69.5, avg: 72.2 },
    ood: { "AttrScore-GenSearch": 74.0, BEGIN: 90.1, HAGRID: 78.5, avg: 80.9 },
  },
  {
    name: "judge",
    threshold: 0.06,
    id: { AttributedQA: 81.7, ExpertQA: 59.1, LFQA: 78.6, "Stanford-GenSearch": 77.3, avg: 74.2 },
    ood: { "AttrScore-GenSearch": 80.0, BEGIN: 83.7, HAGRID: 77.2, avg: 80.3 },
  },
  {
    name: "judge + entity",
    threshold: 0.06,
    id: { AttributedQA: 80.0, ExpertQA: 57.3, LFQA: 78.0, "Stanford-GenSearch": 74.8, avg: 72.5 },
    ood: { "AttrScore-GenSearch": 75.8, BEGIN: 84.3, HAGRID: 78.0, avg: 79.4 },
  },
  {
    name: "minicheck",
    threshold: 0.23,
    id: { AttributedQA: 81.2, ExpertQA: 58.9, LFQA: 83.9, "Stanford-GenSearch": 71.5, avg: 73.9 },
    ood: { "AttrScore-GenSearch": 77.9, BEGIN: 84.3, HAGRID: 75.7, avg: 79.3 },
  },
  {
    name: "minicheck + entity",
    threshold: 0.23,
    id: { AttributedQA: 78.7, ExpertQA: 56.8, LFQA: 82.7, "Stanford-GenSearch": 68.6, avg: 71.7 },
    ood: { "AttrScore-GenSearch": 74.2, BEGIN: 84.1, HAGRID: 76.4, avg: 78.2 },
  },
  {
    name: "lettuce",
    threshold: 0.88,
    id: { AttributedQA: 72.1, ExpertQA: 57.8, LFQA: 70.9, "Stanford-GenSearch": 68.3, avg: 67.3 },
    ood: { "AttrScore-GenSearch": 67.2, BEGIN: 79.8, HAGRID: 75.4, avg: 74.1 },
  },
  {
    name: "lettuce + entity",
    threshold: 0.78,
    id: { AttributedQA: 73.9, ExpertQA: 55.8, LFQA: 69.9, "Stanford-GenSearch": 66.6, avg: 66.5 },
    ood: { "AttrScore-GenSearch": 72.7, BEGIN: 78.7, HAGRID: 76.5, avg: 76.0 },
  },
  {
    name: "lexical",
    threshold: 0.56,
    id: { AttributedQA: 67.8, ExpertQA: 53.2, LFQA: 80.8, "Stanford-GenSearch": 68.6, avg: 67.6 },
    ood: { "AttrScore-GenSearch": 76.5, BEGIN: 89.2, HAGRID: 79.4, avg: 81.7 },
  },
  {
    name: "lexical + entity",
    threshold: 0.56,
    id: { AttributedQA: 73.1, ExpertQA: 51.9, LFQA: 80.2, "Stanford-GenSearch": 68.7, avg: 68.5 },
    ood: { "AttrScore-GenSearch": 74.4, BEGIN: 89.0, HAGRID: 77.8, avg: 80.4 },
  },
];

// Edited claims: catch rates count only claims whose unedited version passes.
export const EDITS = [
  {
    id: "wrong_number",
    title: "Wrong number",
    n: 82,
    headline: "100%",
    caption: "caught",
    sub: "Every number in a claim has to appear in the evidence.",
    before: "They run for approximately 670 km in a south-west direction",
    after: "They run for approximately 402 km in a south-west direction",
    changed: ["670", "402"],
    tone: "good" as const,
  },
  {
    id: "wrong_entity_absent",
    title: "A name the source never mentions",
    n: 150,
    headline: "98%",
    caption: "caught with the entity check",
    sub: "87% from the ensemble alone.",
    before: "Dry ether is used in the Wurtz reaction to ensure that the reaction is free from moisture.",
    after: "Dry ether is used in the Epicureanism reaction to ensure that the reaction is free from moisture.",
    changed: ["Wurtz", "Epicureanism"],
    tone: "good" as const,
  },
  {
    id: "wrong_entity_swap",
    title: "The wrong party, also named in the source",
    n: 150,
    headline: "35%",
    caption: "caught",
    sub: "The weak spot. 64% with the opt-in judge; MiniCheck alone catches 57%.",
    before: "Epicureanism has also managed to adapt and blend with modern secular life",
    after: "Stoicism has also managed to adapt and blend with modern secular life",
    changed: ["Epicureanism", "Stoicism"],
    tone: "weak" as const,
  },
  {
    id: "multi_source",
    title: "Two claims joined, cited [1][2]",
    n: 100,
    headline: "83%",
    caption: "correctly supported by reading both sources",
    sub: "No single source ever passed one on its own.",
    before: "Claim A [1]. Claim B [2].",
    after: "Claim A and claim B [1][2].",
    changed: [],
    tone: "good" as const,
  },
];

export const EDIT_TABLE: {
  verifier: string;
  pass: string;
  wrongNumber: string;
  absent: string;
  absentEntity: string;
  swap: string;
  multi: string;
}[] = [
  { verifier: "ensemble", pass: "73-76%", wrongNumber: "100%", absent: "87%", absentEntity: "98%", swap: "35%", multi: "83%, 0% by one source" },
  { verifier: "ensemble+judge", pass: "73-77%", wrongNumber: "100%", absent: "92%", absentEntity: "97%", swap: "64%", multi: "77%, 0% by one source" },
  { verifier: "judge", pass: "75-80%", wrongNumber: "100%", absent: "95%", absentEntity: "97%", swap: "63%", multi: "78%, 3% by one source" },
  { verifier: "minicheck", pass: "71-74%", wrongNumber: "92%", absent: "90%", absentEntity: "97%", swap: "57%", multi: "68%, 4% by one source" },
  { verifier: "lettuce", pass: "68-72%", wrongNumber: "95%", absent: "82%", absentEntity: "97%", swap: "38%", multi: "86% (59 pairs), 0%" },
  { verifier: "lexical", pass: "76-87%", wrongNumber: "100%", absent: "40%", absentEntity: "97%", swap: "1%", multi: "95%, 6% by one source" },
];

// Fresh 2026 benchmark: counts from evals/fresh/labels-claude.jsonl with the hand labels
// in labels.jsonl on top, as in evals/fresh/scoreboard.md.
export type FreshLabel = "supported" | "partial" | "unsupported" | "cant_judge";

export const FRESH_LABELS: { id: FreshLabel; label: string; note: string }[] = [
  { id: "supported", label: "Supported", note: "The page backs everything the sentence says" },
  { id: "partial", label: "Partial", note: "It backs part of it; a figure, a second fact or a conclusion isn't there" },
  { id: "unsupported", label: "Unsupported", note: "It backs none of it, or says the opposite" },
  { id: "cant_judge", label: "Can't judge", note: "The page blocked automated reading" },
];

export const FRESH_AGENTS: { name: string; model: string; counts: Record<FreshLabel, number>; dead: number }[] = [
  { name: "OpenAI", model: "gpt-6-luna, Codex CLI", counts: { supported: 64, partial: 35, unsupported: 18, cant_judge: 8 }, dead: 1 },
  { name: "Claude", model: "Sonnet 5.5, Claude Code", counts: { supported: 119, partial: 64, unsupported: 43, cant_judge: 29 }, dead: 6 },
  { name: "Gemini", model: "3.8 Flash, Antigravity CLI", counts: { supported: 106, partial: 115, unsupported: 19, cant_judge: 17 }, dead: 0 },
];

// upheld's verdicts against those labels, on the citations whose page it could read. Partial counts as unsupported.
export const FRESH_UPHELD = { read: 476, agreement: 75, recall: 91, precision: 70 };

export const PROBLEM_STATS = [
  {
    value: "39-77%",
    text: "of cited facts were actually in the source, across 14 LLMs writing deep-research reports. Their links worked over 94% of the time.",
    cite: "arXiv 2605.06635",
    href: "https://arxiv.org/abs/2605.06635",
  },
  {
    value: "30.6%",
    text: "of 761,495 AI search citations distort what their source says.",
    cite: "CITETRACE, arXiv 2605.28565",
    href: "https://arxiv.org/abs/2605.28565",
  },
  {
    value: "7.8%",
    text: "of answers from a deployed clinical RAG system cited real evidence about the wrong drug, and passed faithfulness checks.",
    cite: "arXiv 2607.09349",
    href: "https://arxiv.org/abs/2607.09349",
  },
];
