from datetime import date, datetime, timedelta


def days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


def utcnow() -> datetime:
    return datetime.utcnow()
