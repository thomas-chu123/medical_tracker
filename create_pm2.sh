activate
pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload" --name medical-app