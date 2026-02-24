"""
Notification orchestration service.
Checks active tracking subscriptions against the latest appointment snapshots
and fires email/LINE alerts when thresholds are crossed.

All Supabase calls are wrapped with asyncio.to_thread() to avoid blocking
the FastAPI event loop.
"""

import asyncio
from datetime import date

from app.database import get_supabase
from app.services.email_service import send_email, build_clinic_alert_email
from app.services.line_service import send_line_notify, build_line_message


def _run(fn):
    """Run a synchronous Supabase call in a thread pool executor."""
    return asyncio.to_thread(fn)


async def check_and_notify():
    """Main notification loop: called after each scrape cycle."""
    supabase = get_supabase()
    today = str(date.today())

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
        await _process_subscription(supabase, sub)


async def _process_subscription(supabase, sub: dict):
    """Evaluate one subscription and send notifications if needed."""
    doctor_id = sub["doctor_id"]
    session_type = sub.get("session_type")

    # Build query for latest snapshot
    def _fetch_snap():
        q = (
            supabase.table("appointment_snapshots")
            .select("*")
            .eq("doctor_id", doctor_id)
            .eq("session_date", str(date.today()))
            .order("scraped_at", desc=True)
            .limit(1)
        )
        if session_type:
            q = q.eq("session_type", session_type)
        return q.execute()

    snap_res = await _run(_fetch_snap)
    if not snap_res.data:
        return

    snap = snap_res.data[0]
    current_number = snap.get("current_number")
    total_quota = snap.get("total_quota")
    waiting_list = snap.get("waiting_list") or []

    if current_number is None:
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
    else:
        # Fallback to old behavior if waiting_list is missing
        remaining = target_number - current_number

    # Build context for notifications
    doctor_name = (sub.get("doctors") or {}).get("name", "未知醫師")
    dept_name = (sub.get("departments") or {}).get("name", "未知科別")
    session_date_str = str(date.today())
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

    # Fetch user_profiles separately due to missing FK
    profile_res = await _run(
        lambda: supabase.table("user_profiles")
        .select("line_notify_token")
        .eq("id", sub["user_id"])
        .execute()
    )
    user_profile = profile_res.data[0] if profile_res.data else {}
    line_token = user_profile.get("line_notify_token", "")

    # Fetch user email from auth (non-blocking)
    user_email = await _get_user_email(supabase, sub["user_id"])

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
        if remaining > threshold:
            continue  # Not yet reached

        tasks.append(
            await _send_alerts(
                supabase=supabase,
                sub_id=sub["id"],
                user_id=sub["user_id"],
                email=user_email,
                line_token=line_token,
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

    if tasks:
        await asyncio.gather(*tasks)
    else:
        # If no tasks but remaining is low, it might be already notified.
        # But we should log if we expected to notify.
        pass


async def _send_alerts(
    *,
    supabase,
    sub_id: str,
    user_id: str,
    email: str | None,
    line_token: str,
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

    if notify_line and line_token:
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
            send_line_notify(line_token, message)
        ))

    # Mark this threshold as notified
    await _run(
        lambda: supabase.table("tracking_subscriptions")
        .update({notified_flag: True})
        .eq("id", sub_id)
        .execute()
    )

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
    """Fetch email from Supabase auth admin API (non-blocking)."""
    try:
        user = await _run(
            lambda: supabase.auth.admin.get_user_by_id(user_id)
        )
        return user.user.email if user and user.user else None
    except Exception:
        return None
