# Engineering Decision Log (interview notes)

## Why Playwright, not requests + BeautifulSoup?

The prices are location-dependent and the sites render/interact through JavaScript. `requests` retrieves HTTP responses but does not execute that browser behavior; BeautifulSoup parses static HTML. Playwright drives the same public desktop UI a user sees and lets us wait for actual rendered cards.

## Why Playwright, not Selenium?

Both are viable. Playwright was already installed and proved against Blinkit. Its browser contexts, auto-waiting locators, and `storage_state` API make this particular stateful UI task concise. This is a delivery choice, not a claim that Selenium cannot solve it.

## DOM, locators, and selector durability

The DOM is the browser's live tree of page elements. A locator is a query that finds elements in that tree and waits/retries around actions. Instamart exposes `data-testid="item-collection-card-full"`; Blinkit cards have a runtime numeric ID plus `role="button"`. We use those card boundaries and parse their visible text instead of depending on generated CSS classes. DOM changes can still break any scraper, so provider failures are isolated and selectors are kept in provider modules.

## Browser context, cookies, and storage state

A browser context is an isolated browser session—roughly an incognito profile—with its own cookies and local/session storage. Location choices are commonly stored there. Playwright `storage_state` serializes cookies and localStorage so a DTU-configured session can be reused without repeating the location flow. The app creates that state through the normal UI on a fresh machine, stores it only in ignored `.state/` files, and never logs in.

## Why normalize before matching?

Providers disagree on spelling and units. Converting `0.5 kg` and `500gm` to a shared `500 g` representation lets matching enforce real SKU constraints before considering wording. Explicit packs remain explicit because `4 x 70 g` and one `280 g` package can have the same total weight but be different sellable units.

## Why provider adapters?

Marketplace markup changes independently. Each adapter owns navigation and extraction, then emits the same `Product` model. Matching, caching, tests, and UI therefore do not change when one provider changes its DOM.

## Why not only fuzzy-match titles, or use an LLM?

Fuzzy similarity measures wording, not identity: “Maggi 280 g” and “Maggi 420 g” can look nearly identical while being different SKUs. Hard quantity/brand/variant gates run first. An LLM would add latency, cost, nondeterminism, and another failure mode to a small structured problem. It could later help classify ambiguous unmatched pairs, but should not silently decide price equivalence.

## Why cache and isolate failures?

Prices do not need a new marketplace request on every UI rerun. A three-minute success TTL limits traffic while staying reasonably fresh; a short failure TTL avoids hammering an unhealthy provider. Independent provider futures mean one timeout becomes a warning, not a blank app or HTTP 500.

## Deadline shortcuts

The MVP launches a browser per uncached provider search, targets one location, uses an in-memory cache, and has a hand-built variant vocabulary. These are explicit single-user/local-assessment trade-offs. Production would use background collectors, persistent SKU mappings, shared storage/cache, rate limits, retries, monitoring, and per-location inventory keys.
