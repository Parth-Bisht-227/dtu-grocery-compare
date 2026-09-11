from decimal import Decimal

import pytest

import service as service_module
from matching.normalize import parse_quantity
from models import Product, Provider
from providers.base import ProductProvider, ProviderError
from service import ComparisonService


def product(
    provider: Provider,
    title: str,
    quantity: str = "1 ltr",
    price: str = "100",
) -> Product:
    return Product(
        provider=provider,
        title=title,
        quantity_raw=quantity,
        quantity=parse_quantity(quantity),
        price=Decimal(price),
    )


class FakeProvider(ProductProvider):
    def __init__(
        self,
        provider: Provider,
        products: list[Product] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.provider = provider
        self.products = products or []
        self.error = error
        self.calls: list[str] = []

    def search(self, query: str) -> list[Product]:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return list(self.products)


def test_both_providers_succeed_and_matching_output_is_preserved():
    blinkit_product = product(
        Provider.BLINKIT, "Amul Pasteurised Butter", "200 g", "130"
    )
    instamart_product = product(
        Provider.INSTAMART, "Amul Pasteurised Butter", "200 g", "125"
    )
    service = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, [blinkit_product]),
            FakeProvider(Provider.INSTAMART, [instamart_product]),
        ]
    )

    outcome = service.search("Amul butter")

    assert not outcome.errors
    assert outcome.products[Provider.BLINKIT] == [blinkit_product]
    assert outcome.products[Provider.INSTAMART] == [instamart_product]
    assert len(outcome.matches) == 1
    assert outcome.matches[0].blinkit == blinkit_product
    assert outcome.matches[0].instamart == instamart_product


def test_one_provider_failure_does_not_discard_other_results():
    blinkit_product = product(Provider.BLINKIT, "Amul Butter", "200 g")
    blinkit = FakeProvider(Provider.BLINKIT, [blinkit_product])
    instamart = FakeProvider(
        Provider.INSTAMART,
        error=ProviderError("temporary Instamart failure"),
    )

    outcome = ComparisonService([blinkit, instamart]).search("butter")

    assert outcome.products[Provider.BLINKIT] == [blinkit_product]
    assert outcome.products[Provider.INSTAMART] == []
    assert outcome.errors == {
        Provider.INSTAMART: "temporary Instamart failure"
    }
    assert outcome.unmatched[Provider.BLINKIT] == [blinkit_product]


def test_successful_results_are_reused_from_case_insensitive_cache():
    blinkit = FakeProvider(
        Provider.BLINKIT,
        [product(Provider.BLINKIT, "Coca-Cola Soft Drink", "750 ml")],
    )
    instamart = FakeProvider(Provider.INSTAMART)
    service = ComparisonService([blinkit, instamart])

    service.search("  Coke  ")
    service.search("cOkE")

    assert blinkit.calls == ["Coke"]
    assert instamart.calls == ["Coke"]


def test_error_cache_expires_before_success_cache(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(service_module.time, "monotonic", lambda: clock[0])
    blinkit = FakeProvider(
        Provider.BLINKIT,
        [product(Provider.BLINKIT, "Amul Butter", "200 g")],
    )
    instamart = FakeProvider(
        Provider.INSTAMART,
        error=ProviderError("temporary failure"),
    )
    service = ComparisonService(
        [blinkit, instamart],
        cache_ttl_seconds=180,
        error_ttl_seconds=30,
    )

    service.search("butter")
    clock[0] = 110.0
    service.search("butter")
    clock[0] = 131.0
    service.search("butter")

    assert len(blinkit.calls) == 1
    assert len(instamart.calls) == 2


@pytest.mark.parametrize("query", ["   ", "x" * 101])
def test_invalid_query_is_rejected_before_calling_providers(query):
    provider = FakeProvider(Provider.BLINKIT)
    service = ComparisonService([provider])

    with pytest.raises(ValueError):
        service.search(query)

    assert not provider.calls


def test_matches_are_ranked_by_query_relevance_without_changing_raw_order():
    blinkit_orange = product(
        Provider.BLINKIT, "Real Fruit Power Orange Juice"
    )
    blinkit_mixed = product(
        Provider.BLINKIT, "Real Fruit Power Mixed Fruit Juice"
    )
    instamart_orange = product(
        Provider.INSTAMART, "Real Fruit Power Orange Juice"
    )
    instamart_mixed = product(
        Provider.INSTAMART, "Real Fruit Power Mixed Fruit Juice"
    )
    service = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, [blinkit_orange, blinkit_mixed]),
            FakeProvider(Provider.INSTAMART, [instamart_orange, instamart_mixed]),
        ]
    )

    outcome = service.search("Real Mixed Fruit Juice 1L")

    assert outcome.products[Provider.BLINKIT][0] == blinkit_orange
    assert outcome.matches[0].blinkit == blinkit_mixed
    assert outcome.matches[1].blinkit == blinkit_orange


def test_unmatched_products_are_ranked_by_query_relevance():
    orange = product(Provider.BLINKIT, "Real Fruit Power Orange Juice")
    mixed = product(Provider.BLINKIT, "Real Fruit Power Mixed Fruit Juice")
    service = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, [orange, mixed]),
            FakeProvider(Provider.INSTAMART),
        ]
    )

    outcome = service.search("Real Mixed Fruit Juice")

    assert outcome.unmatched[Provider.BLINKIT] == [mixed, orange]
    assert outcome.products[Provider.BLINKIT] == [orange, mixed]
