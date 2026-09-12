"""Streamlit entry point for the DTU Grocery Price Compare MVP."""

from __future__ import annotations

from decimal import Decimal
from html import escape

import streamlit as st

from matching.normalize import extract_quantity
from models import Product, ProductMatch, Provider, SearchOutcome
from providers import BlinkitProvider, InstamartProvider
from service import ComparisonService


VISIBLE_RESULT_LIMIT = 8


st.set_page_config(
    page_title="DTU Grocery Price Compare",
    page_icon="🛒",
    layout="wide",
)

st.markdown(
    """
    <style>
      :root {
        --canvas: #F4F7F9;
        --surface: #FFFFFF;
        --ink: #17212B;
        --blinkit: #F7C948;
        --instamart: #FC6B3F;
        --winner: #16835B;
      }

      .stApp {
        background: var(--canvas);
        color: var(--ink);
        font-family: "Segoe UI", system-ui, sans-serif;
      }

      [data-testid="stHeader"] {
        background: rgba(244, 247, 249, 0.97);
        border-bottom: 1px solid #D9E2E8;
        color: var(--ink);
      }

      [data-testid="stHeader"] button,
      [data-testid="stHeader"] svg {
        color: var(--ink);
        fill: currentColor;
      }

      .block-container {
        max-width: 1080px;
        padding-top: 4.35rem;
        padding-bottom: 4rem;
      }

      h1, h2, h3 {
        color: var(--ink);
        font-family: "Trebuchet MS", "Segoe UI", sans-serif;
        letter-spacing: -0.025em;
      }

      .hero-kicker {
        color: #52616D;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.13em;
        margin-bottom: 0.35rem;
        text-transform: uppercase;
      }

      .hero-subtitle {
        color: #52616D;
        font-size: 1.08rem;
        margin: -0.4rem 0 1rem;
      }

      .location-chip {
        background: var(--surface);
        border: 1px solid #D9E2E8;
        border-radius: 999px;
        color: #34434E;
        display: inline-block;
        font-size: 0.86rem;
        font-weight: 600;
        margin-bottom: 1.4rem;
        padding: 0.42rem 0.78rem;
      }

      [data-testid="stForm"] {
        background: var(--surface);
        border: 1px solid #D9E2E8;
        border-radius: 16px;
        padding: 1rem 1.1rem 1.15rem;
      }

      [data-testid="stWidgetLabel"] p {
        color: #34434E !important;
      }

      [data-testid="stFormSubmitButton"] button {
        background: var(--ink);
        border: 1px solid var(--ink);
        min-height: 2.55rem;
      }

      [data-testid="stFormSubmitButton"] button:hover {
        background: #263643;
        border-color: #263643;
      }

      button:focus-visible, input:focus-visible {
        outline: 3px solid rgba(22, 131, 91, 0.32) !important;
        outline-offset: 2px;
      }

      [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--surface);
        border-radius: 14px;
      }

      [data-testid="stExpander"] details,
      [data-testid="stExpander"] summary {
        background: var(--surface) !important;
        color: var(--ink) !important;
      }

      [data-testid="stExpander"] summary:hover {
        background: #EDF2F5 !important;
        color: var(--ink) !important;
      }

      [data-testid="stExpander"] summary p,
      [data-testid="stExpander"] summary svg {
        color: var(--ink) !important;
        fill: currentColor;
      }

      .match-heading {
        align-items: center;
        display: flex;
        flex-wrap: wrap;
        gap: 0.6rem;
        justify-content: space-between;
        margin-bottom: 0.45rem;
      }

      .match-title {
        color: var(--ink);
        font-family: "Trebuchet MS", "Segoe UI", sans-serif;
        font-size: 1.05rem;
        font-weight: 700;
      }

      .pack-chip {
        background: #EDF2F5;
        border-radius: 999px;
        color: #34434E;
        font-family: ui-monospace, "Cascadia Mono", monospace;
        font-size: 0.8rem;
        font-weight: 700;
        padding: 0.28rem 0.58rem;
      }

      .provider-label {
        border-radius: 999px;
        color: var(--ink);
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        padding: 0.25rem 0.5rem;
        text-transform: uppercase;
      }

      .provider-blinkit { background: var(--blinkit); }
      .provider-instamart { background: var(--instamart); color: var(--ink); }

      .lane-price {
        color: var(--ink);
        font-family: ui-monospace, "Cascadia Mono", monospace;
        font-size: 1.65rem;
        font-weight: 800;
        line-height: 1.2;
        margin: 0.55rem 0 0.2rem;
      }

      .winner-strip {
        background: #E7F5EF;
        border-left: 4px solid var(--winner);
        border-radius: 7px;
        color: #0F6848;
        font-weight: 700;
        margin-top: 0.7rem;
        padding: 0.55rem 0.75rem;
      }

      .provider-section-label {
        border-bottom: 3px solid;
        color: var(--ink);
        font-family: "Trebuchet MS", "Segoe UI", sans-serif;
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: 0.65rem;
        padding-bottom: 0.35rem;
      }

      .provider-section-blinkit { border-color: var(--blinkit); }
      .provider-section-instamart { border-color: var(--instamart); }

      [data-testid="stAlert"] { border-radius: 10px; }

      @media (max-width: 640px) {
        .block-container { padding-top: 3.75rem; }
        .lane-price { font-size: 1.35rem; }
        .hero-subtitle { font-size: 1rem; }
      }

      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
          scroll-behavior: auto !important;
          transition-duration: 0.01ms !important;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def comparison_service() -> ComparisonService:
    return ComparisonService([BlinkitProvider(), InstamartProvider()])


def money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"₹{value:,.2f}".replace(".00", "")


def quantity_label(product: Product) -> str:
    """Show the provider quantity in the matcher's canonical base units."""
    quantity = product.quantity
    if quantity is None:
        return product.quantity_raw

    value = quantity.value if quantity.pack_count > 1 else quantity.total_value
    value_text = format(value.normalize(), "f")
    if quantity.pack_count > 1:
        return f"{quantity.pack_count} × {value_text} {quantity.unit}"
    return f"{value_text} {quantity.unit}"


def product_rows(products: list[Product]) -> list[dict[str, str]]:
    return [
        {
            "Product": product.title,
            "Pack": product.quantity_raw,
            "Price": money(product.price),
            "MRP": money(product.mrp),
        }
        for product in products
    ]


def render_price_lane(provider: Provider, product: Product) -> None:
    provider_class = (
        "provider-blinkit"
        if provider is Provider.BLINKIT
        else "provider-instamart"
    )
    st.markdown(
        f'<span class="provider-label {provider_class}">{provider.value}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="lane-price">{escape(money(product.price))}</div>',
        unsafe_allow_html=True,
    )
    st.caption(product.title)
    if product.mrp is not None and product.mrp > product.price:
        st.caption(f"MRP {money(product.mrp)}")


def render_match(match: ProductMatch) -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="match-heading">'
            f'<span class="match-title">{escape(match.blinkit.title)}</span>'
            f'<span class="pack-chip">{escape(quantity_label(match.blinkit))}</span>'
            "</div>",
            unsafe_allow_html=True,
        )

        blinkit_lane, instamart_lane = st.columns(2)
        with blinkit_lane:
            render_price_lane(Provider.BLINKIT, match.blinkit)
        with instamart_lane:
            render_price_lane(Provider.INSTAMART, match.instamart)

        result_text = (
            "Same price at both stores"
            if match.cheaper_provider is None
            else f"{match.cheaper_provider.value} is {money(match.savings)} cheaper"
        )
        st.markdown(
            f'<div class="winner-strip">🏁 {escape(result_text)}</div>',
            unsafe_allow_html=True,
        )


def render_product_table(products: list[Product]) -> None:
    rows = product_rows(products)
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Product": st.column_config.TextColumn(width="large"),
            "Pack": st.column_config.TextColumn(width="small"),
            "Price": st.column_config.TextColumn(width="small"),
            "MRP": st.column_config.TextColumn(width="small"),
        },
    )


def render_other_results(provider: Provider, products: list[Product]) -> None:
    provider_class = (
        "provider-section-blinkit"
        if provider is Provider.BLINKIT
        else "provider-section-instamart"
    )
    st.markdown(
        f'<div class="provider-section-label {provider_class}">'
        f"Other {provider.value} search results</div>",
        unsafe_allow_html=True,
    )
    if not products:
        st.caption(f"No other {provider.value} listings for this search.")
        return

    render_product_table(products[:VISIBLE_RESULT_LIMIT])
    remaining = products[VISIBLE_RESULT_LIMIT:]
    if remaining:
        with st.expander(f"Show {len(remaining)} more {provider.value} results"):
            render_product_table(remaining)


def render_provider_failures(outcome: SearchOutcome) -> bool:
    failed_providers = set(outcome.errors)
    if len(failed_providers) == len(Provider):
        st.error(
            "Blinkit and Instamart are temporarily unavailable. Try the search "
            "again in a moment."
        )
        return True

    for failed_provider in failed_providers:
        available_provider = (
            Provider.INSTAMART
            if failed_provider is Provider.BLINKIT
            else Provider.BLINKIT
        )
        if outcome.products.get(available_provider):
            st.warning(
                f"{failed_provider.value} is temporarily unavailable. "
                f"{available_provider.value} results are still shown."
            )
        else:
            st.warning(
                f"{failed_provider.value} is temporarily unavailable. "
                "Try again in a moment."
            )
    return False


def render_outcome(outcome: SearchOutcome) -> None:
    both_failed = render_provider_failures(outcome)
    blinkit_count = len(outcome.products.get(Provider.BLINKIT, []))
    instamart_count = len(outcome.products.get(Provider.INSTAMART, []))

    st.caption(
        f'Results for “{outcome.query}” at DTU · '
        f"{blinkit_count} Blinkit listings · {instamart_count} Instamart listings"
    )

    if both_failed:
        return
    if blinkit_count + instamart_count == 0:
        st.info(
            "No grocery listings were found. Try a shorter or more general "
            "product name."
        )
        return

    st.header("Comparable products")
    if outcome.matches:
        for match in outcome.matches:
            render_match(match)
    elif outcome.errors:
        st.info(
            "Price comparisons need results from both stores. Available listings "
            "are shown below."
        )
    else:
        st.info(
            "No confident same-product comparisons were found. Search results "
            "from both stores are shown below."
        )

    blinkit_unmatched = outcome.unmatched.get(Provider.BLINKIT, [])
    instamart_unmatched = outcome.unmatched.get(Provider.INSTAMART, [])
    if blinkit_unmatched or instamart_unmatched or outcome.errors:
        secondary_heading = (
            "Other sizes and search results"
            if extract_quantity(outcome.query) is not None
            else "Other search results"
        )
        st.header(secondary_heading)
        blinkit_column, instamart_column = st.columns(2)
        with blinkit_column:
            render_other_results(Provider.BLINKIT, blinkit_unmatched)
        with instamart_column:
            render_other_results(Provider.INSTAMART, instamart_unmatched)


st.markdown('<div class="hero-kicker">DTU hostel price check</div>', unsafe_allow_html=True)
st.title("The Great DTU Grocery Race")
st.markdown(
    '<div class="hero-subtitle">One search. Two stores. Prices for DTU.</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="location-chip">📍 Delivery location · DTU, Bawana Road</div>',
    unsafe_allow_html=True,
)

with st.form("search-form"):
    search_column, button_column = st.columns([4.8, 1.2], vertical_alignment="bottom")
    with search_column:
        query = st.text_input(
            "Search groceries",
            placeholder="Try Maggi, Amul butter, Coke, or chips",
        )
    with button_column:
        submitted = st.form_submit_button(
            "Compare prices",
            type="primary",
            width="stretch",
        )

st.caption("Prices and availability are fetched when you search and may change quickly.")

if submitted:
    st.session_state.pop("outcome", None)
    st.session_state.pop("ui_error", None)
    try:
        with st.spinner("Checking Blinkit and Instamart for DTU…"):
            st.session_state["outcome"] = comparison_service().search(query)
    except ValueError as error:
        st.session_state["ui_error"] = str(error)
    except Exception:
        st.session_state["ui_error"] = (
            "The comparison could not be completed. Try again in a moment."
        )

if "ui_error" in st.session_state:
    st.error(st.session_state["ui_error"])

if "outcome" in st.session_state:
    render_outcome(st.session_state["outcome"])

with st.expander("How comparison works"):
    st.write(
        "Products are compared only when their pack size and descriptions align "
        "closely. Uncertain matches are kept separate rather than forcing a "
        "potentially misleading price comparison."
    )
    st.caption("Recent searches are cached briefly to avoid unnecessary store requests.")
