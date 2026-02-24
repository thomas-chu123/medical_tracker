import asyncio
import os
import sys

# Ensure app module can be found
sys.path.append(os.getcwd())

from app.services.notification import check_and_notify

async def main():
    print("Starting manual trigger for check_and_notify...")
    await check_and_notify()
    print("Manual trigger complete.")

if __name__ == "__main__":
    asyncio.run(main())
