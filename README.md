# TrailDetector v0.1

LiDAR post-processing toolkit that generates a DEM, Ridge Index (RI), Ground Point Density (GPD), Undergrowth Openness Index (UOI), and the combined Trail Score as PNG heatmaps. The backend follows the FastAPI + NumPy/SciPy stack described in `docs/spec.md`, while the frontend provides a React/Vite control panel to submit jobs and preview the four outputs.

## Repository Layout

```
backend/   FastAPI service (uv / Python 3.12)
frontend/  React + TypeScript + Vite UI
docs/      Specification and project notes
```

## Backend (FastAPI)

```bash
cd backend
uv sync                     # Install dependencies from pyproject.toml
uv run uvicorn app.main:app --reload
```

The API exposes `POST /trail/detect` (JSON with file paths) and `POST /trail/detect/upload` (multipart uploads used by the frontend). Results are written to `trail_results/<run_id>` and served under `/static/results/<run_id>/<metric>.png`.

## Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev                 # Starts Vite on http://127.0.0.1:5173
```

Optional: set `VITE_API_URL` to point at a remote backend; it defaults to `http://127.0.0.1:8000` for local development.

## Spec Reference

See `docs/spec.md` for the end-to-end algorithm description, API contract, and UI expectations implemented here.
