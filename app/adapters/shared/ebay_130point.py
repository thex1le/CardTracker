"""130point.com scraper for eBay sold card data.

Uses the backend API at back.130point.com/sales/ which returns HTML
fragments. Rate limit: max 10 requests per minute or face a 1-hour ban.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
import httpx

API_URL = "https://back.130point.com/sales/"
MIN_REQUEST_INTERVAL = 6.0  # seconds between requests (10/min limit)
_last_request_time = 0.0
_lock = asyncio.Lock()


async def search_sold_cards(
    player_name: str,
    card_set: str = "bowman chrome",
    sort: str = "EndTimeSoonest",
) -> list[dict]:
    """Search 130point for sold eBay listings.

    Returns list of dicts with: title, price_cents, currency, sold_date, ebay_url, sale_type
    """
    global _last_request_time

    query = f"{card_set} {player_name}"

    # Rate limiting
    async with _lock:
        now = time.time()
        wait = MIN_REQUEST_INTERVAL - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                API_URL,
                data={
                    "query": query,
                    "type": "sold_items",
                    "subcat": "-1",
                    "tab_id": "1",
                    "tz": "America/New_York",
                    "sort": sort,
                },
                headers={"User-Agent": "CardScout/1.0"},
            )
            resp.raise_for_status()
    except Exception as e:
        print(f"130point scrape error for '{query}': {e}")
        return []

    return _parse_response(resp.text)


def _parse_response(html: str) -> list[dict]:
    """Parse 130point API HTML response into structured card sale data."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for row in soup.find_all("tr", id="dRow"):
        try:
            # Price from data attribute
            price_str = row.get("data-price", "0")
            currency = row.get("data-currency", "USD")
            try:
                price_dollars = float(price_str)
                price_cents = int(price_dollars * 100)
            except (ValueError, TypeError):
                continue

            # Title and eBay URL
            title_tag = row.select_one("span#titleText a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            ebay_url = title_tag.get("href", "")

            # Sale date
            date_tag = row.select_one("span#dateText")
            sold_date = None
            if date_tag:
                date_text = date_tag.get_text(strip=True)
                date_text = re.sub(r"^Date:\s*", "", date_text)
                sold_date = _parse_date(date_text)

            # Sale type (Auction, BIN, Best Offer)
            sale_type_tag = row.select_one("span#auctionLabel")
            sale_type = sale_type_tag.get_text(strip=True) if sale_type_tag else "Unknown"

            results.append({
                "title": title,
                "price_cents": price_cents,
                "currency": currency,
                "sold_date": sold_date,
                "ebay_url": ebay_url,
                "sale_type": sale_type,
            })

        except Exception:
            continue

    return results


def _parse_date(text: str) -> str | None:
    """Parse 130point date string like 'Thu 09 Apr 2026 14:56:24 EDT' to YYYY-MM-DD."""
    # Strip timezone abbreviation (EDT, EST, PDT, etc.)
    text = re.sub(r"\s+[A-Z]{2,4}\s*$", "", text.strip())
    for fmt in [
        "%a %d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M:%S",
        "%a %d %b %Y",
        "%d %b %Y",
    ]:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_card_info(title: str) -> dict:
    """Try to extract card details from a listing title.

    Returns dict with: card_year, card_set, card_number, is_auto, is_graded, grade
    """
    info = {
        "card_year": None,
        "card_set": None,
        "card_number": None,
        "is_auto": False,
        "is_graded": False,
        "grade": None,
    }

    title_upper = title.upper()

    # Year (4-digit number starting with 19 or 20)
    year_match = re.search(r"\b(19|20)\d{2}\b", title)
    if year_match:
        info["card_year"] = int(year_match.group())

    # Card number (#123, #BC-1, etc.)
    num_match = re.search(r"#\s*([A-Z0-9\-]+)", title_upper)
    if num_match:
        info["card_number"] = num_match.group(1)

    # Auto detection
    auto_patterns = ["AUTO", "AUTOGRAPH", "/AUTO", "ON CARD AUTO", "ON-CARD"]
    info["is_auto"] = any(p in title_upper for p in auto_patterns)

    # Grading detection
    grade_match = re.search(
        r"(PSA|BGS|SGC|CGC)\s*(\d+\.?\d*)", title_upper
    )
    if grade_match:
        info["is_graded"] = True
        info["grade"] = f"{grade_match.group(1)} {grade_match.group(2)}"

    # Card set detection
    set_patterns = [
        "BOWMAN CHROME", "BOWMAN DRAFT", "BOWMAN 1ST", "1ST BOWMAN",
        "TOPPS CHROME", "TOPPS UPDATE", "TOPPS SERIES",
        "BOWMAN SAPPHIRE", "BOWMAN STERLING",
    ]
    for pat in set_patterns:
        if pat in title_upper:
            info["card_set"] = pat.title()
            break

    return info
