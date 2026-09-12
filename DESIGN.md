# Design Note - The Great DTU Grocery Race

The challenge is not simply fetching two prices. Both stores expose location-dependent, inconsistently described listings, so the app must collect comparable DTU data and decide whether two records represent the same sellable product.

## Architecture and choices

```text
User query -> Streamlit UI -> ComparisonService
                                  |
                    +-------------+-------------+
                    |                           |
             BlinkitProvider             InstamartProvider
                Playwright                    Playwright
                    |                           |
                    +-------------+-------------+
                                  |
                         normalized Product[]
                                  |
                         exact-SKU matcher
                                  |
                      query relevance filter
                                  |
                comparisons + other search results
```

For each uncached search, `ComparisonService` calls both provider adapters concurrently. Each launches Playwright in a fresh context, selects the same DTU delivery area through the public desktop UI, searches, and returns normalized Pydantic `Product` records. Provider-specific DOM assumptions stay inside the adapters. Failures are isolated, so one unavailable store does not hide the other's results; short-lived caching limits repeat requests.

This is deliberately an in-process local architecture. Playwright is needed because location and results depend on browser-executed JavaScript; `requests` and BeautifulSoup cannot reliably reproduce that state. Streamlit avoids a separate frontend/API stack. A database, queue, persistent profile, private API, LLM, and embeddings would add complexity without improving this one-location MVP.

## Deciding whether listings are the same SKU

The matcher asks: *are these records the same sellable SKU closely enough for a fair price comparison?* Search relevance alone is not enough.

Results are deduplicated by provider product ID, or by normalized title plus quantity and pack structure. Quantities use canonical units (`0.5 kg = 500 g`, `1 L = 1000 ml`) while preserving multipacks. Quantity is a hard gate: dimensions and total amount must agree; multipacks must also share count and per-item amount. Thus `500 g = 1 x 500 g`, but `150 g != 3 x 50 g`. Missing quantity remains unmatched.

Titles are normalized for case, Unicode, punctuation, embedded quantities, and a tiny filler-word set; SKU-defining terms such as `zero`, `unsalted`, and `classic` remain. There is no product-specific brand or flavour dictionary. Instead, bounded inverse-document-frequency weights make common category words less influential than rarer identifiers. Each quantity-compatible pair receives:

`score = 100 x (0.40R + 0.40D + 0.20C)`

`R` is RapidFuzz token-sort similarity, `D` is weighted symmetric Dice overlap, and `C` is the lower weighted coverage of either title. They tolerate reordered wording, reward distinctive agreement, and penalize subset matches. A pair is accepted only when both products choose each other as best candidate, score at least 76, and lead the runner-up by 8 points on both sides. These are initial calibration values checked against labelled offline cases, not probabilities or universal optima. The policy prefers false negatives: uncertain listings remain separate instead of creating a misleading saving claim.

Search relevance follows SKU matching because a valid pair may still be unrelated to the query. A corpus-derived query anchor and weighted query-token coverage filter both comparisons and unmatched results. An explicit query quantity gates by canonical dimension and total; relevance may accept `400 g = 4 x 100 g`, while exact SKU matching does not.

## Where matching breaks and how it scales

**Where matching breaks.** Equivalents may remain unmatched when quantity or variant data is missing, aliases differ greatly, or several candidates are near-identical. Lexical relevance can retain marketplace noise; DOM/location flows can change; prices and stock are point-in-time. Unit-price comparison across packs is excluded because it needs a second reliable product-family decision.

**Scaling beyond the MVP.** For many locations, location, price, availability, and collection time become stored dimensions refreshed by rate-limited collectors. For many users, browser collection moves into monitored background workers with retries and backoff. Normalized listings and SKU mappings live in a database/search index; a stateless API reads through shared cache and exposes freshness.
