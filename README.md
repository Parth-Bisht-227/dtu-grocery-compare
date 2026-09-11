# DTU Grocery Price Compare

A small local web app that searches Blinkit and Instamart for delivery to Delhi Technological University (DTU), normalizes the listings, and shows only conservative like-for-like price comparisons.

## Architecture

`Streamlit UI -> ComparisonService -> Blinkit/Instamart Playwright adapters -> Product[] -> deterministic matcher`

Each provider owns its website-specific selectors. Everything after extraction uses the same Pydantic `Product` model. The service runs providers independently, so one failure still leaves the other provider's results usable, and caches each `(provider, query, DTU)` result for three minutes.

## Fresh-machine setup

Prerequisites: Python 3.11 and a working desktop session. No account or login is needed.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

macOS/Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`), search for an item such as `Maggi`, and wait for both providers.

On the first search, each adapter selects DTU through the provider's normal public desktop location UI and stores browser location state under `.state/`. Blinkit currently blocks the tested headless Chromium session, so its conservative default is a short-lived visible browser window. Do not close that window while a search is running. Instamart runs headlessly. To test Blinkit headless mode explicitly, set `BLINKIT_HEADLESS=true`; it may be rejected by the site.

## Tests

```powershell
pytest -q
```

The tests cover quantity/unit/pack normalization, conservative SKU matching, one-to-one pairing, and provider card-text parsing. Live browser checks are intentionally not part of the deterministic test suite because inventory, markup, latency, and anti-automation behavior change independently of this code.

## Expected behavior and limitations

- Only DTU (Bawana Road campus) is in scope; there is no user-facing location selector.
- Results are read from visible rendered desktop DOM. No private APIs, authentication bypass, CAPTCHA bypass, or product-detail pages are used.
- Different sizes, units, pack structures, brands, or recognized variants are not compared as the same SKU.
- Marketing copy, brand aliases (`Coke` vs `Coca-Cola`), bundles, and omitted variant words can cause conservative false negatives.
- Provider DOM changes, timeouts, or blocks are reported per provider instead of crashing the whole result.
- This is a local, single-user assessment MVP and should not be publicly deployed.

See [DESIGN.md](DESIGN.md) for the one-page design note and [DECISIONS.md](DECISIONS.md) for interview-ready reasoning.

