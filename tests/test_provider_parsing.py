from decimal import Decimal

from models import Provider
from providers.parsing import parse_blinkit_card, parse_instamart_card


def test_blinkit_card_text_parser():
    product = parse_blinkit_card(
        "10 MINS\nMaggi 2 Minutes Instant Noodles\n420 g\n₹79\n₹90\nADD",
        product_id="12345",
        image_url="https://example.test/maggi.png",
    )

    assert product is not None
    assert product.provider is Provider.BLINKIT
    assert product.title == "Maggi 2 Minutes Instant Noodles"
    assert product.price == Decimal("79")
    assert product.mrp == Decimal("90")


def test_instamart_card_text_parser_uses_image_alt_as_full_title():
    product = parse_instamart_card(
        "4 MINS\nTruncated visual title…\nEnjoy your favourite taste\n280 g\n11% OFF\n60\n70\nAd",
        image_alt="MAGGI 2-Minute Instant Noodles, Made With Quality Spices",
        image_url="https://example.test/maggi.png",
    )

    assert product is not None
    assert product.provider is Provider.INSTAMART
    assert product.title == "MAGGI 2-Minute Instant Noodles, Made With Quality Spices"
    assert product.price == Decimal("60")
    assert product.mrp == Decimal("70")

