"""Pure parsing helpers kept separate from live browser interaction."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from matching.normalize import parse_quantity
from models import Product, Provider


_MONEY_RE = re.compile(r"^₹?\s*(\d[\d,]*(?:\.\d{1,2})?)$")


def _lines(card_text: str) -> list[str]:
    return [line.strip() for line in card_text.splitlines() if line.strip()]


def parse_money(raw: str) -> Decimal | None:
    match = _MONEY_RE.fullmatch(raw.strip())
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def _quantity_index(lines: list[str]) -> tuple[int, object] | None:
    for index, line in enumerate(lines):
        quantity = parse_quantity(line)
        if quantity is not None:
            return index, quantity
    return None


def _prices_after(lines: list[str], quantity_index: int) -> list[Decimal]:
    return [
        price
        for line in lines[quantity_index + 1 :]
        if (price := parse_money(line)) is not None
    ]


def parse_blinkit_card(
    card_text: str,
    *,
    product_id: str | None,
    image_url: str | None,
) -> Product | None:
    lines = _lines(card_text)
    quantity_result = _quantity_index(lines)
    if quantity_result is None:
        return None
    quantity_index, quantity = quantity_result
    if quantity_index == 0:
        return None
    prices = _prices_after(lines, quantity_index)
    if not prices:
        return None

    price = prices[0]
    mrp = prices[1] if len(prices) > 1 and prices[1] > price else None
    return Product(
        provider=Provider.BLINKIT,
        title=lines[quantity_index - 1],
        quantity_raw=lines[quantity_index],
        quantity=quantity,
        price=price,
        mrp=mrp,
        image_url=image_url,
        provider_product_id=product_id,
    )


def parse_instamart_card(
    card_text: str,
    *,
    image_alt: str | None,
    image_url: str | None,
) -> Product | None:
    lines = _lines(card_text)
    quantity_result = _quantity_index(lines)
    title = (image_alt or "").strip()
    if quantity_result is None or not title:
        return None
    quantity_index, quantity = quantity_result
    prices = _prices_after(lines, quantity_index)
    if not prices:
        return None

    price = prices[0]
    mrp = prices[1] if len(prices) > 1 and prices[1] > price else None
    return Product(
        provider=Provider.INSTAMART,
        title=title,
        quantity_raw=lines[quantity_index],
        quantity=quantity,
        price=price,
        mrp=mrp,
        image_url=image_url,
    )

