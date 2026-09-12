"""Comparison orchestration, provider isolation, and short-lived caching."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from matching.matcher import match_products
from models import Product, Provider, SearchOutcome
from providers.base import ProductProvider
from relevance import (
    build_relevance_context,
    filter_and_rank_matches,
    filter_and_rank_products,
)


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    products: list[Product] | None = None
    error: str | None = None


class ComparisonService:
    def __init__(
        self,
        providers: list[ProductProvider],
        *,
        cache_ttl_seconds: int = 180,
        error_ttl_seconds: int = 30,
    ) -> None:
        self.providers = providers
        self.cache_ttl_seconds = cache_ttl_seconds
        self.error_ttl_seconds = error_ttl_seconds
        self._cache: dict[tuple[Provider, str], _CacheEntry] = {}
        self._cache_lock = threading.Lock()

    def _cached(self, key: tuple[Provider, str]) -> _CacheEntry | None:
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None or entry.expires_at <= time.monotonic():
                self._cache.pop(key, None)
                return None
            return entry

    def _store(self, key: tuple[Provider, str], entry: _CacheEntry) -> None:
        with self._cache_lock:
            self._cache[key] = entry

    def search(self, query: str) -> SearchOutcome:
        clean_query = " ".join(query.split())
        if not clean_query:
            raise ValueError("Enter a product to search for.")
        if len(clean_query) > 100:
            raise ValueError("Keep the search query under 100 characters.")

        cache_query = clean_query.casefold()
        products: dict[Provider, list[Product]] = {
            provider.provider: [] for provider in self.providers
        }
        errors: dict[Provider, str] = {}
        pending: dict[object, ProductProvider] = {}

        with ThreadPoolExecutor(max_workers=len(self.providers)) as executor:
            for provider in self.providers:
                key = (provider.provider, cache_query)
                entry = self._cached(key)
                if entry is not None:
                    if entry.error:
                        errors[provider.provider] = entry.error
                    else:
                        products[provider.provider] = list(entry.products or [])
                    continue
                pending[executor.submit(provider.search, clean_query)] = provider

            for future in as_completed(pending):
                provider = pending[future]
                key = (provider.provider, cache_query)
                try:
                    provider_products = future.result()
                    products[provider.provider] = provider_products
                    self._store(
                        key,
                        _CacheEntry(
                            expires_at=time.monotonic() + self.cache_ttl_seconds,
                            products=provider_products,
                        ),
                    )
                except Exception as error:
                    message = str(error) or error.__class__.__name__
                    errors[provider.provider] = message
                    self._store(
                        key,
                        _CacheEntry(
                            expires_at=time.monotonic() + self.error_ttl_seconds,
                            error=message,
                        ),
                    )

        matches, unmatched = match_products(
            products.get(Provider.BLINKIT, []),
            products.get(Provider.INSTAMART, []),
        )
        relevance = build_relevance_context(
            clean_query,
            [
                product
                for provider_products in products.values()
                for product in provider_products
            ],
        )
        matches = filter_and_rank_matches(relevance, matches)
        unmatched = {
            provider: filter_and_rank_products(relevance, provider_products)
            for provider, provider_products in unmatched.items()
        }
        return SearchOutcome(
            query=clean_query,
            products=products,
            errors=errors,
            matches=matches,
            unmatched=unmatched,
        )
