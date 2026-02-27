#!/usr/bin/env python3
"""Debug script to check subscription settings for 黃祥銘."""

import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

async def main():
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # First, find doctors with name 黃祥銘
    print("=" * 80)
    print("Step 1: Find doctor 黃祥銘")
    print("=" * 80)
    
    doctors_res = supabase.table("doctors").select("*").ilike("name", "%黃祥銘%").execute()
    print(f"Found {len(doctors_res.data)} doctor(s)")
    for doc in doctors_res.data:
        print(f"  - ID: {doc['id']}, Name: {doc['name']}, Doctor#: {doc['doctor_no']}, Hospital: {doc['hospital_id']}")
    
    if not doctors_res.data:
        print("No doctor found with name 黃祥銘")
        return
    
    doctor_id = doctors_res.data[0]['id']
    
    # Find subscriptions for this doctor
    print("\n" + "=" * 80)
    print(f"Step 2: Find subscriptions for doctor {doctor_id}")
    print("=" * 80)
    
    subs_res = supabase.table("tracking_subscriptions").select(
        "*,"
        "users_local(id, email, line_user_id, name)"
    ).eq("doctor_id", doctor_id).execute()
    
    print(f"Found {len(subs_res.data)} subscription(s)")
    
    for sub in subs_res.data:
        print(f"\n  Subscription ID: {sub['id']}")
        print(f"  - User ID: {sub['user_id']}")
        print(f"  - Doctor ID: {sub['doctor_id']}")
        print(f"  - Session Date: {sub['session_date']}")
        print(f"  - Appointment Number: {sub['appointment_number']}")
        print(f"  - Threshold: {sub['threshold']}")
        print(f"  - Notify Email: {sub.get('notify_email', 'NOT SET')}")
        print(f"  - Notify LINE: {sub.get('notify_line', 'NOT SET')}")  # <-- THE KEY FIELD
        print(f"  - Is Active: {sub.get('is_active')}")
        
        # User info
        if sub.get('users_local'):
            user = sub['users_local']
            print(f"\n  User Info:")
            print(f"    - Email: {user.get('email', 'NOT SET')}")
            print(f"    - LINE User ID: {user.get('line_user_id', 'NOT SET')}")  # <-- THE KEY FIELD
            print(f"    - Name: {user.get('name', 'NOT SET')}")
    
    # Also check if there's a users_local record with LINE user ID
    print("\n" + "=" * 80)
    print("Step 3: Check users_local for the subscription users")
    print("=" * 80)
    
    for sub in subs_res.data:
        user_res = supabase.table("users_local").select("*").eq("id", sub['user_id']).execute()
        if user_res.data:
            user = user_res.data[0]
            print(f"\nUser {sub['user_id']}:")
            print(f"  - Name: {user.get('name')}")
            print(f"  - Email: {user.get('email')}")
            print(f"  - LINE User ID: {user.get('line_user_id')}")

if __name__ == "__main__":
    asyncio.run(main())
