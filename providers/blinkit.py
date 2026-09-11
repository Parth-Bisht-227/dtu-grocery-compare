"""Blinkit adapter using only the public rendered desktop UI."""

from __future__ import annotations

import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from models import Product, Provider
from providers.base import ProductProvider, ProviderError, environment_flag
from providers.parsing import parse_blinkit_card


class BlinkitProvider(ProductProvider):
    provider = Provider.BLINKIT
    home_url = "https://blinkit.com/"
    location_name = "Delhi Technological University"

    def __init__(
        self,
        *,
        headless: bool | None = None,
        max_results: int = 30,
    ) -> None:
        # Headed Chromium is the conservative default: current Blinkit blocks the
        # same browser in headless mode, while its normal desktop UI works headed.
        self.headless = (
            environment_flag("BLINKIT_HEADLESS", False) if headless is None else headless
        )
        self.max_results = max_results
        self.selected_location: str | None = None

    def _select_dtu(self, page) -> None:
        location_input = page.get_by_placeholder("search delivery location", exact=True)
        location_input.wait_for(state="visible", timeout=20_000)
        location_input.fill(self.location_name)
        suggestions = page.get_by_text(self.location_name, exact=True)
        suggestions.first.wait_for(state="visible", timeout=20_000)

        chosen = None
        chosen_address = None
        for index in range(suggestions.count()):
            candidate = suggestions.nth(index)
            parent_text = candidate.locator("xpath=..").inner_text()
            if "Bawana Road" in parent_text and "Rohini" in parent_text:
                chosen = candidate
                chosen_address = " ".join(parent_text.split())
                break
        if chosen is None or chosen_address is None:
            raise ProviderError("Blinkit did not return the expected DTU Bawana Road result.")

        chosen.click()
        location_input.wait_for(state="hidden", timeout=30_000)

        preparing = page.get_by_text("Preparing your experience...", exact=True)
        if preparing.count():
            preparing.wait_for(state="hidden", timeout=30_000)

        page.locator('a[href="/s/"]').wait_for(state="visible", timeout=30_000)
        self.selected_location = chosen_address

    @staticmethod
    def _product_image(card) -> str | None:
        sources = card.locator("img").evaluate_all(
            "images => images.map(image => image.currentSrc || image.src).filter(Boolean)"
        )
        return next(
            (
                source
                for source in sources
                if "/eta-icons/" not in source and "ad_without_bg" not in source
            ),
            None,
        )

    def search(self, query: str) -> list[Product]:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.headless)
                context = browser.new_context(viewport={"width": 1500, "height": 1000})
                page = context.new_page()
                try:
                    page.goto(self.home_url, wait_until="domcontentloaded", timeout=60_000)
                    page.locator("body").wait_for(state="visible", timeout=30_000)
                    body_head = page.locator("body").inner_text()[:1_000].casefold()
                    if "access denied" in body_head or "you have been blocked" in body_head:
                        raise ProviderError(
                            "Blinkit blocked this browser session; keep BLINKIT_HEADLESS=false "
                            "and retry after a short cooldown."
                        )

                    self._select_dtu(page)
                    search_link = page.locator('a[href="/s/"]').first
                    search_link.wait_for(state="visible", timeout=30_000)
                    search_link.click()

                    search_input = page.locator("input:visible").first
                    search_input.wait_for(state="visible", timeout=20_000)
                    search_input.fill(query)
                    search_input.press("Enter")

                    cards = page.locator('div[role="button"][id]').filter(has_text="₹")
                    cards.first.wait_for(state="visible", timeout=30_000)
                    products: list[Product] = []
                    for index in range(min(cards.count(), self.max_results)):
                        card = cards.nth(index)
                        product_id = card.get_attribute("id")
                        if not product_id or not re.fullmatch(r"\d+", product_id):
                            continue
                        product = parse_blinkit_card(
                            card.inner_text(),
                            product_id=product_id,
                            image_url=self._product_image(card),
                        )
                        if product is not None:
                            products.append(product)
                    if not products:
                        raise ProviderError("Blinkit returned no parseable product cards.")
                    return products
                finally:
                    context.close()
                    browser.close()
        except ProviderError:
            raise
        except PlaywrightTimeoutError as error:
            raise ProviderError("Blinkit timed out while loading its public UI.") from error
        except Exception as error:
            raise ProviderError(f"Blinkit browser failure: {error}") from error
