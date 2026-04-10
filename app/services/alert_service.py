from __future__ import annotations

import logging
from datetime import date, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.event import PlayerEvent
from app.models.market_sale import MarketSale
from app.models.player import Player
from app.models.score_daily import ScoreDaily

logger = logging.getLogger(__name__)


def check_breakout_alert(today: ScoreDaily, yesterday: ScoreDaily | None) -> Alert | None:
    if today.hype_score > 70 and 40 < today.market_score < 70 and today.supply_score < 50:
        return Alert(
            player_id=today.player_id,
            alert_type="breakout",
            alert_date=today.score_date,
            severity="high",
            title=f"Breakout signal detected",
            body=f"Hype score {today.hype_score:.0f} with market activity rising but supply still low.",
            score_snapshot={
                "hype": today.hype_score,
                "market": today.market_score,
                "supply": today.supply_score,
            },
        )
    return None


def check_market_confirmation(today: ScoreDaily, sales_trend: dict) -> Alert | None:
    if (
        today.market_score > 75
        and sales_trend.get("count_rising", False)
        and sales_trend.get("median_rising", False)
    ):
        return Alert(
            player_id=today.player_id,
            alert_type="market_confirmation",
            alert_date=today.score_date,
            severity="medium",
            title="Market confirming narrative",
            body=f"Market score {today.market_score:.0f} — sales count and median price both rising.",
            score_snapshot={"market": today.market_score},
        )
    return None


def check_supply_risk(today: ScoreDaily) -> Alert | None:
    if today.supply_score > 70:
        return Alert(
            player_id=today.player_id,
            alert_type="supply_risk",
            alert_date=today.score_date,
            severity="medium",
            title="Supply surge warning",
            body=f"Supply score {today.supply_score:.0f} — listing growth may outpace demand.",
            score_snapshot={"supply": today.supply_score},
        )
    return None


def check_exit_risk(today: ScoreDaily) -> Alert | None:
    if today.exit_risk_score > 70:
        return Alert(
            player_id=today.player_id,
            alert_type="exit_risk",
            alert_date=today.score_date,
            severity="high",
            title="Exit risk elevated",
            body=f"Exit risk score {today.exit_risk_score:.0f} — consider taking profits.",
            score_snapshot={"exit_risk": today.exit_risk_score},
        )
    return None


def check_watchlist_movement(
    today: ScoreDaily,
    yesterday: ScoreDaily | None,
    new_events: list[PlayerEvent],
) -> Alert | None:
    opp_delta = 0
    if yesterday:
        opp_delta = abs(today.opportunity_score - yesterday.opportunity_score)

    important_events = [e for e in new_events if e.importance_score > 0.7]

    if opp_delta > 15 or important_events:
        reason = f"Opportunity score changed by {opp_delta:.0f} points" if opp_delta > 15 else ""
        if important_events:
            event_desc = ", ".join(e.title for e in important_events[:3])
            reason = f"{reason}; Events: {event_desc}" if reason else f"Events: {event_desc}"

        return Alert(
            player_id=today.player_id,
            alert_type="watchlist_movement",
            alert_date=today.score_date,
            severity="medium",
            title="Watchlist player movement",
            body=reason,
            score_snapshot={
                "opportunity": today.opportunity_score,
                "prev_opportunity": yesterday.opportunity_score if yesterday else None,
            },
        )
    return None


async def check_misspelled_listing_alert(
    db: AsyncSession,
    player: Player,
    median_price_30d: float,
) -> Alert | None:
    yesterday = date.today() - timedelta(days=1)
    result = await db.execute(
        select(MarketSale).where(
            MarketSale.player_id == player.id,
            MarketSale.player_match_method == "typo_variant",
            MarketSale.sale_date >= yesterday,
        )
    )
    typo_sales = result.scalars().all()

    for sale in typo_sales:
        if median_price_30d > 0 and sale.sale_price < 0.85 * median_price_30d:
            severity = "high" if sale.sale_price < 0.70 * median_price_30d else "medium"
            discount_pct = ((median_price_30d - sale.sale_price) / median_price_30d) * 100

            return Alert(
                player_id=player.id,
                alert_type="misspelled_listing",
                alert_date=date.today(),
                severity=severity,
                title=f"Misspelled listing: {discount_pct:.0f}% below median",
                body=(
                    f'Card "{sale.card_title}" sold for ${sale.sale_price:.2f} '
                    f"vs ${median_price_30d:.2f} median (30d). "
                    f"Match method: {sale.player_match_method}."
                ),
                score_snapshot={
                    "sale_price": sale.sale_price,
                    "median_30d": median_price_30d,
                    "discount_pct": discount_pct,
                },
            )

    return None


async def run_alerts(db: AsyncSession) -> int:
    """Compare today's scores to yesterday's and evaluate all alert rules.

    Returns count of alerts generated.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    # Get today's scores
    today_result = await db.execute(
        select(ScoreDaily).where(ScoreDaily.score_date == today)
    )
    today_scores = today_result.scalars().all()

    count = 0
    for score in today_scores:
        # Get yesterday's score
        prev_result = await db.execute(
            select(ScoreDaily).where(
                ScoreDaily.player_id == score.player_id,
                ScoreDaily.score_date == yesterday,
            )
        )
        yesterday_score = prev_result.scalar_one_or_none()

        # Get recent events
        events_result = await db.execute(
            select(PlayerEvent).where(
                PlayerEvent.player_id == score.player_id,
                PlayerEvent.event_date >= yesterday,
            )
        )
        recent_events = events_result.scalars().all()

        # Sales trend
        sales_7d_result = await db.execute(
            select(MarketSale).where(
                MarketSale.player_id == score.player_id,
                MarketSale.sale_date >= today - timedelta(days=7),
            )
        )
        sales_7d = sales_7d_result.scalars().all()
        sales_prior_result = await db.execute(
            select(MarketSale).where(
                MarketSale.player_id == score.player_id,
                MarketSale.sale_date >= today - timedelta(days=14),
                MarketSale.sale_date < today - timedelta(days=7),
            )
        )
        sales_prior = sales_prior_result.scalars().all()

        sales_trend = {
            "count_rising": len(sales_7d) > len(sales_prior),
            "median_rising": (
                median([s.sale_price for s in sales_7d]) > median([s.sale_price for s in sales_prior])
                if sales_7d and sales_prior
                else False
            ),
        }

        # Run all alert checks
        checks = [
            check_breakout_alert(score, yesterday_score),
            check_market_confirmation(score, sales_trend),
            check_supply_risk(score),
            check_exit_risk(score),
            check_watchlist_movement(score, yesterday_score, recent_events),
        ]

        for alert in checks:
            if alert is None:
                continue

            # Deduplicate: no same type+player+date
            existing = await db.execute(
                select(Alert).where(
                    Alert.player_id == alert.player_id,
                    Alert.alert_type == alert.alert_type,
                    Alert.alert_date == alert.alert_date,
                )
            )
            if existing.scalar_one_or_none():
                continue

            db.add(alert)
            logger.info("Alert generated: %s for player %d", alert.alert_type, alert.player_id)
            count += 1

        # Misspelled listing check
        sales_30d_result = await db.execute(
            select(MarketSale).where(
                MarketSale.player_id == score.player_id,
                MarketSale.sale_date >= today - timedelta(days=30),
            )
        )
        sales_30d = sales_30d_result.scalars().all()
        if sales_30d:
            median_30d = median([s.sale_price for s in sales_30d])
            player_result = await db.execute(
                select(Player).where(Player.id == score.player_id)
            )
            player = player_result.scalar_one_or_none()
            if player:
                typo_alert = await check_misspelled_listing_alert(db, player, median_30d)
                if typo_alert:
                    existing = await db.execute(
                        select(Alert).where(
                            Alert.player_id == typo_alert.player_id,
                            Alert.alert_type == typo_alert.alert_type,
                            Alert.alert_date == typo_alert.alert_date,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        db.add(typo_alert)
                        logger.info("Alert generated: misspelled_listing for player %d", player.id)
                        count += 1

    if count:
        await db.commit()

    logger.info("Alert run complete: %d new alerts", count)
    return count
