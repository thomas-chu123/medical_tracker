"""
Notification orchestration service.
Checks active tracking subscriptions against the latest appointment snapshots
and fires email/LINE alerts when thresholds are crossed.

All Supabase calls are wrapped with asyncio.to_thread() to avoid blocking
the FastAPI event loop.
"""

import asyncio

from app.database import get_supabase
from app.services.email_service import send_email, build_clinic_alert_email
from app.services.line_message_api import send_line_message, build_line_message
from app.core.logger import logger as log
from app.core.timezone import today_tw_str, now_tw


def _run(fn):
    """Run a synchronous Supabase call in a thread pool executor."""
    return asyncio.to_thread(fn)


async def check_and_notify():
    """Main notification loop: called after each scrape cycle."""
    supabase = get_supabase()
    today = today_tw_str()  # Use Taiwan timezone to get correct local date
    log.info(f"[Notification] Starting check_and_notify for {today}")

    # Fetch all active subscriptions for today (non-blocking)
    subs_res = await _run(
        lambda: supabase.table("tracking_subscriptions")
        .select(
            "*, "
            "doctors(name, doctor_no, hospital_id), "
            "departments(name)"
        )
        .eq("is_active", True)
        .eq("session_date", today)
        .execute()
    )

    for sub in subs_res.data or []:
        log.info(f"[Notification] Processing sub={sub.get('id','?')[:8]} doctor={sub.get('doctor_id','?')[:8]} session={sub.get('session_date')} {sub.get('session_type')}")
        await _process_subscription(supabase, sub)


async def _process_subscription(supabase, sub: dict):
    """Evaluate one subscription and send notifications if needed."""
    doctor_id = sub["doctor_id"]
    session_type = sub.get("session_type")

    # Build query for latest snapshot
    tw_today = today_tw_str()  # Taiwan date to match session_date format
    def _fetch_snap():
        q = (
            supabase.table("appointment_snapshots")
            .select("*")
            .eq("doctor_id", doctor_id)
            .eq("session_date", tw_today)  # Use Taiwan date (not UTC date)
            .order("scraped_at", desc=True)
            .limit(1)
        )
        if session_type:
            q = q.eq("session_type", session_type)
        return q.execute()

    snap_res = await _run(_fetch_snap)
    sub_id_short = sub.get("id", "?")[:8]
    doctor_id_short = str(doctor_id)[:8]
    if not snap_res.data:
        log.info(f"[Notification] sub={sub_id_short} doc={doctor_id_short} ({session_type}): no snapshot found for {tw_today}")
        return

    snap = snap_res.data[0]
    current_number = snap.get("current_number")
    total_quota = snap.get("total_quota")
    waiting_list = snap.get("waiting_list") or []
    clinic_queue_details = snap.get("clinic_queue_details") or []

    if current_number is None:
        log.info(f"[Notification] sub={sub_id_short} doc={doctor_id_short}: current_number is None, skipping")
        return

    # Use appointment_number if set by user, fallback to 999 (should not happen in practice)
    target_number = sub.get("appointment_number")
    if target_number is None:
        # If no target number, we can't calculate waiting list ahead of user. 
        # Fallback to total headcount vs current number to keep some level of notification?
        # Standard: target_number = total_quota or 0
        target_number = total_quota or 0

    # Calculate remaining people BETWEEN current_number and target_number
    # Using clinic_queue_details with status check (exclude "完成")
    if clinic_queue_details:
        # Count items where: number > current_number AND number < target_number AND status != "完成"
        remaining = len([
            item for item in clinic_queue_details
            if item.get("number", 0) > current_number 
            and item.get("number", 0) < target_number 
            and item.get("status") != "完成"
        ])
        # If user's number is already past current, no one is ahead
        if current_number >= target_number:
            remaining = 0
    elif waiting_list:
        # Fallback to waiting_list if clinic_queue_details is missing
        remaining = len([x for x in waiting_list if x < target_number])
        if current_number > target_number:
            remaining = 0
    else:
        # Last resort: simple calculation
        remaining = max(0, target_number - current_number)

    # Build context for notifications
    doctor_name = (sub.get("doctors") or {}).get("name", "未知醫師")
    dept_name = (sub.get("departments") or {}).get("name", "未知科別")
    session_date_str = tw_today  # Use Taiwan date for display
    session_type_str = sub.get("session_type", "")
    clinic_room = snap.get("clinic_room", "未提供")

    # Fetch hospital name
    hospital_id = (sub.get("doctors") or {}).get("hospital_id")
    hospital_name = "未知醫院"
    if hospital_id:
        hosp_res = await _run(
            lambda: supabase.table("hospitals").select("name").eq("id", hospital_id).maybe_single().execute()
        )
        if hosp_res.data:
            hospital_name = hosp_res.data.get("name", "未知醫院")

    # Fetch user's LINE User ID and notification settings from users_local
    try:
        user_res = await _run(
            lambda: supabase.table("users_local")
            .select("line_user_id")
            .eq("id", sub["user_id"])
            .execute()
        )
        user_data = user_res.data[0] if user_res.data else {}
        line_user_id = user_data.get("line_user_id", "")
    except Exception as e:
        log.warning(f"Failed to fetch line_user_id: {e}. Column may not exist in database.")
        line_user_id = ""

    # Fetch user email from auth (non-blocking)
    user_email = await _get_user_email(supabase, sub["user_id"])

    log.info(f"[Notification] sub={sub_id_short} doc={doctor_id_short}: remaining={remaining}, target={target_number}, current={current_number}, wl={waiting_list}, email={user_email}")

    tasks = []

    # Check thresholds in descending order (20 → 10 → 5)
    thresholds = [
        (20, "notify_at_20", "notified_20"),
        (10, "notify_at_10", "notified_10"),
        (5,  "notify_at_5",  "notified_5"),
    ]

    for threshold, notify_flag, notified_flag in thresholds:
        if not sub.get(notify_flag):
            continue
        if sub.get(notified_flag):
            continue  # Already notified for this threshold
        
        if current_number > target_number:
            # If we missed the window entirely, mark as notified to stop trying, 
            # but don't send an alert for a past appointment.
            await _run(lambda: supabase.table("tracking_subscriptions").update({notified_flag: True}).eq("id", sub["id"]).execute())
            continue

        if remaining > threshold:
            continue  # Not yet reached

        tasks.append(
            _send_alerts(
                supabase=supabase,
                sub_id=sub["id"],
                user_id=sub["user_id"],
                doctor_id=sub.get("doctor_id"),
                email=user_email,
                line_user_id=line_user_id,
                notify_email=sub.get("notify_email", True),
                notify_line=sub.get("notify_line", False),
                hospital_name=hospital_name,
                clinic_room=clinic_room,
                doctor_name=doctor_name,
                dept_name=dept_name,
                session_date_str=session_date_str,
                session_type_str=session_type_str,
                current_number=current_number,
                remaining=remaining,
                threshold=threshold,
                notified_flag=notified_flag,
                appointment_number=sub.get("appointment_number"),
            )
        )
        break

    if tasks:
        log.info(f"[Notification] sub={sub_id_short}: gathering {len(tasks)} alert task(s)")
        await asyncio.gather(*tasks)
    else:
        log.info(f"[Notification] sub={sub_id_short}: no tasks queued (remaining={remaining}, notified flags checked)")


async def _send_alerts(
    *,
    supabase,
    sub_id: str,
    user_id: str,
    doctor_id: str | None = None,
    email: str | None = None,
    line_user_id: str = "",
    notify_email: bool = True,
    notify_line: bool = False,
    hospital_name: str = "Unknown",
    clinic_room: str = "",
    doctor_name: str = "",
    dept_name: str = "",
    session_date_str: str = "",
    session_type_str: str = "",
    current_number: int = 0,
    remaining: int = 0,
    threshold: int = 0,
    notified_flag: str = "",
    appointment_number: int | None = None,
):
    send_tasks = []

    if notify_email and email:
        subject, body = build_clinic_alert_email(
            hospital_name=hospital_name,
            clinic_room=clinic_room,
            doctor_name=doctor_name,
            department_name=dept_name,
            session_date=session_date_str,
            session_type=session_type_str,
            current_number=current_number,
            remaining=remaining,
            threshold=threshold,
            appointment_number=appointment_number,
        )
        send_tasks.append(_send_and_log(
            supabase, sub_id, threshold, "email", email, f"Email: {subject}",
            doctor_id=doctor_id,
            hospital_name=hospital_name,
            department_name=dept_name,
            clinic_room=clinic_room,
            session_date=session_date_str,
            current_number=current_number,
            coro=send_email(email, subject, body)
        ))

    if notify_line and line_user_id:
        message = build_line_message(
            doctor_name=doctor_name,
            department_name=dept_name,
            session_date=session_date_str,
            session_type=session_type_str,
            current_number=current_number,
            remaining=remaining,
            threshold=threshold,
        )
        send_tasks.append(_send_and_log(
            supabase, sub_id, threshold, "line", line_user_id, f"LINE: {message}",
            doctor_id=doctor_id,
            hospital_name=hospital_name,
            department_name=dept_name,
            clinic_room=clinic_room,
            session_date=session_date_str,
            current_number=current_number,
            coro=send_line_message(line_user_id, message)
        ))

    if send_tasks:
        log.info(f"[Notification] Awaiting {len(send_tasks)} alert tasks for sub {sub_id}")
        await asyncio.gather(*send_tasks)

        # Mark this threshold as notified ONLY if we actually attempted to send something
        await _run(
            lambda: supabase.table("tracking_subscriptions")
            .update({notified_flag: True})
            .eq("id", sub_id)
            .execute()
        )
        log.info(f"[Notification] Updated {notified_flag} flag for sub {sub_id}")
    else:
         log.warning(f"[Notification] No alerts sent for sub {sub_id} threshold {threshold}. Tasks list was empty. Email: {email}, LineUserID: {'set' if line_user_id else 'not set'}")


async def _send_and_log(
    supabase,
    sub_id,
    threshold,
    channel,
    recipient,
    message,
    doctor_id=None,
    hospital_name=None,
    department_name=None,
    clinic_room=None,
    session_date=None,
    current_number=None,
    coro=None,
):
    # Log the attempt FIRST with context
    # Set sent_at to Taiwan time (UTC+8) in ISO format
    sent_at_tw = now_tw().isoformat()
    
    log_data = {
        "subscription_id": sub_id,
        "threshold": threshold,
        "channel": channel,
        "recipient": recipient or "Unknown",
        "message": message or "Notification sent",
        "success": False,
        "error_message": "Started sending...",
        "sent_at": sent_at_tw,  # Explicitly set to Taiwan time
    }
    
    # Add optional context fields if available - only add non-empty values
    if doctor_id:
        log_data["doctor_id"] = doctor_id
    if hospital_name and hospital_name != "未知醫院":
        log_data["hospital_name"] = hospital_name
    if department_name and department_name not in ("未知科別", None, ""):
        log_data["department_name"] = department_name
    if clinic_room and clinic_room not in ("未提供", None, ""):
        log_data["clinic_room"] = clinic_room
    if session_date:
        log_data["session_date"] = session_date
    if current_number is not None:
        log_data["current_number"] = current_number
    
    try:
        log_res = await _run(
            lambda: supabase.table("notification_logs").insert(log_data).execute()
        )
        log_id = log_res.data[0]["id"] if log_res.data else None
    except Exception as e:
        log.error(f"[Notification] Failed to insert log row: {e}. Data: {log_data}")
        log_id = None

    success = False
    error_message = None
    http_status_code = None
    
    try:
        if not recipient and channel == "email":
             raise ValueError("User email is missing")
        if coro:
            result = await coro
            
            # Handle different return types (for backward compatibility)
            if isinstance(result, dict):
                # NEW: LINE API now returns dict with detailed error info
                success = result.get("success", False)
                http_status_code = result.get("http_status_code")
                error_message = result.get("error_message")
            else:
                # OLD: Email or legacy boolean returns
                success = bool(result)
                error_message = None
    except Exception as e:
        success = False
        error_message = str(e)
        http_status_code = None

    # Update the log with final result
    if log_id:
        try:
            update_data = {
                "success": success,
                "error_message": error_message,
            }
            # Add http_status_code if available
            if http_status_code is not None:
                update_data["http_status_code"] = http_status_code
            
            await _run(
                lambda: supabase.table("notification_logs").update(update_data).eq("id", log_id).execute()
            )
        except Exception as e:
            log.error(f"[Notification] Failed to update log row {log_id}: {e}")



async def _get_user_email(supabase, user_id: str) -> str | None:
    """Fetch email from Supabase auth admin API, fallback to users_local table."""
    
    # 1. Try Supabase Auth
    try:
        user = await _run(
            lambda: supabase.auth.admin.get_user_by_id(user_id)
        )
        if user and user.user and user.user.email:
            return user.user.email
    except Exception as e:
        log.debug(f"[Notification] Supabase Auth email fetch failed for {user_id}: {e}")

    # 2. Fallback to users_local table
    try:
        res = await _run(
            lambda: supabase.table("users_local")
            .select("email")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        if res.data:
            return res.data.get("email")
    except Exception as e:
        log.error(f"[Notification] users_local email fetch failed for {user_id}: {e}")

    log.warning(f"[Notification] Could not find email for user {user_id} in Auth or users_local")
    return None
