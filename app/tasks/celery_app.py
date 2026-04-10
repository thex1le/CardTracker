from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery = Celery(
    "cardscout",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.prospect_tasks",
        "app.tasks.signal_tasks",
        "app.tasks.card_tasks",
        "app.tasks.news_tasks",
    ],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="US/Eastern",
    enable_utc=True,
    beat_schedule={
        "refresh-prospects-daily": {
            "task": "app.tasks.prospect_tasks.refresh_prospects_task",
            "schedule": crontab(hour=6, minute=0),  # 6 AM ET
        },
        "detect-signals-daily": {
            "task": "app.tasks.signal_tasks.detect_all_signals_task",
            "schedule": crontab(hour=7, minute=0),  # 7 AM ET, after prospects
        },
        "refresh-statcast-weekly": {
            "task": "app.tasks.signal_tasks.refresh_statcast_task",
            "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
        },
        "refresh-card-prices-daily": {
            "task": "app.tasks.card_tasks.refresh_all_card_prices_task",
            "schedule": crontab(hour=9, minute=0),  # 9 AM ET
        },
        "refresh-news-every-4h": {
            "task": "app.tasks.news_tasks.refresh_news_task",
            "schedule": crontab(minute=0, hour="*/4"),  # Every 4 hours
        },
    },
)
