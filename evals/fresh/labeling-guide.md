# Citation labeling guide

Each item is one claim from an AI search answer and one page the answer cited for it. Decide whether **this page** backs **this claim**. Judge the page only: whether the claim is true, what you already know, and what other sources say do not matter.

## Labels

- `supported`: the page states everything the claim says (paraphrase and small rounding are fine; a well-known alias is fine, e.g. a drug's brand name for its code name).
- `partial`: the page backs some of the claim but not all of it.
- `unsupported`: the page backs none of it, contradicts it, or is about something else.
- `cant_judge`: you cannot read enough of the page (paywall, 404, block page you cannot get past) to judge.

Be strict, the same way for every item:

| Situation | Label |
|---|---|
| A number, date, unit, statistic label or interval differs (claim says 95% CI, page says 96.95% CI) | partial |
| Claim joins two facts and the page has only one | partial |
| Claim adds a cause, comparison or conclusion the page doesn't state | partial |
| Page is about a different drug, trial, company, person or year | unsupported |
| Page says the opposite | unsupported |
| Claim is true, but this page doesn't say it | unsupported |
| Page covers the topic but has none of the claim's specific figures | unsupported |
| Paywalled article whose abstract covers the claim | judge from the abstract |
| Live statistics page that has changed since the answer was written | judge it as it reads now |

## Reading the page

The `passages` are text upheld retrieved from the page. Use them when they settle the claim.

Read the page yourself with WebFetch when:
- there are no passages, or the `source_status` is not `live`;
- the passages are boilerplate, a cookie wall, navigation, or cut off before the relevant part;
- you are about to label a plausible claim `unsupported` or `partial` because something is missing from the passages: check the full page first.

If the cited URL is blocked or gone, you may read **the same document** elsewhere: an archived copy (`https://web.archive.org/web/2026/<url>`), or for a journal article the same paper's abstract on PubMed or the publisher's site (match the title or DOI). You may use WebSearch only to find a copy of the same document. Never judge against a different document. If you cannot read the document at all, label `cant_judge`.

Fetch each page once and label every item that cites it.

## Output

Write a JSON array with one object per input item, in input order, to the output path you were given:

```json
{"id": "...", "label": "supported|partial|unsupported|cant_judge", "quote": "...", "read_from": "passages", "note": "..."}
```

- `quote`: for `supported` or `partial`, the exact words from the page (copied verbatim, at most 300 characters) that back the claim; otherwise an empty string.
- `read_from`: `"passages"` if the passages settled it, otherwise the URL you actually read.
- `note`: at most 20 words, saying what is missing or wrong for `partial` and `unsupported`.

Label every item. Do not create or change any other files.
