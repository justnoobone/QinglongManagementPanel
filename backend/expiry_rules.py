"""Date-only expiry rules shared by the API and daily scheduler."""

from datetime import datetime
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo('Asia/Shanghai')


def local_today(now=None):
    return (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ).date()


def parse_date(value):
    if value in (None, ''):
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (TypeError, ValueError) as exc:
        raise ValueError('到期日期必须是 YYYY-MM-DD 格式') from exc


def is_due(end_date, today=None):
    parsed = parse_date(end_date)
    return parsed is not None and parsed <= (today or local_today())


def blocks_start(metadata, today=None):
    """Expired instances require a new future date before manual start.

    Clearing the date cannot unlock a container previously stopped by the
    scheduler; this prevents bypassing the expiry rule by removing the date.
    """
    try:
        parsed = parse_date(metadata.get('end_date'))
    except ValueError:
        # Invalid legacy values must be corrected before a container starts.
        return True
    current = today or local_today()
    if metadata.get('stopped_by_expiry'):
        return parsed is None or parsed <= current
    return parsed is not None and parsed <= current
