from app.models.player import Player
from app.scoring.normalization import clamp

POSITION_BASE_SCORES = {
    "SS": 85, "OF": 80, "3B": 75, "1B": 65, "2B": 60, "C": 40,
    "SP": 60, "RP": 35, "DH": 55,
}


def compute_hobby_fit_score(player: Player) -> float:
    """Compute hobby fit based on position, prospect status, and market size.

    Start from position base score.
    Apply bonuses for prospect flags and large market.
    Clamp to 0-100.
    """
    pos = (player.position or "").upper()
    # Try direct match, then check common multi-position patterns
    score = POSITION_BASE_SCORES.get(pos, 50.0)
    for key in POSITION_BASE_SCORES:
        if key in pos:
            score = POSITION_BASE_SCORES[key]
            break

    if player.top_prospect_flag:
        score += 15
    elif player.prospect_flag:
        score += 8

    if player.market_size_tier == "large":
        score += 8

    return clamp(score)
