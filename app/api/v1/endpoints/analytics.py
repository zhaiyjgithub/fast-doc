"""Provider analytics endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import CurrentPrincipal, require_doctor
from app.db.session import get_db
from app.models.clinical import Encounter

router = APIRouter(prefix="/analytics", tags=["analytics"])


def utc_iso_week_bounds(now: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    """Return (this_week_start, this_week_end, prev_week_start, prev_week_end) in UTC.

    Week is Monday 00:00 UTC through the following Monday 00:00 UTC (half-open).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + timedelta(days=7)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start
    return week_start, week_end, prev_week_start, prev_week_end


def _pace_from_avg_hours(
    this_avg: float | None, last_avg: float | None
) -> tuple[float | None, Literal["faster", "slower", "same", "unknown"]]:
    if this_avg is None or last_avg is None:
        return None, "unknown"
    if last_avg <= 0:
        return None, "unknown"
    pct = (last_avg - this_avg) / last_avg * 100.0
    if abs(pct) < 0.5:
        return round(pct, 1), "same"
    if pct > 0:
        return round(pct, 1), "faster"
    return round(pct, 1), "slower"


def _throughput_change_percent(this_n: int, last_n: int) -> float | None:
    if last_n <= 0:
        return None
    return round((this_n - last_n) / last_n * 100.0, 1)


def _patient_initials(first_name: str | None, last_name: str | None) -> str:
    """Two-letter style initials for weekly insight avatars."""
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if first and last:
        return (first[0] + last[0]).upper()
    if first:
        return (first[:2] if len(first) >= 2 else first[0]).upper()
    if last:
        return (last[:2] if len(last) >= 2 else last[0]).upper()
    return "?"


class WeeklyRecentPatientOut(BaseModel):
    encounter_id: str
    initials: str


class WeeklyInsightOut(BaseModel):
    """Week-over-week productivity for the authenticated provider."""

    week_start: datetime = Field(description="UTC start of current ISO week (Monday 00:00)")
    week_end: datetime = Field(description="UTC end of current week (exclusive)")
    prev_week_start: datetime
    prev_week_end: datetime
    notes_completed_this_week: int
    notes_completed_last_week: int
    avg_completion_hours_this_week: float | None
    avg_completion_hours_last_week: float | None
    completion_time_change_percent: float | None = Field(
        default=None,
        description="Positive means shorter average completion time vs last week (faster).",
    )
    pace_direction: Literal["faster", "slower", "same", "unknown"]
    notes_throughput_change_percent: float | None = Field(
        default=None,
        description="Week-over-week change in completed-note count; null if last week had 0 notes.",
    )
    recent_completed_patients: list[WeeklyRecentPatientOut] = Field(
        default_factory=list,
        description="Up to 5 most recently completed encounters this week (patient initials).",
    )


@router.get("/weekly-insight", response_model=WeeklyInsightOut)
async def get_weekly_insight(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[CurrentPrincipal, Depends(require_doctor)],
) -> WeeklyInsightOut:
    """Compare this week's completed encounters vs last week for the current provider."""
    if not principal.provider_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provider profile is not linked to this account.",
        )

    try:
        provider_uuid = uuid.UUID(principal.provider_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provider profile is not linked to this account.",
        ) from None

    week_start, week_end, prev_start, prev_end = utc_iso_week_bounds(datetime.now(timezone.utc))

    base_filters = (
        Encounter.provider_id == provider_uuid,
        Encounter.status == "done",
    )

    hours_expr = (
        func.extract("epoch", Encounter.updated_at) - func.extract("epoch", Encounter.created_at)
    ) / 3600.0

    count_this = await db.execute(
        select(func.count())
        .select_from(Encounter)
        .where(
            *base_filters,
            Encounter.updated_at >= week_start,
            Encounter.updated_at < week_end,
        )
    )
    notes_this = int(count_this.scalar_one())

    count_last = await db.execute(
        select(func.count())
        .select_from(Encounter)
        .where(
            *base_filters,
            Encounter.updated_at >= prev_start,
            Encounter.updated_at < prev_end,
        )
    )
    notes_last = int(count_last.scalar_one())

    avg_this_result = await db.execute(
        select(func.avg(hours_expr)).where(
            *base_filters,
            Encounter.updated_at >= week_start,
            Encounter.updated_at < week_end,
        )
    )
    avg_this = avg_this_result.scalar_one_or_none()
    avg_this_f = float(avg_this) if avg_this is not None else None

    avg_last_result = await db.execute(
        select(func.avg(hours_expr)).where(
            *base_filters,
            Encounter.updated_at >= prev_start,
            Encounter.updated_at < prev_end,
        )
    )
    avg_last = avg_last_result.scalar_one_or_none()
    avg_last_f = float(avg_last) if avg_last is not None else None

    pace_pct, pace_dir = _pace_from_avg_hours(avg_this_f, avg_last_f)
    throughput_pct = _throughput_change_percent(notes_this, notes_last)

    recent_stmt = (
        select(Encounter)
        .options(selectinload(Encounter.patient))
        .where(
            *base_filters,
            Encounter.updated_at >= week_start,
            Encounter.updated_at < week_end,
        )
        .order_by(desc(Encounter.updated_at))
        .limit(5)
    )
    recent_result = await db.execute(recent_stmt)
    recent_encounters = recent_result.scalars().all()

    recent_patients: list[WeeklyRecentPatientOut] = []
    for enc in recent_encounters:
        patient = getattr(enc, "patient", None)
        fn = getattr(patient, "first_name", None) if patient is not None else None
        ln = getattr(patient, "last_name", None) if patient is not None else None
        recent_patients.append(
            WeeklyRecentPatientOut(
                encounter_id=str(enc.id),
                initials=_patient_initials(fn, ln),
            )
        )

    return WeeklyInsightOut(
        week_start=week_start,
        week_end=week_end,
        prev_week_start=prev_start,
        prev_week_end=prev_end,
        notes_completed_this_week=notes_this,
        notes_completed_last_week=notes_last,
        avg_completion_hours_this_week=round(avg_this_f, 2) if avg_this_f is not None else None,
        avg_completion_hours_last_week=round(avg_last_f, 2) if avg_last_f is not None else None,
        completion_time_change_percent=pace_pct,
        pace_direction=pace_dir,
        notes_throughput_change_percent=throughput_pct,
        recent_completed_patients=recent_patients,
    )
