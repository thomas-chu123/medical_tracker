import asyncio
import os
import sys

# Ensure 'app' can be found but avoid shadowing 'supabase' package
project_root = os.getcwd()
if project_root not in sys.path:
    # Append instead of insert(0) if it shadowing packages
    sys.path.append(project_root)

from app.services.notification import check_and_notify

async def main():
    print("Manual Trigger: Starting notification check...")
    try:
        await check_and_notify()
        print("Manual Trigger: Notification check complete.")
    except Exception as e:
        print(f"Manual Trigger: Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
