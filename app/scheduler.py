"""
APScheduler task: scrape CMUH data for master data and appointments.

All synchronous Supabase calls are run via asyncio.to_thread() to prevent
blocking the FastAPI event loop while scraping.
"""

import asyncio
import random
from datetime import date, datetime, time, timedelta

from app.core.timezone import now_tw, today_tw, today_tw_str, now_utc_str

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.scrapers.cmuh import CMUHScraper, CMUHHsinchuScraper
from app.scrapers.hmmh import HMMHScraper
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
    logger.info(f"[Scheduler] Starting master data scrape at {today_tw()}")
    scrapers = [CMUHScraper(), CMUHHsinchuScraper(), HMMHScraper()]
    
    # Run scrapers for different hospitals concurrently
    await asyncio.gather(*[_scrape_hospital_master_data(s) for s in scrapers])
    logger.info("[Scheduler] Master data scrape complete for all hospitals.")

async def run_morning_tracked_snapshot_sync():
    """Triggered at 08:00 AM to update progress for all currently tracked clinics for today."""
    logger.info(f"[Scheduler] Starting 08:00 AM tracked snapshot sync for {today_tw()}")
    scrapers = [CMUHScraper(), CMUHHsinchuScraper(), HMMHScraper()]
    await asyncio.gather(*[_sync_hospital_morning_progress(s) for s in scrapers])
    logger.info("[Scheduler] 08:00 AM tracked snapshot sync complete.")

async def _sync_hospital_morning_progress(scraper):
    """Worker to perform a full progress scrape for a single hospital's current-day clinics."""
    try:
        hosp_id = await get_hospital_id(scraper.HOSPITAL_CODE)
        if not hosp_id: return

        # Fetch tracked appointments for today for this hospital
        supabase = get_supabase()
        today_str = str(date.today())
        
        # 1. Get tracked doctor_ids for today
        tracking_res = await asyncio.to_thread(
            lambda: supabase.table("tracking")
            .select("doctor_id")
            .eq("session_date", today_str)
            .eq("is_active", True)
            .execute()
        )
        tracked_doctor_ids = list(set([t["doctor_id"] for t in (tracking_res.data or [])]))
        
        if not tracked_doctor_ids:
            logger.info(f"[Scheduler] No tracked appointments found for today. Skipping morning sync for {scraper.HOSPITAL_CODE}.")
            return

        # 2. Fetch latest snapshots for these doctors today
        res = await asyncio.to_thread(
            lambda: supabase.table("appointment_snapshots")
            .select("*, doctors(doctor_no, name), departments(code)")
            .in_("doctor_id", tracked_doctor_ids)
            .eq("session_date", today_str)
            .execute()
        )
        
        snapshots = res.data or []
        if not snapshots:
            logger.info(f"[Scheduler] No existing snapshots found for tracked doctors today. Skipping morning sync for {scraper.HOSPITAL_CODE}.")
            return

        logger.info(f"[Scheduler] Syncing {len(snapshots)} tracked morning snapshots for {scraper.HOSPITAL_CODE}")
        
        updated_rows = []
        for snap in snapshots:
            dept_code = snap.get("departments", {}).get("code")
            doc_no = snap.get("doctors", {}).get("doctor_no")
            doc_name = snap.get("doctors", {}).get("name")
            room = snap.get("clinic_room")
            session_type = snap.get("session_type")
            
            if not (dept_code and doc_no and room): continue

            # Create a mock Slot to use existing _build_snapshot_row logic
            from .scrapers.base import DoctorSlot
            slot = DoctorSlot(
                doctor_no=doc_no,
                doctor_name=doc_name or "",
                department_code=dept_code,
                session_date=date.today(),
                session_type=session_type,
                total_quota=snap.get("total_quota"),
                registered=snap.get("current_registered"),
                clinic_room=room,
                is_full=snap.get("is_full", False)
            )

            # Force fetch progress by setting needs_progress=True
            row = await _build_snapshot_row(scraper, slot, snap["doctor_id"], snap["department_id"], True)
            if row:
                updated_rows.append(row)
            
            # Tiny delay to avoid rate limiting
            await asyncio.sleep(0.1)

        if updated_rows:
            await batch_insert_snapshots(updated_rows)
            
    except Exception as e:
        logger.error(f"[Scheduler] Error in morning sync for {scraper.HOSPITAL_CODE}: {e}", exc_info=True)
    finally:
        await scraper.close()

async def _scrape_hospital_master_data(scraper):
    """Worker to scrape master data for a single hospital with concurrency and delays."""
    import random
    try:
        hosp_id = await get_hospital_id(scraper.HOSPITAL_CODE)
        if not hosp_id:
            logger.warning(f"[Scheduler] {scraper.HOSPITAL_CODE} hospital not found in DB.")
            return

        departments = await scraper.fetch_departments()
        logger.info(f"[Scheduler] Found {len(departments)} departments from {scraper.HOSPITAL_CODE} website")
        
        # We will also collect snapshots to insert so that off-peak times populate our DB with the full schedule.
        snapshot_rows: list[dict] = []

        for dept in departments:
            if "_" in dept.code:
                continue

            dept_id = await upsert_department(hosp_id, dept)

            try:
                # Add a small delay between departments to avoid overloading the server
                await asyncio.sleep(random.uniform(1.0, 3.0))
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
                        "scraped_at": now_utc_str(),
                    })

        # Batch insert all full-schedule snapshots for this hospital
        if snapshot_rows:
            try:
                await batch_insert_snapshots(snapshot_rows)
                logger.info(f"[Scheduler] Successfully inserted {len(snapshot_rows)} off-peak schedule snapshots for {scraper.HOSPITAL_CODE}.")
            except Exception as e:
                logger.error(f"[Scheduler] Error batch inserting master snapshots for {scraper.HOSPITAL_CODE}: {e}")

        logger.info(f"[Scheduler] Master data scrape complete for {scraper.HOSPITAL_CODE}.")
    except Exception as e:
        logger.error(f"[Scheduler] Fatal error in master data for {scraper.HOSPITAL_CODE}: {e}", exc_info=True)
    finally:
        await scraper.close()


async def run_tracked_appointments():
    """Scrapes appointments and clinic progress ONLY for actively tracked targets. Runs 07:00-23:00."""
    logger.info(f"[Scheduler] Starting targeted appointments scrape at {date.today()}")
    scrapers = [CMUHScraper(), CMUHHsinchuScraper(), HMMHScraper()]
    
    # Run tracked scrapes for different hospitals concurrently
    await asyncio.gather(*[_scrape_hospital_tracked_data(s) for s in scrapers])

    logger.info("[Scheduler] Targeted appointments scrape complete. Running notification checks...")
    await check_and_notify()
    logger.info("[Scheduler] Targeted Notification cycle done.")

async def _scrape_hospital_tracked_data(scraper):
    """Worker to scrape tracked appointments for a single hospital."""
    supabase = get_supabase()
    try:
        hosp_id = await get_hospital_id(scraper.HOSPITAL_CODE)
        if not hosp_id:
            logger.warning(f"[Scheduler] {scraper.HOSPITAL_CODE} hospital not found in DB.")
            return

        # Fetch all active tracking subscriptions for this hospital
        track_res = await asyncio.to_thread(
            lambda: supabase.table("tracking_subscriptions")
            .select("department_id, doctor_id")
            .execute()
        )
        tracks = track_res.data or []
        
        if not tracks:
            logger.info(f"[Scheduler] No active trackings found for {scraper.HOSPITAL_CODE}. Skipping targeted scrape.")
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
                # Note: Do NOT filter by hospital_id here — tracked doctors may belong
                # to a different hospital entity than this scraper's hospital.
                # The dept filter below (line ~265) ensures each scraper only
                # scrapes its own hospital's departments.
                .execute()
            )
            for d in (doc_dept_res.data or []):
                tracked_depts.add(d["department_id"])


        if not tracked_depts:
            logger.info(f"[Scheduler] No departments resolved from trackings for {scraper.HOSPITAL_CODE}. Skipping.")
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
        
        # Keep track of which doctors we've already scraped in this cycle
        scraped_doctor_ids = set()
        all_snapshot_rows = []

        # 1. Scrape by Department
        logger.info(f"[Scheduler] Scraping {len(departments)} departments for {scraper.HOSPITAL_CODE}")
        for dept in departments:
            dept_id = dept["id"]
            dept_code = dept["code"]
            dept_name = dept.get("name", "Unknown")
            is_entire_dept_tracked = dept_id in {t.get("department_id") for t in tracks if t.get("department_id")}

            logger.info(f"[Scheduler] Processing department {dept_name} ({dept_code}) for {scraper.HOSPITAL_CODE}")

            try:
                # Add a small delay between departments
                await asyncio.sleep(0.5)
                slots = await scraper.fetch_schedule(dept_code)
            except Exception:
                continue

            # Pre-fetch doctors for this department to map doctor_no to doc_id
            doc_res = await asyncio.to_thread(
                lambda: supabase.table("doctors")
                .select("id, doctor_no")
                .eq("department_id", dept_id)
                .execute()
            )
            doctor_map = {d["doctor_no"]: d["id"] for d in (doc_res.data or [])}

            for slot in slots:
                doctor_id = doctor_map.get(slot.doctor_no)
                if not doctor_id:
                    try:
                        doctor_id = await upsert_doctor(hosp_id, dept_id, slot)
                    except Exception:
                        continue
                
                scraped_doctor_ids.add(doctor_id)
                
                # Check if this specific slot needs real-time progress
                needs_progress = is_entire_dept_tracked or (doctor_id in tracked_doctors)
                
                row = await _build_snapshot_row(scraper, slot, doctor_id, dept_id, needs_progress)
                if row:
                    all_snapshot_rows.append(row)

        # 2. Individual Doctor Supplement
        missing_doctors = tracked_doctors - scraped_doctor_ids
        if missing_doctors:
            logger.info(f"[Scheduler] {len(missing_doctors)} tracked doctors missing from dept schedules for {scraper.HOSPITAL_CODE}. Fetching individually...")
            missing_ids = [str(mid) for mid in missing_doctors]
            logger.info(f"[Scheduler] DEBUG: Querying doctors table for IDs: {missing_ids}")
            
            try:
                doc_info_res = await asyncio.to_thread(
                    lambda: supabase.table("doctors")
                    .select("id, name, doctor_no, department_id, departments(code)")
                    .in_("id", missing_ids)
                    # Note: Do NOT filter by hospital_id here — tracked doctors may belong
                    # to a different hospital entity (e.g. CMUH_HS doctor queried by CMUHScraper).
                    .execute()
                )
                logger.info(f"[Scheduler] DEBUG: Query returned {len(doc_info_res.data or [])} results")

            except Exception as e:
                logger.error(f"[Scheduler] Error querying doctors for supplement: {e}")
                doc_info_res = None
            
            for d in (doc_info_res.data or []):
                doc_id = d["id"]
                doc_no = d["doctor_no"]
                doc_name = d["name"]
                dept_id = d["department_id"]
                dept_code = d.get("departments", {}).get("code") if d.get("departments") else None
                
                if not dept_code: continue
                
                try:
                    logger.info(f"[Scheduler] DEBUG: Fetching slots for {doc_name} ({doc_no})")
                    await asyncio.sleep(0.5)
                    slots = await scraper._fetch_doctor_slots(doc_no, doc_name, dept_code)
                    logger.info(f"[Scheduler] DEBUG: Found {len(slots)} slots for {doc_name}")
                    for slot in slots:
                        row = await _build_snapshot_row(scraper, slot, doc_id, dept_id, True)
                        if row:
                            all_snapshot_rows.append(row)
                except Exception as e:
                    logger.error(f"[Scheduler] Error supplement-fetching doctor {doc_name}: {e}")

        # Batch insert all gathered snapshots
        if all_snapshot_rows:
            try:
                await batch_insert_snapshots(all_snapshot_rows)
            except Exception as e:
                logger.error(f"[Scheduler] Error batch inserting snapshots for {scraper.HOSPITAL_CODE}: {e}")

    except Exception as e:
        logger.error(f"[Scheduler] Fatal error in tracked appointments for {scraper.HOSPITAL_CODE}: {e}", exc_info=True)
    finally:
        await scraper.close()


async def _build_snapshot_row(scraper, slot, doctor_id, dept_id, needs_progress) -> dict | None:
    """Helper to build a snapshot row with session-aware progress fetching."""
    try:
        current_number = slot.current_number 
        registered_count = slot.registered
        total_quota = slot.total_quota
        status = slot.status
        waiting_list = []
        clinic_queue_details = []

        # User's dynamic time gates for real-time progress (current_number):
        # 上午診: 08:00-16:00 (8 hours)
        # 下午診: 13:30-21:30 (8 hours)
        # 晚上診: 18:00-02:00 (8 hours, next day)
        # For non-today sessions (e.g., future tracked appointments), we still upsert
        # the current_registered (headcount) so the dashboard stays up to date.
        # We just skip the real-time progress fetch (current_number).
        
        now = now_tw()
        is_today = slot.session_date == today_tw()

        should_fetch_realtime = False
        if is_today and needs_progress:
            # Define session start times
            session_start_times = {
                "上午": time(8, 0),      # 08:00
                "下午": time(13, 30),   # 13:30
                "晚上": time(18, 0),    # 18:00
            }
            
            # Check if current session type is within its scheduled window
            if slot.session_type in session_start_times:
                start_time = session_start_times[slot.session_type]
                session_start_dt = datetime.combine(slot.session_date, start_time)
                session_end_dt = session_start_dt + timedelta(hours=8)
                
                # Only fetch realtime if we're between session start and 8 hours later
                if now >= session_start_dt and now < session_end_dt:
                    should_fetch_realtime = True

        # If it's time to fetch real-time progress
        if should_fetch_realtime and slot.clinic_room:
            period_map = {"上午": "1", "下午": "2", "晚上": "3"}
            period = period_map.get(slot.session_type, "1")
            try:
                logger.debug(f"[Scheduler] Fetching realtime for {slot.clinic_room}診 period={period}")
                progress = await scraper.fetch_clinic_progress(slot.clinic_room, period)
                if progress:
                    logger.debug(f"[Scheduler] Got progress: current_number={progress.current_number}, queue_items={len(progress.clinic_queue_details) if progress.clinic_queue_details else 0}")
                    current_number = progress.current_number
                    # Standardized: registered_count = Headcount (人數), total_quota = Max Number (總號)
                    if progress.registered_count:
                        registered_count = progress.registered_count # Headcount
                    if progress.total_quota:
                        total_quota = progress.total_quota         # Max Number
                    if progress.status:
                        status = progress.status
                    if progress.waiting_list:
                        waiting_list = progress.waiting_list
                    if progress.clinic_queue_details:
                        clinic_queue_details = progress.clinic_queue_details
                        logger.debug(f"[Scheduler] Set clinic_queue_details: {len(clinic_queue_details)} items")
            except Exception as e:
                logger.error(f"[Scheduler] Error fetching realtime for {slot.clinic_room}診: {e}")


        row = {
            "doctor_id": doctor_id,
            "department_id": dept_id,
            "session_date": str(slot.session_date),
            "session_type": slot.session_type,
            "clinic_room": slot.clinic_room or "",
            "current_registered": registered_count,
            "is_full": slot.is_full,
            "status": status,
            "scraped_at": now_utc_str(),
        }
        # Only write current_number / total_quota / waiting_list / clinic_queue_details if we actually have values.
        # This prevents the排班 (schedule) UPSERT from overwriting previously scraped
        # real-time progress data with null values when the clinic hasn't opened yet.
        if current_number is not None:
            row["current_number"] = current_number
        if total_quota is not None:
            row["total_quota"] = total_quota
        if waiting_list:
            row["waiting_list"] = waiting_list
        if clinic_queue_details:
            row["clinic_queue_details"] = clinic_queue_details
        return row

    except Exception as e:
        logger.error(f"[Scheduler] Error building snapshot row for {slot.doctor_name}: {e}")
        return None


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
        run_morning_tracked_snapshot_sync,
        trigger=CronTrigger(hour=8, minute=0),
        id="morning_tracked_sync",
        name="Morning Tracked Snapshot Sync",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        run_tracked_appointments,
        trigger=CronTrigger(hour='6-23,0-2', minute=f'*/{interval}'),
        id="cmuh_appointments",
        name="CMUH Appointments Scraper (Tracked)",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(f"[Scheduler] Started. Master Data: 00-06 h. Morning Sync: 08:00. Appointments(Tracked): 06-02 h (next day). Interval: {interval}m.")
    return scheduler


def stop_scheduler():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")
