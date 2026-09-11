"""Instamart adapter using the rendered public desktop UI."""

from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from models import Product, Provider
from providers.base import ProductProvider, ProviderError, environment_flag
from providers.parsing import parse_instamart_card


class InstamartProvider(ProductProvider):
    provider = Provider.INSTAMART
    home_url = "https://instamart.in/"
    location_name = "Delhi Technological University"
    expected_address_terms = (
        "Bawana",
        "Delhi Technological University",
        "Rohini",
        "110042",
    )

    def __init__(
        self,
        *,
        headless: bool | None = None,
        max_results: int = 30,
    ) -> None:
        self.headless = (
            environment_flag("INSTAMART_HEADLESS", True)
            if headless is None
            else headless
        )
        self.max_results = max_results
        self.resolved_address: str | None = None

    def _configure_dtu(self, page) -> None:
        location_search = page.get_by_test_id("search-location")
        location_search.wait_for(state="visible", timeout=20_000)
        location_search.click()

        location_input = page.get_by_placeholder(
            "Search for area, street name…", exact=True
        )
        location_input.wait_for(state="visible", timeout=15_000)
        location_input.fill(self.location_name)

        # The first exact DTU result is the main Bawana Road campus. The more
        # verbose Rohini result resolves differently in Instamart's map flow.
        dtu_result = page.get_by_text(self.location_name, exact=True).first
        dtu_result.wait_for(state="visible", timeout=20_000)
        dtu_result.click()

        confirm = page.get_by_role("button", name="Confirm Location")
        confirm.wait_for(state="visible", timeout=20_000)
        confirmation_panel = confirm.locator(
            "xpath=ancestor::div[.//*[normalize-space()='SELECT DELIVERY LOCATION']][1]"
        )
        panel_lines = [
            line.strip()
            for line in confirmation_panel.inner_text().splitlines()
            if line.strip()
        ]
        panel_text = " ".join(panel_lines)
        if not all(
            term.casefold() in panel_text.casefold()
            for term in self.expected_address_terms
        ):
            raise ProviderError(
                "Instamart did not resolve the selected result to the DTU Bawana "
                "Road address."
            )

        confirm.scroll_into_view_if_needed()
        confirm.click()
        confirm.wait_for(state="hidden", timeout=20_000)
        confirmed_address = page.get_by_test_id("address-line")
        confirmed_address.wait_for(state="visible", timeout=30_000)
        confirmed_address_text = " ".join(confirmed_address.inner_text().split())
        if (
            confirmed_address_text
            and self.location_name.casefold() not in confirmed_address_text.casefold()
        ):
            raise ProviderError(
                "Instamart's confirmed location no longer refers to DTU."
            )
        if confirmed_address_text:
            self.resolved_address = confirmed_address_text
        page.get_by_test_id("search-container").wait_for(state="visible", timeout=30_000)

    def search(self, query: str) -> list[Product]:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    viewport={"width": 1500, "height": 1000}
                )
                page = context.new_page()
                try:
                    page.goto(self.home_url, wait_until="domcontentloaded", timeout=60_000)
                    page.locator("body").wait_for(state="visible", timeout=30_000)
                    self._configure_dtu(page)

                    search_button = page.get_by_test_id("search-container")
                    search_button.wait_for(state="visible", timeout=30_000)
                    search_button.click()

                    search_input = page.get_by_test_id(
                        "search-page-header-search-bar-input"
                    )
                    search_input.wait_for(state="visible", timeout=20_000)
                    search_input.fill(query)
                    search_input.press("Enter")

                    cards = page.get_by_test_id("item-collection-card-full")
                    cards.first.wait_for(state="visible", timeout=30_000)
                    products: list[Product] = []
                    for index in range(min(cards.count(), self.max_results)):
                        card = cards.nth(index)
                        # The test ID marks the title/image section; its parent is
                        # the complete listing containing quantity and prices.
                        listing = card.locator("xpath=..")
                        image = card.locator("img").first
                        product = parse_instamart_card(
                            listing.inner_text(),
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
