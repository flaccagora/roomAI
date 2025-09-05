from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import os
import logging
from datetime import timedelta, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path

from backend.run_pipeline import run_pipeline, analyze_pending
from backend.database import DB
from backend.scraper import Scraper

logging.basicConfig(level=logging.INFO)

app = FastAPI(title='Pipeline Scheduler')
db = DB()
LAST_RUN_TIME = None  # ISO-like string used for next scheduled run start (persisted)

# Serve the simple frontend from ./static
static_dir = Path(__file__).parent / 'static'
if not static_dir.exists():
    static_dir.mkdir(exist_ok=True)
app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')


@app.get('/', response_class=HTMLResponse)
def root():
    index = static_dir / 'index.html'
    if index.exists():
        return index.read_text(encoding='utf-8')
    return HTMLResponse('<h1>Pipeline Scheduler</h1><p>No frontend installed.</p>')


class NotifyConfig(BaseModel):
    webhook: Optional[str] = None


scheduler = BackgroundScheduler()
scheduler.start()

# Keep last seen ids to notify only on new goods
LAST_SEEN_IDS = set()  # persisted via DB (initialized at startup from good_facebook_posts)


def notify_new_items(new_items, webhook_url=None):
    if not new_items:
        return
    # Simple notification: either POST to webhook URL with JSON or log
    payload = {
        'new_good_count': len(new_items),
        'ids': [i.get('id') for i in new_items],
        'samples': [i.get('text')[:200] for i in new_items]
    }
    if webhook_url:
        try:
            import requests
            requests.post(webhook_url, json=payload, timeout=10)
            logging.info('Notified webhook %s about %d new items', webhook_url, len(new_items))
        except Exception as e:
            logging.exception('Failed to notify webhook: %s', e)
    else:
        logging.info('New good items found: %s', payload)


def _normalize_start_time(ts: str | None) -> str | None:
    """Normalize various input formats (from UI) to include seconds and .000 ms if missing."""
    if not ts:
        return None
    try:
        # Already full ISO with seconds
        if len(ts) >= 19 and ts[10] == 'T':
            # ensure .000
            if '.' not in ts:
                return ts[:19] + '.000'
            return ts
        # HTML datetime-local like YYYY-MM-DDTHH:MM
        if len(ts) == 16 and ts[10] == 'T':
            return ts + ':00.000'
    except Exception:
        pass
    return ts


def scheduled_run(webhook_url=None, start_time: str | None = None):
    logging.info('Scheduled run starting...')
    global LAST_RUN_TIME
    # For scheduled runs: use provided start_time override or fallback to LAST_RUN_TIME
    eff_start = _normalize_start_time(start_time) or LAST_RUN_TIME
    new_good = run_pipeline(start_time=eff_start)
    # filter only items not seen before
    global LAST_SEEN_IDS
    unseen = [i for i in new_good if i.get('id') not in LAST_SEEN_IDS]
    if unseen:
        notify_new_items(unseen, webhook_url=webhook_url)
        for i in unseen:
            LAST_SEEN_IDS.add(i.get('id'))
    else:
        logging.info('No new accepted items since last run')
    # After a successful run, set LAST_RUN_TIME to now for the next iteration
    try:
        from datetime import datetime
        LAST_RUN_TIME = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000')
        # persist
        db.set_last_run_time(LAST_RUN_TIME)
        db.upsert_scheduler_config(
            last_scrape_time_from=eff_start,
        )

    except Exception:
        pass


def analyze_pending_run(webhook_url=None):
    logging.info('Analyze-pending run starting...')
    new_good = analyze_pending()
    global LAST_SEEN_IDS
    unseen = [i for i in new_good if i.get('id') not in LAST_SEEN_IDS]
    if unseen:
        notify_new_items(unseen, webhook_url=webhook_url)
        for i in unseen:
            LAST_SEEN_IDS.add(i.get('id'))
    else:
        logging.info('No new accepted items from pending analysis')


def _schedule_day_night(minutes_day: int | None, minutes_night: int | None, day_start_hour: int, night_start_hour: int, webhook: str | None):
    """Configure day/night cron jobs based on provided minutes and hour boundaries.
    Removes any existing day/night jobs and creates new ones for the provided windows.
    """
    # Clear any existing jobs
    for jid in ('pipeline_job', 'pipeline_job_day', 'pipeline_job_night'):
        try:
            scheduler.remove_job(jid)
        except Exception:
            pass

    def add_cron_job(job_id: str, minute_step: int, hours_expr: str):
        trig = CronTrigger(minute=f'*/{int(minute_step)}', hour=hours_expr)
        scheduler.add_job(lambda: scheduled_run(webhook_url=webhook), trigger=trig, id=job_id)

    # Determine hour expressions from boundaries
    # Day window: [day_start_hour, night_start_hour)
    # Night window: [night_start_hour, 24) U [0, day_start_hour)
    if minutes_day:
        if day_start_hour < night_start_hour:
            day_hours = f"{day_start_hour}-{night_start_hour-1}"
        else:
            # degenerate, treat as full day if misconfigured
            day_hours = "0-23"
        add_cron_job('pipeline_job_day', int(minutes_day), day_hours)

    if minutes_night:
        if night_start_hour < day_start_hour:
            night_hours = f"{night_start_hour}-23,0-{day_start_hour-1}"
        else:
            night_hours = f"{night_start_hour}-23,0-{max(0, day_start_hour-1)}"
        add_cron_job('pipeline_job_night', int(minutes_night), night_hours)


@app.on_event('startup')
def startup():
    """Restore persisted scheduler state and seen IDs."""
    global LAST_RUN_TIME, LAST_SEEN_IDS
    try:
        # Restore last run time
        LAST_RUN_TIME = db.get_last_run_time()
    except Exception:
        LAST_RUN_TIME = None

    try:
        # Initialize seen ids from accepted posts
        LAST_SEEN_IDS = set(db.fetch_good_ids())
    except Exception:
        LAST_SEEN_IDS = set()

    # Restore scheduled job(s) if persisted as active
    try:
        cfg = db.get_scheduler_config()
        webhook = cfg.get('webhook')
        minutes = cfg.get('minutes')
        minutes_day = cfg.get('minutes_day')
        minutes_night = cfg.get('minutes_night')
        day_start_hour = int(cfg.get('day_start_hour') or 8)
        night_start_hour = int(cfg.get('night_start_hour') or 20)

        if cfg.get('active'):
            if minutes_day or minutes_night:
                _schedule_day_night(minutes_day, minutes_night, day_start_hour, night_start_hour, webhook)
                logging.info('Restored day/night schedule: day=%s min, night=%s min, day_start=%d, night_start=%d', minutes_day, minutes_night, day_start_hour, night_start_hour)
            elif minutes:
                try:
                    scheduler.remove_job('pipeline_job')
                except Exception:
                    pass
                scheduler.add_job(lambda: scheduled_run(webhook_url=webhook), 'interval', minutes=int(minutes), id='pipeline_job')
                logging.info('Restored single interval schedule: every %d minutes, webhook=%s', int(minutes), webhook)
    except Exception as e:
        logging.exception('Failed to restore scheduler state: %s', e)


@app.on_event('shutdown')
def shutdown():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    try:
        db.close()
    except Exception:
        pass


@app.post('/start_every')
def start_every(minutes: int | None = 30, day_minutes: int | None = None, night_minutes: int | None = None,
                day_start_hour: int = 8, night_start_hour: int = 20, cfg: NotifyConfig = None):
    """Start scheduling the pipeline every `minutes` minutes. Optionally give JSON {"webhook": "https://..."} to notify."""
    webhook = cfg.webhook if cfg else None
    # remove existing job if present
    try:
        scheduler.remove_job('pipeline_job')
    except Exception:
        pass
    # If day/night provided, schedule those, else simple interval
    if day_minutes or night_minutes:
        _schedule_day_night(day_minutes, night_minutes, int(day_start_hour), int(night_start_hour), webhook)
    else:
        scheduler.add_job(lambda: scheduled_run(webhook_url=webhook), 'interval', minutes=int(minutes or 30), id='pipeline_job')
    # Initialize LAST_RUN_TIME so that the first scheduled run uses 'now' as a baseline
    global LAST_RUN_TIME
    try:
        db.upsert_scheduler_config(
            active=1,
            minutes=int(minutes) if minutes is not None else None,
            webhook=webhook,
            last_run_time=LAST_RUN_TIME,
            minutes_day=int(day_minutes) if day_minutes is not None else None,
            minutes_night=int(night_minutes) if night_minutes is not None else None,
            day_start_hour=int(day_start_hour),
            night_start_hour=int(night_start_hour),
        )
    except Exception:
        LAST_RUN_TIME = None
    # read back next run time
    jobs = scheduler.get_jobs()
    nexts = {}
    for j in jobs:
        if j.id in ('pipeline_job', 'pipeline_job_day', 'pipeline_job_night'):
            try:
                nexts[j.id] = j.next_run_time.isoformat() if j.next_run_time else None
            except Exception:
                nexts[j.id] = None
    return {
        'status': 'scheduled',
        'every_minutes': minutes,
        'day_minutes': day_minutes,
        'night_minutes': night_minutes,
        'day_start_hour': day_start_hour,
        'night_start_hour': night_start_hour,
        'webhook': webhook,
        'next_runs': nexts
    }


@app.post('/run_now')
def run_now(background_tasks: BackgroundTasks, start_time: str | None = None, cfg: NotifyConfig = None):
    webhook = cfg.webhook if cfg else None
    # Use provided start_time if given (from UI), else fallback to LAST_RUN_TIME
    start_time = _normalize_start_time(start_time) or LAST_RUN_TIME
    background_tasks.add_task(scheduled_run, webhook, start_time)
    return {'status': 'scheduled_now', 'webhook': webhook, 'start_time': start_time}


@app.post('/analyze_pending')
def analyze_pending_endpoint(background_tasks: BackgroundTasks, cfg: NotifyConfig = None):
    """Analyze only posts with NULL status in background. Optional JSON {"webhook": "https://..."}."""
    webhook = cfg.webhook if cfg else None
    background_tasks.add_task(analyze_pending_run, webhook)
    return {'status': 'analyze_pending_scheduled', 'webhook': webhook}

@app.post('/populate_db')
def populate_db():
    start_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000')
    scraper = Scraper(start_time=start_time)
    runs = ["wQhVk1oOIFHBKpN24"]
    
    for run in runs:
        items = scraper.get_run_items(run)
        db.add_items_to_db(items)
    return {'status': 'populated_db'}

@app.get('/status')
def status():
    jobs = scheduler.get_jobs()
    info = {'jobs': [j.id for j in jobs], 'last_run_time': LAST_RUN_TIME}
    job = next((j for j in jobs if j.id == 'pipeline_job'), None)
    if job is not None:
        try:
            next_run_at = job.next_run_time.isoformat() if job.next_run_time else None
        except Exception:
            next_run_at = None
        every_minutes = None
        try:
            # IntervalTrigger has .interval as a timedelta
            trig = getattr(job, 'trigger', None)
            interval = getattr(trig, 'interval', None)
            if isinstance(interval, timedelta):
                every_minutes = int(interval.total_seconds() // 60)
        except Exception:
            pass
        info.update({'next_run_at': next_run_at, 'every_minutes': every_minutes})
    # include persisted config snapshot and next runs for day/night jobs
    try:
        info.update({'persisted': db.get_scheduler_config()})
        for jid in ('pipeline_job_day', 'pipeline_job_night'):
            j = scheduler.get_job(jid)
            if j is not None:
                try:
                    info[f'next_{jid}'] = j.next_run_time.isoformat() if j.next_run_time else None
                except Exception:
                    info[f'next_{jid}'] = None
    except Exception:
        pass
    return info


@app.post('/cancel')
def cancel():
    """Cancel the scheduled pipeline job (if present)."""
    removed_any = False
    for jid in ('pipeline_job', 'pipeline_job_day', 'pipeline_job_night'):
        try:
            scheduler.remove_job(jid)
            removed_any = True
        except Exception:
            pass
    if removed_any:
        db.upsert_scheduler_config(active=0)
        return {'status': 'cancelled'}
    else:
        return {'status': 'no_job'}


@app.get('/posts')
def get_posts(table: str = 'facebook_posts', limit: int = 50, offset: int = 0, search: Optional[str] = None):
    """List posts from the database. Table can be 'facebook_posts' or 'good_facebook_posts'.
    Supports optional text search (on `text`), limit and offset.
    """
    items = db.fetch_items(table=table, limit=limit, offset=offset, search=search)
    return { 'count': len(items), 'items': items }
