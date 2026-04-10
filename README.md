# CardEdge

Baseball card market intelligence tool. Tracks players, ingests eBay market data, detects narrative triggers, and computes scores to surface buying opportunities.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env  # edit with your credentials

# Seed players from MLB rosters
python scripts/bootstrap_players.py

# Start API
uvicorn app.main:app --reload

# Start frontend (separate terminal)
streamlit run frontend/streamlit_app.py
```

## API Endpoints

- `GET /players` — search players
- `GET /players/{id}` — player detail with scores, events, sales
- `GET /feed/opportunities` — ranked opportunity feed
- `GET /feed/misspelled` — misspelled listing arbitrage feed
- `GET /watchlists` — list watchlists
- `GET /alerts` — alert feed
- `GET /api/health` — health check
