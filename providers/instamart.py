"""Instamart adapter using stable test IDs from the rendered desktop UI."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from models import Product, Provider
from providers.base import ProductProvider, ProviderError, environment_flag
from providers.parsing import parse_instamart_card


class InstamartProvider(ProductProvider):
    provider = Provider.INSTAMART
    home_url = "https://instamart.in/"
    location_name = "Delhi Technological University"

    def __init__(
        self,
        *,
        state_path: Path = Path(".state/instamart.json"),
        headless: bool | None = None,
        max_results: int = 30,
    ) -> None:
        self.state_path = state_path
        self.headless = (
            environment_flag("INSTAMART_HEADLESS", True)
            if headless is None
            else headless
        )
        self.max_results = max_results

    def _new_context(self, browser):
        kwargs: dict[str, object] = {"viewport": {"width": 1500, "height": 1000}}
        if self.state_path.exists():
            kwargs["storage_state"] = str(self.state_path)
        return browser.new_context(**kwargs)

    def _configure_dtu_if_needed(self, page, context) -> None:
        location_search = page.get_by_test_id("search-location")
        if not location_search.is_visible():
            return

        location_search.click()
        location_input = page.get_by_placeholder("Search for area, street name…")
        location_input.wait_for(state="visible", timeout=15_000)
        location_input.fill(self.location_name)

        suggestions = page.get_by_text(self.location_name, exact=True)
        suggestions.first.wait_for(state="visible", timeout=20_000)
        # The first exact result was verified to resolve to the DTU Bawana Road campus.
        suggestions.first.click()

        confirm = page.get_by_role("button", name="Confirm Location")
        confirm.wait_for(state="visible", timeout=20_000)
        confirm.click()
        confirm.wait_for(state="hidden", timeout=20_000)
        page.get_by_test_id("search-container").wait_for(state="visible", timeout=30_000)

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(self.state_path))

    def search(self, query: str) -> list[Product]:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.headless)
                context = self._new_context(browser)
                page = context.new_page()
                try:
                    page.goto(self.home_url, wait_until="domcontentloaded", timeout=60_000)
                    page.locator("body").wait_for(state="visible", timeout=30_000)
                    self._configure_dtu_if_needed(page, context)

                    search_button = page.get_by_test_id("search-container")
                    search_button.wait_for(state="visible", timeout=30_000)
                    search_button.click()

                    search_input = page.locator("input:visible").first
                    search_input.wait_for(state="visible", timeout=20_000)
                    search_input.fill(query)
                    search_input.press("Enter")

                    cards = page.get_by_test_id("item-collection-card-full")
                    cards.first.wait_for(state="visible", timeout=30_000)
                    products: list[Product] = []
                    for index in range(min(cards.count(), self.max_results)):
                        card = cards.nth(index)
                        image = card.locator("img").first
                        product = parse_instamart_card(
                            card.inner_text(),
                            image_alt=image.get_attribute("alt"),
                            image_url=image.get_attribute("src"),
                        )
                        if product is not None:
                            products.append(product)
                    if not products:
                        raise ProviderError("Instamart returned no parseable product cards.")
                    return products
                finally:
                    context.close()
                    browser.close()
        except ProviderError:
            raise
        except PlaywrightTimeoutError as error:
            raise ProviderError("Instamart timed out while loading its public UI.") from error
        except Exception as error:
            raise ProviderError(f"Instamart browser failure: {error}") from error

