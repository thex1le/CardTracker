import pytest

from app.name_resolution.normalizer import normalize_name
from app.name_resolution.variants import generate_typo_variants
from app.name_resolution.resolver import PlayerNameResolver


# --- normalize_name tests ---

class TestNormalizeName:
    def test_accents_removed(self):
        assert normalize_name("José Ramírez Jr.") == "jose ramirez"

    def test_periods_removed(self):
        assert normalize_name("C.J. Abrams") == "cj abrams"

    def test_suffix_jr(self):
        assert normalize_name("Bobby Witt Jr.") == "bobby witt"

    def test_suffix_sr(self):
        assert normalize_name("Ken Griffey Sr.") == "ken griffey"

    def test_suffix_iii(self):
        assert normalize_name("Ronald Acuña III") == "ronald acuna"

    def test_suffix_ii(self):
        assert normalize_name("Player Name II") == "player name"

    def test_whitespace_collapse(self):
        assert normalize_name("  Mike   Trout  ") == "mike trout"

    def test_plain_name(self):
        assert normalize_name("Corbin Carroll") == "corbin carroll"


# --- generate_typo_variants tests ---

class TestGenerateTypoVariants:
    def test_transposition(self):
        variants = generate_typo_variants("Corbin Carroll")
        assert "carroll corbin" in variants

    def test_single_char_deletion_long_last_name(self):
        variants = generate_typo_variants("Corbin Carroll")
        # "carroll" -> "arroll", "crroll", "caroll", "caroll"
        assert any("arroll" in v for v in variants)

    def test_double_letter_collapse(self):
        variants = generate_typo_variants("Corbin Carroll")
        assert "corbin carrol" in variants

    def test_excludes_original(self):
        variants = generate_typo_variants("Corbin Carroll")
        assert "corbin carroll" not in variants

    def test_initials_variants(self):
        variants = generate_typo_variants("CJ Abrams")
        assert any("c.j." in v for v in variants) or any("c j" in v for v in variants)

    def test_short_last_name_no_deletion(self):
        # Last name "Witt" is 4 chars, no single-char deletions should occur
        variants = generate_typo_variants("Bobby Witt")
        deletion_variants = [v for v in variants if len(v.split()[-1]) == 3]
        assert len(deletion_variants) == 0


# --- PlayerNameResolver tests ---

PLAYER_UNIVERSE = [
    {"id": 1, "name": "Corbin Carroll", "name_normalized": "corbin carroll", "variants": ["carroll corbin", "corbin carrol"]},
    {"id": 2, "name": "Bobby Witt Jr.", "name_normalized": "bobby witt", "variants": ["witt bobby"]},
    {"id": 3, "name": "Gunnar Henderson", "name_normalized": "gunnar henderson", "variants": ["henderson gunnar", "gunnar henderon"]},
]


class TestPlayerNameResolver:
    def setup_method(self):
        self.resolver = PlayerNameResolver(PLAYER_UNIVERSE)

    def test_exact_match(self):
        result = self.resolver.resolve("2023 Bowman Chrome Corbin Carroll RC Auto")
        assert result is not None
        assert result.player_id == 1
        assert result.match_method == "exact"
        assert result.match_score == 1.0
        assert result.confident is True

    def test_typo_variant_match(self):
        result = self.resolver.resolve("2023 Topps Corbin Carrol Rookie Card")
        assert result is not None
        assert result.player_id == 1
        assert result.match_method == "typo_variant"
        assert result.match_score == 0.85

    def test_fuzzy_match(self):
        result = self.resolver.resolve("2023 Bowman Chrome Gunnar Hendersen Baseball Card")
        assert result is not None
        assert result.player_id == 3
        assert result.match_method == "fuzzy"
        assert result.match_score >= 0.75

    def test_non_baseball_rejected(self):
        result = self.resolver.resolve("2023 Panini Prizm Corbin Carroll Football Card")
        assert result is None

    def test_basketball_rejected(self):
        result = self.resolver.resolve("Bobby Witt Basketball NBA Rookie")
        assert result is None

    def test_no_baseball_keyword_rejected(self):
        result = self.resolver.resolve("Corbin Carroll signed photograph print")
        assert result is None

    def test_resolve_batch(self):
        titles = [
            "2023 Bowman Chrome Corbin Carroll RC Auto",
            "Bobby Witt football card",
        ]
        results = self.resolver.resolve_batch(titles)
        assert results[0] is not None
        assert results[0].player_id == 1
        assert results[1] is None
