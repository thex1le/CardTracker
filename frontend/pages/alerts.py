"""Alerts page."""
from __future__ import annotations

import httpx
import streamlit as st


def render_alerts(api_base_url: str) -> None:
    st.header("Alerts")

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        severity_filter = st.selectbox(
            "Severity",
            ["All", "high", "medium", "low"],
        )
    with col2:
        type_filter = st.selectbox(
            "Type",
            [
                "All",
                "breakout",
                "market_confirmation",
                "supply_risk",
                "exit_risk",
                "watchlist_movement",
                "misspelled_listing",
            ],
        )

    params = {"limit": 50}
    if severity_filter != "All":
        params["severity"] = severity_filter
    if type_filter != "All":
        params["alert_type"] = type_filter

    try:
        resp = httpx.get(f"{api_base_url}/alerts", params=params, timeout=10)
        alerts = resp.json()
    except Exception as e:
        st.error(f"Failed to fetch alerts: {e}")
        return

    if not alerts:
        st.info("No alerts found.")
        return

    for alert in alerts:
        severity = alert["severity"]
        color = "red" if severity == "high" else "orange" if severity == "medium" else "blue"
        ack = " (acknowledged)" if alert.get("acknowledged") else ""

        with st.container():
            st.markdown(
                f"**:{color}[{severity.upper()}]** "
                f"**{alert['title']}**{ack} — {alert['alert_date']}"
            )
            st.write(alert["body"])

            if not alert.get("acknowledged"):
                if st.button("Acknowledge", key=f"ack_{alert['id']}"):
                    try:
                        httpx.post(f"{api_base_url}/alerts/{alert['id']}/acknowledge", timeout=10)
                        st.rerun()
                    except Exception:
                        st.error("Failed to acknowledge")

            st.divider()
