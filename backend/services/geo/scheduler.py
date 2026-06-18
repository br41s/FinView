"""APScheduler wrapper for periodic geo-intel pipeline cycles (per user)."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import settings

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()
_active_jobs: dict[int, str] = {}  # user_id -> job_id


def start_user_schedule(user_id: int) -> None:
    """Start a periodic geo pipeline job for a user."""
    from backend.services.geo.orchestrator import run_cycle_for_user

    job_id = f"geo_monitor_{user_id}"
    if job_id in _active_jobs.values():
        logger.info("Geo job already running for user %d", user_id)
        return

    _scheduler.add_job(
        run_cycle_for_user,
        "interval",
        minutes=settings.geo_monitor_interval_minutes,
        args=[user_id],
        id=job_id,
        replace_existing=True,
    )
    _active_jobs[user_id] = job_id

    if not _scheduler.running:
        _scheduler.start()

    logger.info(
        "Started geo monitor for user %d (every %d min)",
        user_id, settings.geo_monitor_interval_minutes,
    )


def stop_user_schedule(user_id: int) -> None:
    """Stop the geo pipeline job for a user."""
    job_id = _active_jobs.pop(user_id, None)
    if job_id:
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            pass
        logger.info("Stopped geo monitor for user %d", user_id)


def is_running(user_id: int) -> bool:
    return f"geo_monitor_{user_id}" in _active_jobs.values()


def shutdown_scheduler() -> None:
    """Graceful shutdown of all geo jobs."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Geo APScheduler shut down")
