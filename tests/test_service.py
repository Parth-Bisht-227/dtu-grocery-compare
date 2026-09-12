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


def test_irrelevant_matches_are_filtered_without_changing_raw_order():
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
    assert [match.blinkit for match in outcome.matches] == [blinkit_mixed]


def test_unmatched_products_are_filtered_and_ranked_by_query_relevance():
    orange = product(Provider.BLINKIT, "Real Fruit Power Orange Juice")
    mixed = product(Provider.BLINKIT, "Real Fruit Power Mixed Fruit Juice")
    service = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, [orange, mixed]),
            FakeProvider(Provider.INSTAMART),
        ]
    )

    outcome = service.search("Real Mixed Fruit Juice")

    assert outcome.unmatched[Provider.BLINKIT] == [mixed]
    assert outcome.products[Provider.BLINKIT] == [orange, mixed]


def test_brand_anchor_removes_irrelevant_exact_matches():
    blinkit = [
        product(
            Provider.BLINKIT,
            "Nutralite DoodhShakti Salted Butter",
            "500 g",
        ),
        product(Provider.BLINKIT, "Harvest Gold White Bread", "350 g"),
        product(Provider.BLINKIT, "Amul Pasteurised Butter", "200 g"),
    ]
    instamart = [
        product(
            Provider.INSTAMART,
            "Nutralite DoodhShakti Salted Butter",
            "500 g",
        ),
        product(Provider.INSTAMART, "Harvest Gold White Bread", "350 g"),
        product(Provider.INSTAMART, "Amul Pasteurised Butter", "200 g"),
    ]
    outcome = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, blinkit),
            FakeProvider(Provider.INSTAMART, instamart),
        ]
    ).search("Amul Butter")

    assert [match.blinkit.title for match in outcome.matches] == [
        "Amul Pasteurised Butter"
    ]


def test_query_modifier_removes_womens_and_cross_brand_matches():
    blinkit = [
        product(
            Provider.BLINKIT,
            "Nivea Men Deep Impact Freshness Deodorant Roll On",
            "50 ml",
        ),
        product(
            Provider.BLINKIT,
            "Nivea Pearl & Beauty Women's Deodorant",
            "150 ml",
        ),
        product(
            Provider.BLINKIT,
            "Bombay Shaving Company Desire Men's Deodorant",
            "200 ml",
        ),
    ]
    instamart = [
        product(
            Provider.INSTAMART,
            "Nivea Men Deep Impact Freshness Deodorant Roll On",
            "50 ml",
        ),
        product(
            Provider.INSTAMART,
            "Nivea Pearl & Beauty Women's Deodorant",
            "150 ml",
        ),
        product(
            Provider.INSTAMART,
            "Bombay Shaving Company Desire Men's Deodorant",
            "200 ml",
        ),
    ]
    outcome = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, blinkit),
            FakeProvider(Provider.INSTAMART, instamart),
        ]
    ).search("Nivea Deodorant Men")

    assert [match.blinkit.title for match in outcome.matches] == [
        "Nivea Men Deep Impact Freshness Deodorant Roll On"
    ]


def test_matched_pair_can_supply_query_words_across_provider_titles():
    blinkit = product(
        Provider.BLINKIT,
        "Dettol Original Bathing Bar",
        "100 g",
    )
    instamart = product(
        Provider.INSTAMART,
        "Dettol Original Bathing Bar Soap",
        "100 g",
    )
    outcome = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, [blinkit]),
            FakeProvider(Provider.INSTAMART, [instamart]),
        ]
    ).search("Dettol Soap")

    assert len(outcome.matches) == 1


def test_no_observed_query_token_falls_back_instead_of_hiding_aliases():
    blinkit = product(Provider.BLINKIT, "Coca-Cola Soft Drink", "750 ml")
    outcome = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, [blinkit]),
            FakeProvider(Provider.INSTAMART),
        ]
    ).search("Coke")

    assert outcome.unmatched[Provider.BLINKIT] == [blinkit]


def test_irrelevant_unmatched_products_are_removed():
    relevant = product(
        Provider.BLINKIT,
        "Nivea Men Fresh Active Deodorant Roll On",
        "50 ml",
    )
    womens = product(
        Provider.BLINKIT,
        "Nivea Pearl & Beauty Women's Deodorant",
        "150 ml",
    )
    other_brand = product(
        Provider.BLINKIT,
        "Park Avenue Trance Perfume Spray for Men",
        "135 ml",
    )
    outcome = ComparisonService(
        [
            FakeProvider(
                Provider.BLINKIT,
                [womens, other_brand, relevant],
            ),
            FakeProvider(Provider.INSTAMART),
        ]
    ).search("Nivea Deodorant Men")

    assert outcome.unmatched[Provider.BLINKIT] == [relevant]


def test_query_quantity_prioritizes_requested_amount_in_secondary_results():
    one_litre = product(
        Provider.BLINKIT,
        "Surf Excel Matic Front Load Liquid Detergent",
        "1 ltr",
    )
    two_litres = product(
        Provider.BLINKIT,
        "Surf Excel Matic Front Load Liquid Detergent",
        "2 ltr",
    )
    wrong_dimension = product(
        Provider.BLINKIT,
        "Surf Excel Matic Front Load Liquid Detergent",
        "2000 g",
    )
    missing_quantity = product(
        Provider.BLINKIT,
        "Surf Excel Matic Front Load Liquid Detergent",
        "family pack",
    )
    outcome = ComparisonService(
        [
            FakeProvider(
                Provider.BLINKIT,
                [two_litres, wrong_dimension, missing_quantity, one_litre],
            ),
            FakeProvider(Provider.INSTAMART),
        ]
    ).search("Surf Excel Matic Liquid 1L")

    assert outcome.unmatched[Provider.BLINKIT] == [
        one_litre,
        two_litres,
        wrong_dimension,
        missing_quantity,
    ]


def test_query_quantity_allows_equal_total_single_and_multipack_results():
    single_pack = product(
        Provider.BLINKIT,
        "Dettol Original Bathing Bar Soap",
        "400 g",
    )
    multi_pack = product(
        Provider.BLINKIT,
        "Dettol Original Bathing Bar Soap",
        "4 x 100 g",
    )
    outcome = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, [single_pack, multi_pack]),
            FakeProvider(Provider.INSTAMART),
        ]
    ).search("Dettol Soap 400g")

    assert outcome.unmatched[Provider.BLINKIT] == [single_pack, multi_pack]


def test_query_quantity_filters_existing_exact_sku_matches():
    blinkit_one_litre = product(
        Provider.BLINKIT,
        "Surf Excel Matic Front Load Liquid Detergent",
        "1 ltr",
    )
    instamart_one_litre = product(
        Provider.INSTAMART,
        "Surf Excel Matic Front Load Liquid Detergent",
        "1000 ml",
    )
    blinkit_two_litres = product(
        Provider.BLINKIT,
        "Surf Excel Matic Top Load Liquid Detergent",
        "2 ltr",
    )
    instamart_two_litres = product(
        Provider.INSTAMART,
        "Surf Excel Matic Top Load Liquid Detergent",
        "2000 ml",
    )
    outcome = ComparisonService(
        [
            FakeProvider(
                Provider.BLINKIT,
                [blinkit_two_litres, blinkit_one_litre],
            ),
            FakeProvider(
                Provider.INSTAMART,
                [instamart_two_litres, instamart_one_litre],
            ),
        ]
    ).search("Surf Excel Matic Liquid 1L")

    assert [match.blinkit for match in outcome.matches] == [blinkit_one_litre]
    assert outcome.unmatched[Provider.BLINKIT] == [blinkit_two_litres]
    assert outcome.unmatched[Provider.INSTAMART] == [instamart_two_litres]


def test_quantity_query_keeps_other_matched_sizes_as_secondary_results():
    blinkit_58g = product(
        Provider.BLINKIT,
        "Lays Magic Masala Potato Chips",
        "58 g",
    )
    instamart_58g = product(
        Provider.INSTAMART,
        "Lays Magic Masala Potato Chips",
        "58 g",
    )
    blinkit_90g = product(
        Provider.BLINKIT,
        "Lays Magic Masala Potato Chips",
        "90 g",
    )
    instamart_90g = product(
        Provider.INSTAMART,
        "Lays Magic Masala Potato Chips",
        "90 g",
    )

    outcome = ComparisonService(
        [
            FakeProvider(Provider.BLINKIT, [blinkit_90g, blinkit_58g]),
            FakeProvider(Provider.INSTAMART, [instamart_90g, instamart_58g]),
        ]
    ).search("Lays 58 g")

    assert [match.blinkit for match in outcome.matches] == [blinkit_58g]
    assert outcome.unmatched[Provider.BLINKIT] == [blinkit_90g]
    assert outcome.unmatched[Provider.INSTAMART] == [instamart_90g]
