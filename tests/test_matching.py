from decimal import Decimal

from matching.matcher import evaluate_match, match_products
from matching.normalize import parse_quantity
from models import Product, Provider


def product(provider: Provider, title: str, quantity: str, price: str = "60") -> Product:
    return Product(
        provider=provider,
        title=title,
        quantity_raw=quantity,
        quantity=parse_quantity(quantity),
        price=Decimal(price),
    )


def test_similar_wording_same_sku_matches():
    blinkit = product(
        Provider.BLINKIT,
        "Maggi Masala - 2 Minutes Instant Noodles Made With Quality Spices",
        "280 g",
    )
    instamart = product(
        Provider.INSTAMART,
        "MAGGI 2-Minute Instant Noodles, Made With Quality Spices",
        "280 g",
    )

    decision = evaluate_match(blinkit, instamart)

    assert decision.accepted
    assert decision.score >= 82


def test_same_product_different_size_is_rejected():
    blinkit = product(Provider.BLINKIT, "Maggi 2 Minute Instant Noodles", "280 g")
    instamart = product(Provider.INSTAMART, "Maggi 2-Minute Instant Noodles", "420 g")

    decision = evaluate_match(blinkit, instamart)

    assert not decision.accepted
    assert decision.reason == "different total quantities"


def test_same_brand_different_variant_is_rejected():
    garlic = product(Provider.BLINKIT, "Maggi Spicy Garlic Instant Noodles", "70.5 g")
    cheese = product(Provider.INSTAMART, "Maggi Spicy Cheesy Instant Noodles", "70.5 g")

    decision = evaluate_match(garlic, cheese)

    assert not decision.accepted
    assert decision.reason == "different product variants"


def test_equivalent_butter_wording_matches():
    blinkit = product(Provider.BLINKIT, "Amul Pasteurised Salted Butter", "500 g")
    instamart = product(Provider.INSTAMART, "Amul Salted Butter", "500gm")

    assert evaluate_match(blinkit, instamart).accepted


def test_different_products_with_brand_overlap_are_rejected():
    butter = product(Provider.BLINKIT, "Amul Salted Butter", "500 g")
    milk = product(Provider.INSTAMART, "Amul Chocolate Milk", "500 g")

    assert not evaluate_match(butter, milk).accepted


def test_equal_total_but_different_pack_structure_is_rejected():
    single = product(Provider.BLINKIT, "Maggi Masala Instant Noodles", "280 g")
    multipack = product(Provider.INSTAMART, "Maggi Masala Instant Noodles", "4 x 70 g")

    decision = evaluate_match(single, multipack)

    assert not decision.accepted
    assert decision.reason == "different pack structure"


def test_matching_is_one_to_one():
    blinkit = [product(Provider.BLINKIT, "Amul Salted Butter", "500 g", "275")]
    instamart = [
        product(Provider.INSTAMART, "Amul Salted Butter", "500 g", "270"),
        product(Provider.INSTAMART, "Amul Pasteurised Salted Butter", "500 g", "280"),
    ]

    matches, unmatched = match_products(blinkit, instamart)

    assert len(matches) == 1
    assert len(unmatched[Provider.INSTAMART]) == 1

