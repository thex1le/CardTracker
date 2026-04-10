from pydantic import BaseModel

from app.scoring.normalization import clamp


class HypeFeatures(BaseModel):
    call_up_last_7d: bool = False
    debut_last_7d: bool = False
    injury_return_last_7d: bool = False
    important_event_count_7d: int = 0
    hr_last_7d: int = 0
    ops_delta_7d: float = 0.0
    saves_last_7d: int = 0


def compute_hype_score(features: HypeFeatures) -> float:
    score = 0.0
    if features.call_up_last_7d:
        score += 30
    if features.debut_last_7d:
        score += 15
    if features.injury_return_last_7d:
        score += 10
    score += min(features.hr_last_7d * 4, 20)
    score += min(max(features.ops_delta_7d, 0) * 20, 25)
    score += min(features.saves_last_7d * 5, 20)
    return clamp(score)
