"""Streamlit entry point for the DTU Grocery Price Compare MVP."""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from models import Product, Provider, SearchOutcome
from providers import BlinkitProvider, InstamartProvider
from service import ComparisonService


st.set_page_config(
    page_title="DTU Grocery Price Compare",
    page_icon="🛒",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 1100px; padding-top: 2.2rem;}
      [data-testid="stMetricValue"] {font-size: 1.65rem;}
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


def product_rows(products: list[Product]) -> list[dict[str, str]]:
    return [
        {
            "Product": product.title,
            "Quantity": product.quantity_raw,
            "Price": money(product.price),
            "MRP": money(product.mrp),
        }
        for product in products
    ]


def render_outcome(outcome: SearchOutcome) -> None:
    for provider, error in outcome.errors.items():
        st.warning(f"{provider.value} is temporarily unavailable: {error}")

    blinkit_count = len(outcome.products.get(Provider.BLINKIT, []))
    instamart_count = len(outcome.products.get(Provider.INSTAMART, []))
    metrics = st.columns(3)
    metrics[0].metric("Confident matches", len(outcome.matches))
    metrics[1].metric("Blinkit listings", blinkit_count)
    metrics[2].metric("Instamart listings", instamart_count)

    st.subheader("Like-for-like comparisons")
    if not outcome.matches:
        st.info(
            "No confident same-SKU matches were found. The app deliberately avoids "
            "comparing different sizes or uncertain variants."
        )
    else:
        comparison_rows: list[dict[str, str]] = []
        for match in outcome.matches:
            cheaper = (
                "Same price"
                if match.cheaper_provider is None
                else f"{match.cheaper_provider.value} saves {money(match.savings)}"
            )
            comparison_rows.append(
                {
                    "Product": match.blinkit.title,
                    "Quantity": match.blinkit.quantity_raw,
                    "Blinkit": money(match.blinkit.price),
                    "Instamart": money(match.instamart.price),
                    "Best price": cheaper,
                    "Confidence": f"{match.score:.0f}%",
                }
            )
        st.dataframe(comparison_rows, hide_index=True, use_container_width=True)

    st.subheader("Provider listings")
    blinkit_tab, instamart_tab = st.tabs(["Blinkit", "Instamart"])
    with blinkit_tab:
        rows = product_rows(outcome.products.get(Provider.BLINKIT, []))
        st.dataframe(rows, hide_index=True, use_container_width=True) if rows else st.caption(
            "No Blinkit listings available."
        )
    with instamart_tab:
        rows = product_rows(outcome.products.get(Provider.INSTAMART, []))
        st.dataframe(rows, hide_index=True, use_container_width=True) if rows else st.caption(
            "No Instamart listings available."
        )


st.title("The Great DTU Grocery Race")
st.caption("Live Blinkit vs Instamart listings for Delhi Technological University")

with st.form("search-form"):
    query = st.text_input(
        "What are you looking for?",
        placeholder="Try Maggi, Amul butter, Coke, or chips",
    )
    submitted = st.form_submit_button("Compare prices", type="primary")

if submitted:
    try:
        with st.spinner("Checking both stores for DTU…"):
            st.session_state["outcome"] = comparison_service().search(query)
    except ValueError as error:
        st.error(str(error))

if "outcome" in st.session_state:
    render_outcome(st.session_state["outcome"])

with st.sidebar:
    st.header("How matching works")
    st.write(
        "A pair must have compatible normalized quantity, pack structure, brand, "
        "and variant before title similarity is considered. Uncertain pairs stay unmatched."
    )
    st.caption("Results are cached for 3 minutes to keep request volume reasonable.")

