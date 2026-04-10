"""Watchlist management page."""
from __future__ import annotations

import httpx
import streamlit as st


def render_watchlist(api_base_url: str) -> None:
    st.header("Watchlists")

    # Fetch watchlists
    try:
        resp = httpx.get(f"{api_base_url}/watchlists", timeout=10)
        watchlists = resp.json()
    except Exception as e:
        st.error(f"Failed to fetch watchlists: {e}")
        watchlists = []

    # Create new watchlist
    with st.expander("Create New Watchlist"):
        name = st.text_input("Watchlist name")
        user_id = st.text_input("User ID", value="default")
        if st.button("Create") and name:
            try:
                httpx.post(
                    f"{api_base_url}/watchlists",
                    json={"name": name, "user_id": user_id},
                    timeout=10,
                )
                st.success(f"Created watchlist: {name}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

    if not watchlists:
        st.info("No watchlists yet. Create one above.")
        return

    # Select watchlist
    selected = st.selectbox(
        "Select watchlist",
        watchlists,
        format_func=lambda w: f"{w['name']} ({w['player_count']} players)",
    )

    if selected:
        try:
            resp = httpx.get(f"{api_base_url}/watchlists/{selected['id']}", timeout=10)
            detail = resp.json()
        except Exception:
            st.error("Failed to load watchlist")
            return

        players = detail.get("players", [])
        if players:
            for p in players:
                col1, col2, col3 = st.columns([3, 2, 1])
                col1.write(f"**{p['name']}** ({p.get('team', '?')} — {p.get('position', '?')})")
                scores = p.get("scores")
                if scores and scores.get("opportunity_score") is not None:
                    col2.write(f"Opportunity: {scores['opportunity_score']:.0f}")
                if col3.button("Remove", key=f"rm_{p['player_id']}"):
                    try:
                        httpx.delete(
                            f"{api_base_url}/watchlists/{selected['id']}/players/{p['player_id']}",
                            timeout=10,
                        )
                        st.rerun()
                    except Exception:
                        st.error("Failed to remove")
        else:
            st.info("No players in this watchlist.")

        # Add player
        st.subheader("Add Player")
        search = st.text_input("Search player to add", key="wl_search")
        if search:
            try:
                resp = httpx.get(f"{api_base_url}/players", params={"q": search}, timeout=10)
                results = resp.json()
            except Exception:
                results = []

            for r in results[:10]:
                col1, col2 = st.columns([4, 1])
                col1.write(f"{r['name']} ({r.get('team', '?')})")
                if col2.button("Add", key=f"add_{r['id']}"):
                    try:
                        httpx.post(
                            f"{api_base_url}/watchlists/{selected['id']}/players",
                            json={"player_id": r["id"]},
                            timeout=10,
                        )
                        st.rerun()
                    except Exception:
                        st.error("Failed to add (may already be in watchlist)")
