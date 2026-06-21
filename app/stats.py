"""Statistics and aggregations for GUI and HTTP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import Database


def _since_minutes(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _since_days(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def relevance_percent(db: Database, minutes: int | None = None, days: int | None = None) -> float:
    if minutes is not None:
        since = _since_minutes(minutes)
    elif days is not None:
        since = _since_days(days)
    else:
        since = "1970-01-01T00:00:00+00:00"
    total = db.count_events_since(since)
    if total == 0:
        return 0.0
    relevant = db.count_events_since(since, relevant_only=True)
    return round(100.0 * relevant / total, 1)


def counters_today(db: Database) -> dict[str, int]:
    total = db.count_events_today()
    relevant = db.count_events_today(relevant_only=True)
    negative = total - relevant
    return {"total": total, "relevant": relevant, "negative": negative}


def disturbance_rate(db: Database, days: int = 7) -> float:
    since = _since_days(days)
    total = db.count_events_since(since)
    if total == 0:
        return 0.0
    disturbers = 0
    for row in db.events_since(since):
        if row["event_type"] in ("disturber", "noise"):
            disturbers += 1
    return round(100.0 * disturbers / total, 1)


def distance_buckets(db: Database, days: int = 7) -> dict[str, int]:
    since = _since_days(days)
    buckets = {"under_10": 0, "10_20": 0, "20_40": 0, "over_40": 0}
    for row in db.events_since(since):
        if row["event_type"] != "lightning" or row["distance_km"] is None:
            continue
        d = float(row["distance_km"])
        if d < 10:
            buckets["under_10"] += 1
        elif d < 20:
            buckets["10_20"] += 1
        elif d <= 40:
            buckets["20_40"] += 1
        else:
            buckets["over_40"] += 1
    return buckets


def hourly_heatmap(db: Database, days: int = 7) -> list[int]:
    since = _since_days(days)
    counts = [0] * 24
    for row in db.events_since(since):
        if not row["relevant"]:
            continue
        ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
        local = ts.astimezone()
        counts[local.hour] += 1
    return counts


def quiet_since(db: Database) -> str | None:
    last = db.last_relevant_event()
    if not last:
        return None
    ts = datetime.fromisoformat(last["ts"].replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
    return format_duration(delta.total_seconds())


def format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def distance_trend(db: Database) -> str:
    """Return rising, falling, or stable based on recent relevant distances."""
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT distance_km FROM events
            WHERE relevant = 1 AND distance_km IS NOT NULL
            ORDER BY ts DESC LIMIT 6
            """
        ).fetchall()
    if len(rows) < 4:
        return "stable"
    recent = [float(r[0]) for r in rows[:3]]
    older = [float(r[0]) for r in rows[3:6]]
    r_avg = sum(recent) / len(recent)
    o_avg = sum(older) / len(older)
    diff = r_avg - o_avg
    if diff < -2:
        return "rising"  # closer = smaller km
    if diff > 2:
        return "falling"
    return "stable"


def snapshot(db: Database, config: dict) -> dict[str, Any]:
    block_mgr_summary = {}
    last = db.last_relevant_event()
    return {
        "counters_today": counters_today(db),
        "windows": {
            "60m": relevance_percent(db, minutes=60),
            "24h": relevance_percent(db, minutes=24 * 60),
            "7d": relevance_percent(db, days=7),
            "365d": relevance_percent(db, days=365),
        },
        "quiet_since": quiet_since(db),
        "sparkline": db.recent_relevant_distances(20),
        "disturbance_rate_7d": disturbance_rate(db),
        "distance_buckets_7d": distance_buckets(db),
        "hourly_heatmap_7d": hourly_heatmap(db),
        "distance_trend": distance_trend(db),
        "last_relevant": dict(last) if last else None,
        "zones": config.get("zones", {}),
    }
