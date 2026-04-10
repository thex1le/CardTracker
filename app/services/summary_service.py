from __future__ import annotations

from typing import Any

from app.models.player import Player


def generate_summary(
    player: Player,
    scores: Any,
    hype_features: Any,
    market_features: Any,
    recent_events: list,
) -> str:
    """Returns a 1-2 sentence plain-English explanation of the player's current signal.

    Uses rule-based template matching, not LLM.
    """
    call_up = getattr(hype_features, "call_up_last_7d", False)
    debut = getattr(hype_features, "debut_last_7d", False)
    hype = getattr(scores, "hype_score", 0)
    market = getattr(scores, "market_score", 0)
    supply = getattr(scores, "supply_score", 0)
    hobby_fit = getattr(scores, "hobby_fit_score", 0)
    opportunity = getattr(scores, "opportunity_score", 0)
    exit_risk = getattr(scores, "exit_risk_score", 0)
    confidence = getattr(scores, "data_confidence", getattr(market_features, "data_points", 0))

    # Determine data_confidence from market_features if not on scores
    data_confidence = 0.0
    dp = getattr(market_features, "data_points", 0)
    if dp < 3:
        data_confidence = 0.2
    elif dp < 10:
        data_confidence = 0.5
    elif dp < 25:
        data_confidence = 0.75
    else:
        data_confidence = 1.0

    # Priority-ordered templates
    if call_up and market < 50:
        return "Recent call-up with rising attention, but market prices haven't fully adjusted yet."

    if debut:
        return "MLB debut within the last week — hobby attention typically peaks in the first few days."

    if market > 75 and supply > 65:
        return "Strong recent demand, but listing growth suggests supply is catching up quickly."

    if opportunity > 70 and data_confidence < 0.5:
        return "High opportunity score, but limited sales data — treat with caution."

    if hype > 60 and market < 35:
        return "Active narrative hasn't translated to buyer activity yet — early mover opportunity."

    if exit_risk > 65:
        return "Warning: price spike and listing surge suggest this window may be closing."

    if hobby_fit < 45 and hype > 50:
        return "Narrative is active, but this player archetype historically has weaker hobby follow-through."

    top_signal = _top_signal(hype_features, market_features)
    return f"Opportunity score {opportunity:.0f}/100 based on recent {top_signal}."


def _top_signal(hype_features: Any, market_features: Any) -> str:
    """Return the strongest single signal word."""
    signals = {}

    if getattr(hype_features, "call_up_last_7d", False):
        signals["call-up"] = 100
    if getattr(hype_features, "debut_last_7d", False):
        signals["debut"] = 90

    hr = getattr(hype_features, "hr_last_7d", 0)
    ops_d = getattr(hype_features, "ops_delta_7d", 0)
    if hr > 0 or ops_d > 0:
        signals["performance"] = hr * 10 + max(ops_d, 0) * 50

    velocity = getattr(market_features, "sales_velocity_delta", 0)
    if velocity > 0:
        signals["sales velocity"] = velocity

    median_d = getattr(market_features, "median_sale_delta_pct", 0)
    if median_d > 0:
        signals["price increase"] = median_d

    if not signals:
        return "activity"

    return max(signals, key=signals.get)
