"""CardEdge — Streamlit frontend entry point."""
import streamlit as st

st.set_page_config(page_title="CardEdge", layout="wide")

API_BASE = "http://localhost:8000"

# Sidebar navigation
page = st.sidebar.radio("Navigation", ["Home", "Player Search", "Watchlist", "Alerts"])

if page == "Home":
    from frontend.pages.home import render_home
    render_home(API_BASE)
elif page == "Player Search":
    from frontend.pages.player import render_player_search
    render_player_search(API_BASE)
elif page == "Watchlist":
    from frontend.pages.watchlist import render_watchlist
    render_watchlist(API_BASE)
elif page == "Alerts":
    from frontend.pages.alerts import render_alerts
    render_alerts(API_BASE)
