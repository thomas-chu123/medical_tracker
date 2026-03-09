# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language Requirements

**所有回覆都必須使用繁體中文 (Traditional Chinese)**

- ✅ 使用繁體中文
- ❌ 不使用簡體中文、英文或其他語言
- ✅ 代碼註釋: 繁體中文
- ✅ Git 提交信息: 英文（按照專案慣例）
- ✅ PR 描述: 英文（按照專案慣例）
- ✅ Code review 評論: 繁體中文
- ✅ 文件說明: 繁體中文, 放置於 `/docs` 目錄
- ✅ 回覆內容: 繁體中文

## Project Overview

This is a medical appointment tracking system for Taiwan hospitals that automatically collects hospital clinic registration data and notifies users when their appointment is approaching. The system supports multiple hospitals with different scraping implementations, featuring:

- Multi-hospital support with a modular scraper architecture
- Real-time clinic progress tracking with email and LINE notifications
- REST API built with FastAPI
- Supabase database for data storage
- JWT authentication for user management

## Architecture & Structure

The codebase follows a layered architectural pattern with these key components:

### Core Packages
- `app/`: Main application code
  - `main.py`: FastAPI application entry point with lifespan management
  - `config.py`: Environment variable configuration
  - `database.py`: Supabase connection and database interactions
  - `auth.py`: JWT authentication and user management
  - `scheduler.py`: APScheduler for scheduling data scraping tasks
  - `scrapers/`: Hospital-specific scraper implementations
    - `base.py`: Abstract BaseScraper class defining scraper interface
    - `hospital_registry.py`: Registry for managing enabled hospital scrapers
  - `services/`: Business logic services (notification, data writer)
  - `api/`: FastAPI routes organized by functionality
  - `models/`: Pydantic data models for API schemas
- `tools/`: CLI utilities for database and notion interactions

### Key Technical Patterns
- **Strategy Pattern**: Hospital scrapers implement a common interface (BaseScraper) allowing for dynamic loading
- **Dependency Injection**: Configuration loaded via Pydantic settings
- **Modular Task Scheduling**: Separate master data (departments/doctors) and tracked appointments scraping tasks
- **Async/Await**: Most operations use async for concurrent data fetching
- **Supabase Synchronization**: All database operations wrapped with `asyncio.to_thread()` to prevent blocking

## Common Development Tasks

### Running the Application
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with SMTP credentials and Supabase config

# Run with uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# View API documentation
Open browser to http://localhost:8000/docs
```

### Running Tests
```bash
# Run all non-UI tests (unit and integration tests)
pytest tests/ --ignore=tests/test_ui_selenium.py --ignore=tests/test_ui_e2e_minimal.py -v --tb=short

# Run specific test file or function
pytest tests/test_scheduler_logic.py::TestClassName::test_method_name -v

# Run unit tests
pytest tests/ -m unit -v

# Run integration tests
pytest tests/ -m integration -v

# Run UI/Selenium tests (requires server and Chrome)
SELENIUM_HEADLESS=true pytest tests/test_ui_selenium.py -v -s --tb=short

# Manual trigger crawler (requires server running)
curl -X POST http://localhost:8000/api/admin/scrape-now
```

### Adding a New Hospital Scraper
1. Create a new scraper class in `app/scrapers/` that inherits from `BaseScraper`
2. Implement the abstract methods (`fetch_departments`, `fetch_schedule`, `fetch_clinic_progress`, `calculate_remaining_count`)
3. Set the `HOSPITAL_CODE` class attribute (used for querying DB hospital records)
4. Add the scraper to the `HOSPITAL_SCRAPERS` dictionary in `app/scrapers/hospital_registry.py`
5. Enable the hospital in `.env` by adding its code to `ENABLED_HOSPITALS`

### Database Operations
All Supabase calls are synchronous (supabase-py is sync client) and must be wrapped with `asyncio.to_thread()`:
```python
result = await asyncio.to_thread(
    lambda: supabase.table("doctors").select("*").eq("id", doc_id).execute()
)
```

### Time Zone Considerations
All crawling and notification logic uses Taiwan time (UTC+8). Use helper functions in `app/core/timezone.py`:
- `now_tw()` for current time in Taiwan
- `today_tw()` for today's date in Taiwan
- `today_tw_str()` for today's date as string
- `now_utc_str()` for UTC timestamp
- Use UTC timestamps in DB but compare `session_date` using Taiwan local date

### Period Mapping
Use Chinese `"上午"` / `"下午"` / `"晚上"` in code and database. API period parameters map to `"1"` / `"2"` / `"3"`.

### Supabase CLI Tools
For quick database operations, use the provided CLI tools:

#### tool_supabase.py
```bash
# List all hospitals
python tools/tool_supabase.py list_hospitals

# List doctors in department
python tools/tool_supabase.py list_doctors --department_id DEPT001

# Get user subscriptions
python tools/tool_supabase.py get_subscriptions user123

# Select from table with filters
python tools/tool_supabase.py select appointment_snapshots --filter doctor_id eq DOC001 --filter session_date gte 2026-03-01 --limit 100

# Upsert data
python tools/tool_supabase.py upsert appointment_snapshots --data '{"doctor_id":"DOC001","session_date":"2026-03-05","session_type":"上午","current_number":5}' --on_conflict "doctor_id,session_date,session_type"
```

#### tool_notion.py
```bash
# List all projects
python tools/tool_notion.py list_projects

# Query projects with filters
python tools/tool_notion.py query_projects --filter Status is "進行中"

# Create new project
python tools/tool_notion.py create_project --data '{"Name":"新項目","Status":"計劃中"}'
```

## Scraping Architecture

The system uses two distinct scraping tasks:

1. **Master Data**: Fetch department and doctor information (runs less frequently)
   - Ran from 00:00–06:00 daily
   - Update `appointment_snapshots` with basic data (no real-time progress)

2. **Tracked Appointments**: Fetch real-time clinic progress for subscribed appointments (runs every 3 minutes)
   - Ran 07:00–23:00 daily
   - Only fetches data for tracked appointments
   - Only retrieves progressive data (current_number) when clinic session has started
   - Triggers `check_and_notify()` to send notifications when appropriate

The scheduler uses `apscheduler` to orchestrate these tasks and includes anti-scraping measures like random delays between requests.

## Data Flow

1. **APScheduler** runs scheduled tasks:
   - 00:00–06:00: `run_cmuh_master_data()` - Fetch comprehensive department/doctor/schedule data
   - 07:00–23:00 every 3 minutes: `run_tracked_appointments()` - Fetch real-time clinic progress for tracked appointments
   - 08:00: `run_morning_tracked_snapshot_sync()` - Refresh today's tracked clinic progress

2. **Crawlers** inherit from `BaseScraper` and implement 3 abstract methods:
   - `fetch_departments()` → `list[DepartmentData]`
   - `fetch_schedule(dept_code)` → `list[DoctorSlot]`
   - `fetch_clinic_progress(room, period)` → `Optional[ClinicProgress]`

3. **Snapshot Writing Logic** has time-aware capabilities:
   - Only fetches `current_number` after clinic session has started (08:00 for morning, 13:30 for afternoon, 18:00 for evening)
   - Only updates real-time fields (`current_number`, `total_quota`, `waiting_list`) when not None
   - Prevents overwriting previous valid data

4. **Notification Thresholds**: `check_and_notify()` triggers notifications when remaining numbers are ≤ 20, ≤ 10, and ≤ 5, with `notified_N` flags to prevent duplicates