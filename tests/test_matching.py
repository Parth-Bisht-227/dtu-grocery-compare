from decimal import Decimal

import pytest

import matching.matcher as matcher_module
from matching.matcher import _title_score, evaluate_match, match_products
from matching.normalize import normalize_title, parse_quantity
from models import Product, Provider


def product(
    provider: Provider,
    title: str,
    quantity: str | None,
    price: str = "60",
    *,
    product_id: str | None = None,
) -> Product:
    return Product(
        provider=provider,
        title=title,
        quantity_raw=quantity or "unknown",
        quantity=parse_quantity(quantity) if quantity else None,
        price=Decimal(price),
        provider_product_id=product_id,
    )


def _install_scores(monkeypatch, scores: dict[tuple[str, str], float]) -> None:
    def fake_title_score(
        left_title: str, right_title: str, _token_weights: dict[str, float]
    ) -> float:
        return scores[(left_title, right_title)]

    monkeypatch.setattr(matcher_module, "_title_score", fake_title_score)


# Pair-level SKU labels.


def test_equivalent_mass_units_match():
    left = product(Provider.BLINKIT, "Amul Salted Butter", "500 g")
    right = product(Provider.INSTAMART, "Amul Salted Butter", "0.5 kg")

    assert evaluate_match(left, right).accepted


def test_same_sku_with_reordered_wording_matches():
    left = product(Provider.BLINKIT, "Fortune Sunflower Refined Oil", "1 L")
    right = product(Provider.INSTAMART, "Refined Sunflower Oil Fortune", "1000 ml")

    assert evaluate_match(left, right).accepted


def test_real_magggi_titles_with_harmless_marketing_text_match():
    left = product(
        Provider.BLINKIT,
        "Maggi Masala - 2 Minutes Instant Noodles Made With Quality Spices",
        "280 g",
    )
    right = product(
        Provider.INSTAMART,
        "MAGGI 2-Minute Instant Noodles, Made With Quality Spices",
        "280 g",
    )

    assert evaluate_match(left, right).accepted


def test_different_quantity_is_rejected():
    left = product(Provider.BLINKIT, "Maggi 2 Minute Instant Noodles", "280 g")
    right = product(Provider.INSTAMART, "Maggi 2-Minute Instant Noodles", "420 g")

    decision = evaluate_match(left, right)

    assert not decision.accepted
    assert decision.reason == "different total quantities"


def test_different_quantity_units_are_rejected():
    left = product(Provider.BLINKIT, "Example Grocery Product", "500 g")
    right = product(Provider.INSTAMART, "Example Grocery Product", "500 ml")

    assert evaluate_match(left, right).reason == "different quantity units"


def test_explicit_single_pack_matches_normal_single_pack():
    left = product(Provider.BLINKIT, "Amul Salted Butter", "500 g")
    right = product(Provider.INSTAMART, "Amul Salted Butter", "1 x 500 g")

    assert evaluate_match(left, right).accepted


def test_single_pack_and_multipack_are_rejected():
    left = product(Provider.BLINKIT, "Maggi Masala Instant Noodles", "150 g")
    right = product(Provider.INSTAMART, "Maggi Masala Instant Noodles", "3 x 50 g")

    assert evaluate_match(left, right).reason == "different pack structure"


def test_different_multipack_structures_are_rejected():
    left = product(Provider.BLINKIT, "Snack Bars", "2 x 100 g")
    right = product(Provider.INSTAMART, "Snack Bars", "4 x 50 g")

    assert evaluate_match(left, right).reason == "different pack counts"


def test_different_brands_are_rejected_by_generic_title_evidence():
    left = product(Provider.BLINKIT, "Amul Salted Butter", "100 g")
    right = product(Provider.INSTAMART, "Mother Dairy Salted Butter", "100 g")

    assert not evaluate_match(left, right).accepted


def test_salted_and_unsalted_are_rejected():
    left = product(Provider.BLINKIT, "Amul Salted Butter", "100 g")
    right = product(Provider.INSTAMART, "Amul Unsalted Butter", "100 g")

    assert not evaluate_match(left, right).accepted


def test_coke_and_coke_zero_are_rejected():
    left = product(Provider.BLINKIT, "Coca Cola", "750 ml")
    right = product(Provider.INSTAMART, "Coca Cola Zero Sugar", "750 ml")

    assert not evaluate_match(left, right).accepted


def test_different_lays_flavours_are_rejected():
    left = product(Provider.BLINKIT, "Lay's Magic Masala Potato Chips", "50 g")
    right = product(Provider.INSTAMART, "Lays Cream & Onion Potato Chips", "50 g")

    assert not evaluate_match(left, right).accepted


def test_missing_quantity_is_never_a_confident_match():
    left = product(Provider.BLINKIT, "Amul Salted Butter", None)
    right = product(Provider.INSTAMART, "Amul Salted Butter", "100 g")

    decision = evaluate_match(left, right)

    assert not decision.accepted
    assert decision.reason == "unparsed quantity"


def test_repeated_title_token_is_not_extra_identity_evidence():
    left = product(Provider.BLINKIT, "Real Fruit Juice", "1 ltr")
    right = product(Provider.INSTAMART, "Real Fruit Fruit Juice", "1 ltr")

    assert evaluate_match(left, right).score == 100.0


def test_distinctive_activ_token_outranks_repeated_fruit_power_wording():
    instamart_title = normalize_title(
        "Real Fruit Power Activ Mixed Fruit Juice"
    )
    token_weights = {
        "real": 1.0,
        "fruit": 1.0,
        "power": 1.6,
        "activ": 1.9,
        "mixed": 1.0,
        "juice": 1.0,
    }

    activ_score = _title_score(
        normalize_title("Real Activ Mixed Fruit Juice"),
        instamart_title,
        token_weights,
    )
    plain_score = _title_score(
        normalize_title("Real Fruit Power Mixed Fruit Juice"),
        instamart_title,
        token_weights,
    )

    assert activ_score > plain_score


# List-level resolution labels.


def test_two_corresponding_sizes_match_independently():
    blinkit = [
        product(Provider.BLINKIT, "MAGGI 2 Minute Instant Noodles", "280 g"),
        product(Provider.BLINKIT, "MAGGI 2 Minute Instant Noodles", "420 g"),
    ]
    instamart = [
        product(Provider.INSTAMART, "Maggi 2-Minute Instant Noodles", "420 g"),
        product(Provider.INSTAMART, "Maggi 2-Minute Instant Noodles", "280 g"),
    ]

    matches, unmatched = match_products(blinkit, instamart)

    assert len(matches) == 2
    assert not unmatched[Provider.BLINKIT]
    assert not unmatched[Provider.INSTAMART]
    assert {
        (match.blinkit.quantity.total_value, match.instamart.quantity.total_value)
        for match in matches
    } == {(Decimal("280"), Decimal("280")), (Decimal("420"), Decimal("420"))}


def test_duplicate_listing_does_not_create_false_ambiguity():
    blinkit = [product(Provider.BLINKIT, "Amul Pasteurised Butter", "200 g")]
    instamart = [
        product(Provider.INSTAMART, "Amul Pasteurised Butter", "200 g", "130"),
        product(Provider.INSTAMART, "Amul Pasteurised Butter", "200 g", "125"),
    ]

    matches, unmatched = match_products(blinkit, instamart)

    assert len(matches) == 1
    assert matches[0].instamart.price == Decimal("130")
    assert not unmatched[Provider.INSTAMART]


def test_exact_score_tie_remains_unmatched(monkeypatch):
    blinkit = [product(Provider.BLINKIT, "Blinkit cereal", "500 g")]
    instamart = [
        product(Provider.INSTAMART, "Instamart cereal one", "500 g"),
        product(Provider.INSTAMART, "Instamart cereal two", "500 g"),
    ]
    _install_scores(
        monkeypatch,
        {
            ("blinkit cereal", "instamart cereal one"): 90.0,
            ("blinkit cereal", "instamart cereal two"): 90.0,
        },
    )

    matches, unmatched = match_products(blinkit, instamart)

    assert not matches
    assert len(unmatched[Provider.BLINKIT]) == 1


def test_near_tie_below_margin_remains_unmatched(monkeypatch):
    blinkit = [product(Provider.BLINKIT, "Blinkit cereal", "500 g")]
    instamart = [
        product(Provider.INSTAMART, "Instamart cereal one", "500 g"),
        product(Provider.INSTAMART, "Instamart cereal two", "500 g"),
    ]
    _install_scores(
        monkeypatch,
        {
            ("blinkit cereal", "instamart cereal one"): 92.0,
            ("blinkit cereal", "instamart cereal two"): 91.0,
        },
    )

    assert not match_products(blinkit, instamart)[0]


def test_misleading_subset_loses_to_complete_variant():
    blinkit = [product(Provider.BLINKIT, "Coca Cola Zero Sugar", "750 ml")]
    instamart = [
        product(Provider.INSTAMART, "Coca Cola", "750 ml"),
        product(Provider.INSTAMART, "Coca-Cola Zero Sugar", "750 ml"),
    ]

    matches, _ = match_products(blinkit, instamart)

    assert len(matches) == 1
    assert matches[0].instamart.title == "Coca-Cola Zero Sugar"


def test_clear_best_candidate_above_margin_is_accepted(monkeypatch):
    blinkit = [product(Provider.BLINKIT, "Blinkit cereal", "500 g")]
    instamart = [
        product(Provider.INSTAMART, "Instamart cereal one", "500 g"),
        product(Provider.INSTAMART, "Instamart cereal two", "500 g"),
    ]
    _install_scores(
        monkeypatch,
        {
            ("blinkit cereal", "instamart cereal one"): 94.0,
            ("blinkit cereal", "instamart cereal two"): 73.0,
        },
    )

    matches, _ = match_products(blinkit, instamart)

    assert len(matches) == 1
    assert matches[0].instamart.title == "Instamart cereal one"


def test_reverse_direction_margin_is_also_required(monkeypatch):
    blinkit = [
        product(Provider.BLINKIT, "Blinkit cereal one", "500 g"),
        product(Provider.BLINKIT, "Blinkit cereal two", "500 g"),
    ]
    instamart = [product(Provider.INSTAMART, "Instamart cereal", "500 g")]
    _install_scores(
        monkeypatch,
        {
            ("blinkit cereal one", "instamart cereal"): 94.0,
            ("blinkit cereal two", "instamart cereal"): 90.0,
        },
    )

    assert not match_products(blinkit, instamart)[0]
