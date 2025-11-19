"""Pydantic schemas for requests and responses."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class TrailDetectRequest(BaseModel):
    """Incoming payload for /trail/detect."""

    pointcloud_files: List[str] = Field(..., description="Absolute or relative LAS/LAZ file paths.")
    grid_size: float = Field(1.0, gt=0, description="Spatial resolution for grid aggregation in meters.")
    output_dir: Optional[str] = Field(
        default=None,
        description="Optional filesystem directory that receives a copy of the generated PNG files.",
    )
    params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional overrides for trail metric parameters.",
    )
    show_legend: bool = Field(
        default=False,
        description="Set true to render each PNG with a 0-1 colorbar legend.",
    )

    @field_validator("pointcloud_files")
    @classmethod
    def _ensure_non_empty(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("At least one LAS/LAZ file must be provided.")
        return value


class TrailImagePaths(BaseModel):
    """JSON payload for the four rendered rasters."""

    ridge: str
    gpd: str
    uoi: str
    trail_score: str


class TrailDetectResponse(BaseModel):
    """Successful /trail/detect response."""

    status: Literal["ok"] = "ok"
    extent: List[float] = Field(..., min_length=4, max_length=4)
    images: TrailImagePaths


class TrailErrorResponse(BaseModel):
    """Error payload for /trail/detect."""

    status: Literal["error"] = "error"
    message: str
