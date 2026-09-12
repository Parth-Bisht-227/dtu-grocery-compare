# Engineering Decision Log

This file records the main implementation choices in compact form. See [Interview_prep.md](Interview_prep.md) for the detailed walkthrough.

## Public browser automation

Both marketplaces depend on JavaScript-rendered, location-specific UI. Playwright drives the same public desktop controls a user sees; `requests` and BeautifulSoup would not execute the location/search flow. Selenium was viable, but Playwright's locators, waits, and contexts made the already-proven flows concise.

## Fresh context instead of saved state

Every uncached provider search creates an isolated context and establishes DTU through the UI. No cookies, `storage_state`, or persistent local profile is shipped. This costs several seconds but gives the evaluator a reproducible fresh-machine flow. Blinkit defaults to headed mode because tested headless sessions were blocked; Instamart defaults to headless.

## Provider adapters and normalized models

Each adapter owns its selectors, location flow, and card extraction, then returns the same frozen Pydantic `Product` model. This keeps website changes out of matching, service, tests, and UI, while Pydantic validates the boundary between messy external text and deterministic logic.

## Structured quantity before title similarity

Quantities are normalized to `g`, `ml`, `pcs`, or `combo`. Equivalent single quantities such as `0.5 kg` and `500 g` can match. Multipack structure remains explicit because `150 g` and `3 x 50 g` are different sellable SKUs. Missing quantities are not guessed.

## Generic conservative SKU matching

There is no brand/flavour dictionary, LLM, or embedding dependency. Titles retain potentially defining words, and tokens receive IDF-like weights from the current combined result set. Symmetric reordered similarity, weighted Dice overlap, and minimum coverage produce a score. A pair must be mutual best, score at least 76, and lead alternatives by eight points on both sides. False negatives are preferred because unmatched listings remain visible, while a false positive can misstate which store is cheaper.

## Separate query relevance

SKU identity and search relevance are different decisions. After matching, a corpus-derived query anchor and weighted token coverage remove unrelated valid matches. When no query token appears in the corpus, the system preserves results rather than introducing hardcoded aliases. One explicit query quantity gates candidates by canonical unit and total; it does not relax exact SKU pack rules.

## Short cache and failure isolation

The service runs independent provider searches concurrently. A three-minute in-memory success cache limits repeated traffic while keeping prices reasonably fresh; failures are cached for 30 seconds. One provider exception becomes a UI warning and does not discard the other provider's results.

## Deliberate MVP omissions

The project fixes location to DTU, launches browsers for uncached searches, stores no history, and has no database, login, deployment, unit-price comparison, or production monitoring. At scale, background collectors would populate timestamped provider/location records, stable product mappings, a database/search index, and shared cache behind a stateless API.
