"""CardEdge — Streamlit frontend entry point."""
import sys
from pathlib import Path

# Ensure the frontend directory is on the path so `pages` is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

st.set_page_config(page_title="CardEdge", layout="wide")

API_BASE = "http://localhost:8000"

# Sidebar navigation
page = st.sidebar.radio("Navigation", ["Home", "Player Search", "Watchlist", "Alerts"])

if page == "Home":
    from pages.home import render_home
    render_home(API_BASE)
elif page == "Player Search":
    from pages.player import render_player_search
    render_player_search(API_BASE)
elif page == "Watchlist":
    from pages.watchlist import render_watchlist
    render_watchlist(API_BASE)
elif page == "Alerts":
    from pages.alerts import render_alerts
    render_alerts(API_BASE)
