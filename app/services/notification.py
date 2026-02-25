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
from app.services.line_service import send_line_notify, build_line_message
from app.core.logger import logger as log
from app.core.timezone import today_tw_str


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
    doctor_id_short = doctor_id[:8]
    if not snap_res.data:
        log.info(f"[Notification] sub={sub_id_short} doc={doctor_id_short} ({session_type}): no snapshot found for {tw_today}")
        return

    snap = snap_res.data[0]
    current_number = snap.get("current_number")
    total_quota = snap.get("total_quota")
    waiting_list = snap.get("waiting_list") or []

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

    if waiting_list:
        # Calculate people waiting AHEAD of the user
        remaining = len([x for x in waiting_list if x < target_number])
        # If the user's number is already passed, this count will correctly be 0
        # However, we check if the current number already passed the target to be sure
        if current_number > target_number:
            remaining = 0
    else:
        # Fallback to old behavior if waiting_list is missing
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

    # Fetch user's LINE Notify token from users_local
    user_res = await _run(
        lambda: supabase.table("users_local")
        .select("line_notify_token")
        .eq("id", sub["user_id"])
        .execute()
    )
    user_data = user_res.data[0] if user_res.data else {}
    line_notify_token = user_data.get("line_notify_token", "")

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
                email=user_email,
                line_notify_token=line_notify_token,
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
    email: str | None,
    line_notify_token: str,
    notify_email: bool,
    notify_line: bool,
    hospital_name: str,
    clinic_room: str,
    doctor_name: str,
    dept_name: str,
    session_date_str: str,
    session_type_str: str,
    current_number: int,
    remaining: int,
    threshold: int,
    notified_flag: str,
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
        )
        send_tasks.append(_send_and_log(
            supabase, sub_id, threshold, "email", email,
            send_email(email, subject, body)
        ))

    if notify_line and line_notify_token:
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
            supabase, sub_id, threshold, "line", "",
            send_line_notify(line_notify_token, message)
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
         log.warning(f"[Notification] No alerts sent for sub {sub_id} threshold {threshold}. Tasks list was empty. Email: {email}, LineToken: {'set' if line_notify_token else 'not set'}")


async def _send_and_log(supabase, sub_id, threshold, channel, recipient, coro):
    # Log the attempt FIRST so we have a record even if it crashes
    log_res = await _run(
        lambda: supabase.table("notification_logs").insert({
            "subscription_id": sub_id,
            "threshold": threshold,
            "channel": channel,
            "recipient": recipient or "Unknown",
            "success": False,
            "error_message": "Started sending...",
        }).execute()
    )
    log_id = log_res.data[0]["id"] if log_res.data else None

    success = False
    error = None
    try:
        if not recipient and channel == "email":
             raise ValueError("User email is missing")
        success = await coro
    except Exception as e:
        error = str(e)

    # Update the log with final result
    if log_id:
        await _run(
            lambda: supabase.table("notification_logs").update({
                "success": success,
                "error_message": error,
            }).eq("id", log_id).execute()
        )


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
