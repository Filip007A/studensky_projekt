# Metro signage project (folder structure)

## Backend
- `backend/main.py` FastAPI + WebSocket + Golemio (Metro B only)
- `backend/mock_feed.py` generates offline `data/stations.json`
- `backend/test_gtfs.py` minimal unit tests

### Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
export GOLEMIO_API_KEY="..."
export GOLEMIO_STOP_NAMES="Muzeum"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:
- `http://localhost:8000/` (served from `frontend/`)

## Frontend
- `frontend/index.html` (WebSocket client)

## Offline data
- `data/stations.json`
