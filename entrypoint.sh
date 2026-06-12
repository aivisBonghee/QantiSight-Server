#!/bin/sh
python scripts/seed_mock_data.py
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
