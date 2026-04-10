import pytest

from app.ingestion.market.sold_listings import parse_card_type, parse_grader_grade, parse_listing_to_sale
from app.name_resolution.resolver import ResolveResult


class TestParseCardType:
    def test_auto(self):
        assert parse_card_type("2023 Bowman Chrome Auto /99") == "auto"

    def test_rookie(self):
        assert parse_card_type("2023 Topps RC Corbin Carroll") == "rookie"

    def test_rookie_word(self):
        assert parse_card_type("2023 Topps Rookie Card") == "rookie"

    def test_refractor(self):
        assert parse_card_type("2023 Bowman Chrome Refractor") == "refractor"

    def test_chrome_as_refractor(self):
        assert parse_card_type("2023 Bowman Chrome") == "refractor"

    def test_numbered(self):
        assert parse_card_type("2023 Topps Base #/50") == "numbered"

    def test_base(self):
        assert parse_card_type("2023 Topps Series 1") == "base"

    def test_auto_takes_priority(self):
        assert parse_card_type("2023 Bowman Chrome Auto /99 RC") == "auto"


class TestParseGraderGrade:
    def test_psa_10(self):
        assert parse_grader_grade("PSA 10 Gem Mint") == ("PSA", "10")

    def test_bgs_9_5(self):
        assert parse_grader_grade("BGS 9.5") == ("BGS", "9.5")

    def test_sgc_10(self):
        assert parse_grader_grade("SGC10 Pristine") == ("SGC", "10")

    def test_no_grade(self):
        assert parse_grader_grade("2023 Topps Base Card") == (None, None)

    def test_case_insensitive(self):
        assert parse_grader_grade("psa 9") == ("PSA", "9")


class TestParseListingToSale:
    def _make_raw(self, title="Test Card", price="10.99", item_id="123", listing_type="Auction"):
        return {
            "title": [title],
            "itemId": [item_id],
            "sellingStatus": [{"currentPrice": [{"__value__": price}]}],
            "listingInfo": [{
                "endTime": ["2024-06-15T12:00:00.000Z"],
                "listingType": [listing_type],
            }],
        }

    def _make_resolve(self):
        return ResolveResult(
            player_id=1,
            player_name="Test Player",
            matched_text="test player",
            match_method="exact",
            match_score=1.0,
            confident=True,
        )

    def test_basic_parse(self):
        raw = self._make_raw()
        result = parse_listing_to_sale(raw, 1, self._make_resolve())
        assert result is not None
        assert result["sale_price"] == 10.99
        assert result["source_item_id"] == "123"
        assert result["player_match_method"] == "exact"
        assert result["player_match_score"] == 1.0

    def test_auction_type(self):
        raw = self._make_raw(listing_type="Auction")
        result = parse_listing_to_sale(raw, 1, self._make_resolve())
        assert result["listing_type"] == "auction"

    def test_bin_type(self):
        raw = self._make_raw(listing_type="FixedPrice")
        result = parse_listing_to_sale(raw, 1, self._make_resolve())
        assert result["listing_type"] == "buy_it_now"
