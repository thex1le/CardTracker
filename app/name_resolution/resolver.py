from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.name_resolution.normalizer import normalize_name

logger = logging.getLogger(__name__)

# Sport keywords to reject non-baseball titles
OTHER_SPORT_KEYWORDS = {"football", "basketball", "hockey", "soccer", "nfl", "nba", "nhl"}

BASEBALL_KEYWORDS = {
    "baseball", "mlb", "bowman", "topps", "donruss", "panini", "rookie", "rc",
    "auto", "refractor", "chrome", "prizm", "card", "psa", "bgs", "sgc",
}


@dataclass
class ResolveResult:
    player_id: int
    player_name: str
    matched_text: str
    match_method: str       # exact | fuzzy | typo_variant
    match_score: float      # 0.0-1.0
    confident: bool         # True if match_score >= 0.90


class PlayerNameResolver:
    def __init__(self, player_universe: list[dict]):
        """player_universe: list of {"id": int, "name": str, "name_normalized": str}

        Optionally include "variants": list[str] for typo variant matching.
        """
        self._players = player_universe
        self._name_index: dict[str, dict] = {}
        self._variant_index: dict[str, dict] = {}
        self._names_for_fuzzy: list[str] = []
        self._name_to_player: dict[str, dict] = {}

        for p in player_universe:
            norm = p["name_normalized"]
            self._name_index[norm] = p
            self._names_for_fuzzy.append(norm)
            self._name_to_player[norm] = p

            for v in p.get("variants", []):
                self._variant_index[v] = p

    def resolve(self, raw_title: str) -> ResolveResult | None:
        """Attempt to identify a player from a raw eBay listing title."""
        title_lower = raw_title.lower()

        # Guard: reject other sports
        if any(kw in title_lower for kw in OTHER_SPORT_KEYWORDS):
            logger.debug("Rejected (other sport): %s", raw_title[:80])
            return None

        # Guard: must contain at least one baseball keyword
        if not any(kw in title_lower for kw in BASEBALL_KEYWORDS):
            logger.debug("Rejected (no baseball keyword): %s", raw_title[:80])
            return None

        title_norm = normalize_name(raw_title)

        # 1. Exact match: check if any normalized player name is a substring
        for norm_name, player in self._name_index.items():
            if norm_name in title_norm:
                result = ResolveResult(
                    player_id=player["id"],
                    player_name=player["name"],
                    matched_text=norm_name,
                    match_method="exact",
                    match_score=1.0,
                    confident=True,
                )
                logger.debug(
                    "Resolved exact: '%s' -> %s (score=1.0)",
                    raw_title[:60], player["name"],
                )
                return result

        # 2. Typo variant match
        for variant, player in self._variant_index.items():
            if variant in title_norm:
                result = ResolveResult(
                    player_id=player["id"],
                    player_name=player["name"],
                    matched_text=variant,
                    match_method="typo_variant",
                    match_score=0.85,
                    confident=False,
                )
                logger.debug(
                    "Resolved typo_variant: '%s' -> %s (variant='%s', score=0.85)",
                    raw_title[:60], player["name"], variant,
                )
                return result

        # 3. Fuzzy match — try ngrams of the title to avoid dilution
        if not self._names_for_fuzzy:
            return None

        # Extract 2-3 word ngrams from title as candidate name strings
        words = title_norm.split()
        candidates = [title_norm]
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                candidates.append(" ".join(words[i:i + n]))

        best_match = None
        best_score = 0
        for candidate in candidates:
            match = process.extractOne(
                candidate,
                self._names_for_fuzzy,
                scorer=fuzz.ratio,
                score_cutoff=75,
            )
            if match and match[1] > best_score:
                best_match = match
                best_score = match[1]

        if best_match is None:
            logger.debug("No match: '%s'", raw_title[:60])
            return None

        matched_name, score, _ = best_match
        player = self._name_to_player[matched_name]
        norm_score = score / 100.0

        result = ResolveResult(
            player_id=player["id"],
            player_name=player["name"],
            matched_text=matched_name,
            match_method="fuzzy",
            match_score=norm_score,
            confident=norm_score >= 0.90,
        )
        logger.debug(
            "Resolved fuzzy: '%s' -> %s (score=%.2f)",
            raw_title[:60], player["name"], norm_score,
        )
        return result

    def resolve_batch(self, titles: list[str]) -> list[ResolveResult | None]:
        """Resolve a list of titles."""
        return [self.resolve(t) for t in titles]
