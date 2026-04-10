"""Player detail page."""
from __future__ import annotations

import httpx
import streamlit as st


def render_player_search(api_base_url: str) -> None:
    st.header("Player Search")

    query = st.text_input("Search by name")

    if query:
        try:
            resp = httpx.get(f"{api_base_url}/players", params={"q": query}, timeout=10)
            players = resp.json()
        except Exception as e:
            st.error(f"Search failed: {e}")
            return

        if not players:
            st.info("No players found.")
            return

        selected = st.selectbox(
            "Select player",
            players,
            format_func=lambda p: f"{p['name']} ({p['team']} — {p['position']})",
        )

        if selected:
            render_player_detail(api_base_url, selected["id"])


def render_player_detail(api_base_url: str, player_id: int) -> None:
    try:
        resp = httpx.get(f"{api_base_url}/players/{player_id}", timeout=10)
        data = resp.json()
    except Exception as e:
        st.error(f"Failed to load player: {e}")
        return

    # Header
    st.subheader(f"{data['name']} — {data.get('team', '?')} {data.get('position', '?')}")

    # Score cards
    scores = data.get("scores")
    if scores:
        cols = st.columns(5)
        labels = [
            ("Hype", "hype_score"),
            ("Market", "market_score"),
            ("Supply", "supply_score"),
            ("Hobby Fit", "hobby_fit_score"),
            ("Opportunity", "opportunity_score"),
        ]
        for col, (label, key) in zip(cols, labels):
            col.metric(label, f"{scores.get(key, 0):.0f}")

        # Data confidence
        conf = scores.get("data_confidence", 0)
        conf_label = "Low" if conf < 0.3 else "Medium" if conf < 0.7 else "High"
        st.progress(conf, text=f"Data confidence: {conf_label} ({conf:.0%})")

    # Summary
    summary = data.get("summary_text")
    if summary:
        st.info(summary)

    # Tabs
    tab_events, tab_perf, tab_market = st.tabs(["Events", "Performance", "Market"])

    with tab_events:
        events = data.get("recent_events", [])
        if events:
            for e in events:
                st.markdown(f"**{e['event_date']}** — {e['title']}")
                if e.get("details"):
                    st.caption(e["details"])
        else:
            st.info("No recent events.")

    with tab_perf:
        perf = data.get("recent_performance", [])
        if perf:
            st.dataframe(perf, use_container_width=True, hide_index=True)
        else:
            st.info("No recent performance data.")

    with tab_market:
        sales = data.get("recent_sales", [])
        snapshots = data.get("listing_snapshots", [])

        if sales:
            st.subheader("Recent Sales")
            st.dataframe(
                [
                    {
                        "Date": s["sale_date"],
                        "Title": s["card_title"][:60],
                        "Type": s.get("card_type", ""),
                        "Grade": f"{s.get('grader', '')} {s.get('grade', '')}".strip(),
                        "Price": f"${s['sale_price']:.2f}",
                        "Match": s.get("match_method", ""),
                    }
                    for s in sales
                ],
                use_container_width=True,
                hide_index=True,
            )

        if snapshots:
            st.subheader("Listing Trend")
            st.line_chart(
                {s["snapshot_date"]: s["active_listing_count"] for s in reversed(snapshots)}
            )
