"""Home page — Today's Opportunities."""
from __future__ import annotations

import httpx
import streamlit as st


def render_home(api_base_url: str) -> None:
    st.header("Today's Opportunities")

    # Filter row
    col1, col2, col3 = st.columns(3)
    with col1:
        position = st.selectbox(
            "Position",
            ["All", "SS", "OF", "3B", "1B", "2B", "C", "SP", "RP", "DH"],
        )
    with col2:
        team = st.text_input("Team filter", "")
    with col3:
        prospects_only = st.checkbox("Prospects only")

    # Fetch opportunities
    params = {"limit": 25}
    if position != "All":
        params["position"] = position
    if team:
        params["team"] = team
    if prospects_only:
        params["prospects_only"] = "true"

    try:
        resp = httpx.get(f"{api_base_url}/feed/opportunities", params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        st.error(f"Failed to fetch opportunities: {e}")
        data = []

    if data:
        st.dataframe(
            [
                {
                    "Player": d["player_name"],
                    "Team": d["team"],
                    "Pos": d["position"],
                    "Opportunity": f'{d["opportunity_score"]:.0f}',
                    "Hype": f'{d["hype_score"]:.0f}',
                    "Market": f'{d["market_score"]:.0f}',
                    "Supply": f'{d["supply_score"]:.0f}',
                    "Summary": d.get("summary", ""),
                }
                for d in data
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No opportunities found. Run the daily ingest and score refresh first.")

    # Misspelled Listing Alerts
    st.subheader("Misspelled Listing Alerts")
    try:
        resp = httpx.get(f"{api_base_url}/feed/misspelled", timeout=10)
        misspelled = resp.json()
    except Exception:
        misspelled = []

    if misspelled:
        for item in misspelled:
            severity_color = "red" if item["severity"] == "high" else "orange"
            st.markdown(
                f'**:{severity_color}[{item["severity"].upper()}]** '
                f'**{item["player_name"]}** — {item["title"]}'
            )
            st.caption(item["body"])
    else:
        st.info("No misspelled listing alerts.")
