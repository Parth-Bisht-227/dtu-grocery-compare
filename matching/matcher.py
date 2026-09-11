"""Conservative, explainable cross-provider SKU matching."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz

from matching.normalize import normalize_title
from models import Product, ProductMatch, Provider


MATCH_THRESHOLD = 82.0
_MARKETING_TOKENS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "made",
    "of",
    "only",
    "pack",
    "quality",
    "spice",
    "the",
    "with",
}
_VARIANT_ALIASES = {
    "cheese": "cheese",
    "cheesy": "cheese",
    "chili": "chilli",
    "chilli": "chilli",
    "chilly": "chilli",
    "curry": "curry",
    "dark": "dark",
    "diet": "diet",
    "double": "double",
    "garlic": "garlic",
    "hot": "hot",
    "korean": "korean",
    "manchurian": "manchurian",
    "milk": "milk",
    "mushroom": "mushroom",
    "peri": "peri",
    "salted": "salted",
    "special": "special",
    "spicy": "spicy",
    "sweet": "sweet",
    "tandoori": "tandoori",
    "tomato": "tomato",
    "unsalted": "unsalted",
    "veg": "veg",
    "vegetable": "veg",
    "white": "white",
    "zero": "zero",
}


@dataclass(frozen=True)
class MatchDecision:
    accepted: bool
    score: float
    reason: str


def _tokens(product: Product) -> list[str]:
    return normalize_title(product.title).split()


def _brand(tokens: list[str]) -> str | None:
    return next(
        (token for token in tokens if token not in _MARKETING_TOKENS and not token.isdigit()),
        None,
    )


def _variant_signature(tokens: list[str]) -> frozenset[str]:
    return frozenset(
        _VARIANT_ALIASES[token] for token in tokens if token in _VARIANT_ALIASES
    )


def _family_tokens(tokens: list[str], brand: str | None) -> set[str]:
    return {
        token
        for token in tokens
        if token != brand
        and token not in _MARKETING_TOKENS
        and token not in _VARIANT_ALIASES
        and token not in {"instant", "minute", "2"}
        and not token.isdigit()
    }


def _quantities_compatible(left: Product, right: Product) -> tuple[bool, str]:
    if left.quantity is None or right.quantity is None:
        return False, "unparsed quantity"
    if left.quantity.unit != right.quantity.unit:
        return False, "different quantity units"
    if left.quantity.explicit_pack != right.quantity.explicit_pack:
        return False, "different pack structure"
    if left.quantity.explicit_pack and left.quantity.pack_count != right.quantity.pack_count:
        return False, "different pack counts"

    tolerance = max(Decimal("0.01"), left.quantity.total_value * Decimal("0.005"))
    if abs(left.quantity.total_value - right.quantity.total_value) > tolerance:
        return False, "different total quantities"
    return True, "equivalent quantity"


def evaluate_match(left: Product, right: Product) -> MatchDecision:
    """Return a decision with a concise reason suitable for debugging/interviews."""

    quantity_ok, quantity_reason = _quantities_compatible(left, right)
    if not quantity_ok:
        return MatchDecision(False, 0.0, quantity_reason)

    left_tokens, right_tokens = _tokens(left), _tokens(right)
    left_brand, right_brand = _brand(left_tokens), _brand(right_tokens)
    if not left_brand or not right_brand or left_brand != right_brand:
        return MatchDecision(False, 0.0, "different or unknown brands")

    left_variants = _variant_signature(left_tokens)
    right_variants = _variant_signature(right_tokens)
    if left_variants != right_variants:
        return MatchDecision(False, 0.0, "different product variants")

    left_family = _family_tokens(left_tokens, left_brand)
    right_family = _family_tokens(right_tokens, right_brand)
    if not left_family.intersection(right_family):
        return MatchDecision(False, 0.0, "no shared product-family token")

    left_title = " ".join(left_tokens)
    right_title = " ".join(right_tokens)
    score = round(
        0.55 * fuzz.token_set_ratio(left_title, right_title)
        + 0.45 * fuzz.WRatio(left_title, right_title),
        1,
    )
    if score < MATCH_THRESHOLD:
        return MatchDecision(False, score, "title similarity below threshold")
    return MatchDecision(True, score, f"{quantity_reason}; compatible brand and variant")


def match_products(
    blinkit_products: list[Product], instamart_products: list[Product]
) -> tuple[list[ProductMatch], dict[Provider, list[Product]]]:
    """Greedily choose the highest-scoring one-to-one valid matches."""

    candidates: list[tuple[float, int, int]] = []
    for blinkit_index, blinkit in enumerate(blinkit_products):
        for instamart_index, instamart in enumerate(instamart_products):
            decision = evaluate_match(blinkit, instamart)
            if decision.accepted:
                candidates.append((decision.score, blinkit_index, instamart_index))

    used_blinkit: set[int] = set()
    used_instamart: set[int] = set()
    matches: list[ProductMatch] = []
    for score, blinkit_index, instamart_index in sorted(candidates, reverse=True):
        if blinkit_index in used_blinkit or instamart_index in used_instamart:
            continue
        used_blinkit.add(blinkit_index)
        used_instamart.add(instamart_index)
        matches.append(
            ProductMatch(
                blinkit=blinkit_products[blinkit_index],
                instamart=instamart_products[instamart_index],
                score=score,
            )
        )

    unmatched = {
        Provider.BLINKIT: [
            product
            for index, product in enumerate(blinkit_products)
            if index not in used_blinkit
        ],
        Provider.INSTAMART: [
            product
            for index, product in enumerate(instamart_products)
            if index not in used_instamart
        ],
    }
    return matches, unmatched

