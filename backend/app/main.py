"""FastAPI entrypoint for the Trail Detector backend."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional
from uuid import uuid4

import matplotlib

# Use a non-interactive backend for headless servers.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import get_settings
from .core.algorithms import TrailParams, run_trail_detection
from .schemas import TrailDetectRequest, TrailDetectResponse, TrailErrorResponse

settings = get_settings()

app = FastAPI(title="Trail Detector API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(settings.static_url_prefix, StaticFiles(directory=settings.static_root), name="results")


def _error(message: str, status_code: int = 400) -> JSONResponse:
    """Return an error payload following the spec."""
    payload = TrailErrorResponse(message=message).model_dump()
    return JSONResponse(status_code=status_code, content=payload)


def _render_heatmap(array: np.ndarray, out_path: Path, cmap: str) -> None:
    """Save a single-channel array as a PNG heatmap."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(4, 4), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.imshow(array, cmap=cmap, vmin=0.0, vmax=1.0, origin="lower")
    fig.savefig(out_path, dpi=200, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def _save_images(arrays: Dict[str, np.ndarray], run_id: str) -> Dict[str, str]:
    """Render all rasters and return HTTP paths."""
    cmap_map = {
        "ridge": "magma",
        "gpd": "viridis",
        "uoi": "plasma",
        "trail_score": "cividis",
    }
    storage_dir = settings.static_root / run_id
    saved: Dict[str, str] = {}
    for name, array in arrays.items():
        path = storage_dir / f"{name}.png"
        _render_heatmap(array, path, cmap_map.get(name, "viridis"))
        saved[name] = f"{settings.static_url_prefix}/{run_id}/{path.name}"
    return saved


def _copy_results_to_output(files: Dict[str, str], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for url in files.values():
        filename = Path(url).name
        source = settings.static_root / Path(url).parent.name / filename
        if source.exists():
            shutil.copy2(source, destination / filename)


def _run_detection_pipeline(
    pointcloud_files: List[str],
    grid_size: float,
    params_override: Optional[Dict[str, Any]],
    output_dir: Optional[str],
) -> TrailDetectResponse:
    params_dict: Dict[str, Any] = {"grid_size": grid_size}
    if params_override:
        params_dict.update(params_override)
    params = TrailParams(**params_dict)

    results = run_trail_detection(pointcloud_files, params)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    run_id = f"{timestamp}_{uuid4().hex[:6]}"
    arrays = {
        "ridge": results["ri"],
        "gpd": results["gpd"],
        "uoi": results["uoi"],
        "trail_score": results["trail_score"],
    }
    image_paths = _save_images(arrays, run_id)

    if output_dir:
        _copy_results_to_output(image_paths, Path(output_dir).expanduser())

    return TrailDetectResponse(
        status="ok",
        extent=[float(value) for value in results["grid"]["extent"]],
        images=image_paths,
    )


def _handle_detection(
    pointcloud_files: List[str],
    grid_size: float,
    params_override: Optional[Dict[str, Any]],
    output_dir: Optional[str],
):
    try:
        return _run_detection_pipeline(pointcloud_files, grid_size, params_override, output_dir)
    except ValidationError as exc:
        return _error(f"Invalid parameters: {exc}", status_code=400)
    except FileNotFoundError as exc:
        return _error(str(exc), status_code=400)
    except ValueError as exc:
        return _error(str(exc), status_code=400)
    except Exception as exc:  # pragma: no cover - unexpected error surface
        return _error(f"Unhandled processing error: {exc}", status_code=500)


@app.post(
    "/trail/detect",
    response_model=TrailDetectResponse,
    responses={400: {"model": TrailErrorResponse}},
)
async def detect_trails(payload: TrailDetectRequest):
    """Main endpoint: read LAS files, compute metrics, and respond with PNGs."""
    return _handle_detection(payload.pointcloud_files, payload.grid_size, payload.params, payload.output_dir)


@app.post(
    "/trail/detect/upload",
    response_model=TrailDetectResponse,
    responses={400: {"model": TrailErrorResponse}},
)
async def detect_trails_from_upload(
    files: List[UploadFile] = File(...),
    grid_size: float = Form(1.0),
    output_dir: Optional[str] = Form(None),
    params: Optional[str] = Form(None),
):
    """Endpoint that accepts LAS/LAZ uploads instead of filesystem paths."""
    if not files:
        return _error("At least one LAS/LAZ file must be uploaded.", status_code=400)

    params_dict: Optional[Dict[str, Any]] = None
    if params:
        try:
            parsed = json.loads(params)
        except json.JSONDecodeError as exc:
            return _error(f"Invalid params JSON: {exc}", status_code=400)
        if parsed is not None and not isinstance(parsed, dict):
            return _error("params must be a JSON object.", status_code=400)
        params_dict = parsed

    with TemporaryDirectory(prefix="trail_upload_") as temp_dir:
        saved_paths: List[str] = []
        for upload in files:
            filename = Path(upload.filename or f"upload_{len(saved_paths) + 1}.las").name
            destination = Path(temp_dir) / filename
            contents = await upload.read()
            destination.write_bytes(contents)
            saved_paths.append(str(destination))

        return _handle_detection(saved_paths, grid_size, params_dict, output_dir)
