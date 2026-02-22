"""
APScheduler task: scrape CMUH data for master data and appointments.

All synchronous Supabase calls are run via asyncio.to_thread() to prevent
blocking the FastAPI event loop while scraping.
"""

import asyncio
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.scrapers.cmuh import CMUHScraper
from app.services.data_writer import (
    get_hospital_id,
    upsert_department,
    upsert_doctor,
    batch_insert_snapshots,
)
from app.services.notification import check_and_notify
from app.database import get_supabase
from app.core.logger import logger

settings = get_settings()

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def run_cmuh_master_data():
    """Scrapes and updates departments, doctors, and full schedule snapshots. Runs 00:00-06:00."""
    logger.info(f"[Scheduler] Starting CMUH master data scrape at {date.today()}")
    scraper = CMUHScraper()
    try:
        hosp_id = await get_hospital_id("CMUH")
        if not hosp_id:
            logger.warning("[Scheduler] CMUH hospital not found in DB.")
            return

        departments = await scraper.fetch_departments()
        logger.info(f"[Scheduler] Found {len(departments)} departments from CMUH website")
        
        # We will also collect snapshots to insert so that off-peak times populate our DB with the full schedule.
        snapshot_rows: list[dict] = []

        for dept in departments:
            if "_" in dept.code:
                continue

            dept_id = await upsert_department(hosp_id, dept)

            try:
                slots = await scraper.fetch_schedule(dept.code)
            except Exception as e:
                logger.warning(f"[Scheduler] Warning: Error scraping dept {dept.code}: {e}")
                continue

            # Optimize finding doctor IDs
            doc_map = {}
            for slot in slots:
                if slot.doctor_no not in doc_map:
                    try:
                        doc_id = await upsert_doctor(hosp_id, dept_id, slot)
                        doc_map[slot.doctor_no] = doc_id
                    except Exception as e:
                        logger.error(f"[Scheduler]   -> Error saving doctor {slot.doctor_name}: {e}")
                        continue
                
                # Append to snapshot rows without doing real-time progress fetches
                doctor_id = doc_map.get(slot.doctor_no)
                if doctor_id:
                    snapshot_rows.append({
                        "doctor_id": doctor_id,
                        "department_id": dept_id,
                        "session_date": str(slot.session_date),
                        "session_type": slot.session_type,
                        "clinic_room": slot.clinic_room or "",
                        "total_quota": slot.total_quota,
                        "current_registered": slot.registered,
                        "current_number": None, # Skip fetching progress during off-peak full scan
                        "is_full": slot.is_full,
                        "status": slot.status,
                    })

        # Batch insert all full-schedule snapshots
        if snapshot_rows:
            try:
                await batch_insert_snapshots(snapshot_rows)
                logger.info(f"[Scheduler] Successfully inserted {len(snapshot_rows)} off-peak schedule snapshots.")
            except Exception as e:
                logger.error(f"[Scheduler] Error batch inserting master snapshots: {e}")

        logger.info("[Scheduler] Master data scrape complete.")
    except Exception as e:
        logger.error(f"[Scheduler] Fatal error in master data: {e}", exc_info=True)
    finally:
        await scraper.close()


async def run_tracked_appointments():
    """Scrapes appointments and clinic progress ONLY for actively tracked targets. Runs 07:00-23:00."""
    logger.info(f"[Scheduler] Starting targeted appointments scrape at {date.today()}")
    scraper = CMUHScraper()
    supabase = get_supabase()
    try:
        hosp_id = await get_hospital_id("CMUH")
        if not hosp_id:
            logger.warning("[Scheduler] CMUH hospital not found in DB.")
            return

        # Fetch all active tracking subscriptions for this hospital
        track_res = await asyncio.to_thread(
            lambda: supabase.table("tracking_subscriptions")
            .select("department_id, doctor_id")
            .execute()
        )
        tracks = track_res.data or []
        
        if not tracks:
            logger.info("[Scheduler] No active trackings found. Skipping targeted scrape.")
            return
            
        # Collect sets of tracked departments and doctors
        tracked_depts = {t["department_id"] for t in tracks if t.get("department_id")}
        tracked_doctors = {t["doctor_id"] for t in tracks if t.get("doctor_id")}

        # If there are tracked doctors without explicit department trackings, we still need
        # to know their departments to scrape them (since scraping is per-department).
        if tracked_doctors:
            doc_dept_res = await asyncio.to_thread(
                lambda: supabase.table("doctors")
                .select("department_id")
                .in_("id", list(tracked_doctors))
                .execute()
            )
            for d in (doc_dept_res.data or []):
                tracked_depts.add(d["department_id"])

        if not tracked_depts:
            logger.info("[Scheduler] No departments resolved from trackings. Skipping.")
            return

        # Fetch department info for the tracked departments
        dept_res = await asyncio.to_thread(
            lambda: supabase.table("departments")
            .select("id, code, name")
            .in_("id", list(tracked_depts))
            .eq("hospital_id", hosp_id)
            .execute()
        )
        departments = dept_res.data or []

        for dept in departments:
            dept_id = dept["id"]
            dept_code = dept["code"]
            is_entire_dept_tracked = dept_id in {t.get("department_id") for t in tracks if t.get("department_id")}

            try:
                slots = await scraper.fetch_schedule(dept_code)
            except Exception:
                continue

            # Pre-fetch doctors for this department
            doc_res = await asyncio.to_thread(
                lambda: supabase.table("doctors")
                .select("id, doctor_no")
                .eq("department_id", dept_id)
                .execute()
            )
            doctor_map = {d["doctor_no"]: d["id"] for d in (doc_res.data or [])}

            snapshot_rows: list[dict] = []

            for slot in slots:
                doctor_id = doctor_map.get(slot.doctor_no)
                if not doctor_id:
                    try:
                        doctor_id = await upsert_doctor(hosp_id, dept_id, slot)
                    except Exception:
                        continue
                        
                # Progress fetching logic:
                # We fetch progress ONLY IF the doctor is individually tracked OR 
                # their entire department is tracked.
                needs_progress = is_entire_dept_tracked or (doctor_id in tracked_doctors)

                try:
                    current_number = None
                    if slot.session_date == date.today() and slot.clinic_room and needs_progress:
                        period_map = {"上午": "1", "下午": "2", "晚上": "3"}
                        period = period_map.get(slot.session_type, "1")
                        try:
                            progress = await scraper.fetch_clinic_progress(slot.clinic_room, period)
                            if progress:
                                current_number = progress.current_number
                        except Exception:
                            pass

                    snapshot_rows.append({
                        "doctor_id": doctor_id,
                        "department_id": dept_id,
                        "session_date": str(slot.session_date),
                        "session_type": slot.session_type,
                        "clinic_room": slot.clinic_room or "",
                        "total_quota": slot.total_quota,
                        "current_registered": slot.registered,
                        "current_number": current_number,
                        "is_full": slot.is_full,
                        "status": slot.status,
                    })
                except Exception as e:
                    logger.error(f"[Scheduler]   -> Error building slot for {slot.doctor_name} in {dept_code}: {e}")

            # Batch insert snapshots
            if snapshot_rows:
                try:
                    await batch_insert_snapshots(snapshot_rows)
                except Exception as e:
                    logger.error(f"[Scheduler] Error batch inserting snapshots for {dept_code}: {e}")

        logger.info("[Scheduler] Targeted appointments scrape complete. Running notification checks...")
        await check_and_notify()
        logger.info("[Scheduler] Targeted Notification cycle done.")

    except Exception as e:
        logger.error(f"[Scheduler] Fatal error in tracked appointments: {e}", exc_info=True)
    finally:
        await scraper.close()


def start_scheduler():
    scheduler = get_scheduler()
    interval = settings.scrape_interval_minutes

    scheduler.add_job(
        run_cmuh_master_data,
        trigger=CronTrigger(hour='0-6', minute=f'*/{interval}'),
        id="cmuh_master_data",
        name="CMUH Master Data Scraper",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        run_tracked_appointments,
        trigger=CronTrigger(hour='7-23', minute=f'*/{interval}'),
        id="cmuh_appointments",
        name="CMUH Appointments Scraper (Tracked)",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(f"[Scheduler] Started. Master Data: 00-06 h. Appointments(Tracked): 07-23 h. Interval: {interval}m.")
    return scheduler


def stop_scheduler():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")
