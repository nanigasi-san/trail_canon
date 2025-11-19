"""Numerical routines that derive trail metrics from LiDAR point clouds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import laspy
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, field_validator
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter, gaussian_laplace


@dataclass(slots=True)
class PointCloud:
    """In-memory cache of LAS/LAZ data."""

    x: NDArray[np.float64]
    y: NDArray[np.float64]
    z: NDArray[np.float64]
    classification: NDArray[np.int32]


class TrailParams(BaseModel):
    """Collection of tunable parameters for trail detection."""

    grid_size: float = Field(1.0, gt=0)
    ridge_scales_m: Tuple[float, float, float] = (3.0, 6.0, 9.0)
    tpi_scale_m: float = Field(15.0, gt=0)
    tpi_percentiles: Tuple[float, float] = (5.0, 95.0)
    log_percentiles: Tuple[float, float] = (5.0, 95.0)
    slope_pref_deg: float = Field(20.0, ge=0.0)
    slope_sigma_deg: float = Field(20.0, gt=0.0)
    density_percentile: float = Field(99.0, gt=0.0, le=100.0)
    density_classes: Tuple[int, ...] = (2,)
    ground_classes: Tuple[int, ...] = (2, 22)
    uoi_height_band: Tuple[float, float] = (0.0, 1.0)
    uoi_percentile: float = Field(95.0, gt=0.0, le=100.0)
    flatness_classes: Tuple[int, ...] = (3, 4, 5)
    flatness_percentile: float = Field(95.0, gt=0.0, le=100.0)

    model_config = ConfigDict(validate_default=True)

    @field_validator("ridge_scales_m")
    @classmethod
    def _validate_scales(cls, value: Tuple[float, ...]) -> Tuple[float, ...]:
        if any(scale <= 0 for scale in value):
            raise ValueError("ridge_scales_m must contain positive values.")
        return value

    @field_validator("uoi_height_band")
    @classmethod
    def _validate_height_band(cls, value: Tuple[float, float]) -> Tuple[float, float]:
        lower, upper = value
        if upper <= lower:
            raise ValueError("uoi_height_band must be defined as (min, max).")
        return value


def _load_point_cloud(las_files: Sequence[str]) -> PointCloud:
    """Load LAS/LAZ points into numpy arrays."""
    xs: List[NDArray[np.float64]] = []
    ys: List[NDArray[np.float64]] = []
    zs: List[NDArray[np.float64]] = []
    classes: List[NDArray[np.int32]] = []

    for file_path in las_files:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Point cloud file not found: {path}")
        las = laspy.read(path)
        xs.append(np.asarray(las.x, dtype=np.float64))
        ys.append(np.asarray(las.y, dtype=np.float64))
        zs.append(np.asarray(las.z, dtype=np.float64))
        classes.append(np.asarray(las.classification, dtype=np.int32))

    if not xs:
        raise ValueError("No LAS/LAZ files supplied.")

    x = np.concatenate(xs)
    y = np.concatenate(ys)
    z = np.concatenate(zs)
    classification = np.concatenate(classes)
    return PointCloud(x=x, y=y, z=z, classification=classification)


def _filter_by_classes(point_cloud: PointCloud, classes: Iterable[int]) -> NDArray[np.bool_]:
    class_array = np.array(list(classes), dtype=np.int32)
    return np.isin(point_cloud.classification, class_array)


def _build_grid(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    grid_size: float,
) -> Tuple[NDArray[np.float64], NDArray[np.float64], Dict[str, float]]:
    xmin = float(np.min(x))
    xmax = float(np.max(x))
    ymin = float(np.min(y))
    ymax = float(np.max(y))

    nx = max(int(np.ceil((xmax - xmin) / grid_size)) + 1, 2)
    ny = max(int(np.ceil((ymax - ymin) / grid_size)) + 1, 2)

    x_coords = xmin + np.arange(nx, dtype=np.float64) * grid_size
    y_coords = ymin + np.arange(ny, dtype=np.float64) * grid_size
    grid_x, grid_y = np.meshgrid(x_coords, y_coords)

    grid = {
        "xmin": xmin,
        "xmax": float(x_coords[-1]),
        "ymin": ymin,
        "ymax": float(y_coords[-1]),
        "nx": nx,
        "ny": ny,
        "grid_size": grid_size,
        "extent": (xmin, float(x_coords[-1]), ymin, float(y_coords[-1])),
    }
    return grid_x, grid_y, grid


def _normalize_percentile(
    array: NDArray[np.floating],
    lower: float,
    upper: float,
) -> NDArray[np.float32]:
    if upper <= lower:
        upper = lower + 1e-3
    if np.all(np.isnan(array)):
        return np.zeros_like(array, dtype=np.float32)
    lo = np.nanpercentile(array, lower)
    hi = np.nanpercentile(array, upper)
    if np.isclose(hi, lo):
        return np.zeros_like(array, dtype=np.float32)
    normalized = (array - lo) / (hi - lo)
    return np.clip(normalized, 0.0, 1.0).astype(np.float32)


def _normalize_minmax(array: NDArray[np.floating]) -> NDArray[np.float32]:
    if np.all(np.isnan(array)):
        return np.zeros_like(array, dtype=np.float32)
    min_val = np.nanmin(array)
    max_val = np.nanmax(array)
    if np.isclose(max_val, min_val):
        return np.zeros_like(array, dtype=np.float32)
    normalized = (array - min_val) / (max_val - min_val)
    return np.clip(normalized, 0.0, 1.0).astype(np.float32)


def compute_dem_from_las(
    las_files: List[str],
    params: TrailParams,
    *,
    point_data: Optional[PointCloud] = None,
) -> Tuple[NDArray[np.float32], Dict[str, float]]:
    """Generate a raster DEM from ground-classified points."""
    points = point_data or _load_point_cloud(las_files)
    mask = _filter_by_classes(points, params.ground_classes)
    if not np.any(mask):
        raise ValueError("No ground-classified points were found.")

    ground_x = points.x[mask]
    ground_y = points.y[mask]
    ground_z = points.z[mask]

    grid_x, grid_y, grid = _build_grid(ground_x, ground_y, params.grid_size)

    locations = np.column_stack((ground_x, ground_y))
    dem_linear = griddata(locations, ground_z, (grid_x, grid_y), method="linear")
    dem_nearest = griddata(locations, ground_z, (grid_x, grid_y), method="nearest")
    dem = np.where(np.isnan(dem_linear), dem_nearest, dem_linear)
    fill_value = np.nanmedian(ground_z)
    dem = np.nan_to_num(dem, nan=float(fill_value))
    return dem.astype(np.float32), grid


def compute_ri(
    dem: NDArray[np.float32],
    grid: Dict[str, float],
    params: TrailParams,
) -> NDArray[np.float32]:
    """Compute the Ridge Index using TPI, LoG filters, and slope weighting."""
    sigma_tpi = max(params.tpi_scale_m / params.grid_size, 0.5)
    local_mean = gaussian_filter(dem, sigma=sigma_tpi, mode="nearest")
    tpi = dem - local_mean
    tpi_norm = _normalize_percentile(tpi, params.tpi_percentiles[0], params.tpi_percentiles[1])

    log_maps: List[NDArray[np.float32]] = []
    for scale in params.ridge_scales_m:
        sigma = max(scale / params.grid_size, 0.5)
        response = -gaussian_laplace(dem, sigma=sigma, mode="nearest")
        log_maps.append(_normalize_minmax(response))
    log_stack = np.maximum.reduce(log_maps) if log_maps else tpi_norm

    grad_y, grad_x = np.gradient(dem, params.grid_size, params.grid_size)
    slope_rad = np.arctan(np.sqrt(grad_x**2 + grad_y**2))
    slope_deg = np.degrees(slope_rad)
    slope_weight = np.exp(-((slope_deg - params.slope_pref_deg) ** 2) / (2 * params.slope_sigma_deg**2))
    slope_weight = np.clip(slope_weight, 0.0, 1.0).astype(np.float32)

    raw_score = (0.6 * log_stack + 0.4 * np.clip(tpi_norm, 0.0, 1.0)) * slope_weight
    return _normalize_minmax(raw_score)


def _bin_points_to_grid(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    grid: Dict[str, float],
    grid_size: float,
) -> Tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.bool_]]:
    xmin = grid["xmin"]
    ymin = grid["ymin"]
    nx = int(grid["nx"])
    ny = int(grid["ny"])
    ix = np.floor((x - xmin) / grid_size).astype(np.int64)
    iy = np.floor((y - ymin) / grid_size).astype(np.int64)
    valid = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    return ix, iy, valid


def compute_gpd(
    las_files: List[str],
    grid: Dict[str, float],
    params: TrailParams,
    *,
    point_data: Optional[PointCloud] = None,
) -> NDArray[np.float32]:
    """Compute per-cell ground point density."""
    points = point_data or _load_point_cloud(las_files)
    mask = _filter_by_classes(points, params.density_classes)
    if not np.any(mask):
        return np.zeros((int(grid["ny"]), int(grid["nx"])), dtype=np.float32)

    x = points.x[mask]
    y = points.y[mask]
    ix, iy, valid = _bin_points_to_grid(x, y, grid, params.grid_size)
    nx = int(grid["nx"])
    ny = int(grid["ny"])
    counts = np.zeros((ny, nx), dtype=np.float64)
    np.add.at(counts, (iy[valid], ix[valid]), 1)
    density = counts / (params.grid_size**2)
    return _normalize_percentile(density, 5.0, params.density_percentile)


def _sample_dem_at_points(
    dem: NDArray[np.float32],
    grid: Dict[str, float],
    x: NDArray[np.float64],
    y: NDArray[np.float64],
) -> NDArray[np.float32]:
    ix, iy, valid = _bin_points_to_grid(x, y, grid, grid["grid_size"])
    ny, nx = dem.shape
    samples = np.full_like(x, np.nan, dtype=np.float32)
    ix = np.clip(ix, 0, nx - 1)
    iy = np.clip(iy, 0, ny - 1)
    samples[valid] = dem[iy[valid], ix[valid]]
    return np.nan_to_num(samples, nan=float(np.nanmedian(samples[valid]) if np.any(valid) else 0.0))


def compute_uoi(
    las_files: List[str],
    dem: NDArray[np.float32],
    grid: Dict[str, float],
    params: TrailParams,
    *,
    point_data: Optional[PointCloud] = None,
) -> NDArray[np.float32]:
    """Compute the Undergrowth Openness Index."""
    points = point_data or _load_point_cloud(las_files)
    mask = _filter_by_classes(points, params.flatness_classes)
    if not np.any(mask):
        return np.zeros((int(grid["ny"]), int(grid["nx"])), dtype=np.float32)

    x = points.x[mask]
    y = points.y[mask]
    z = points.z[mask]
    dtm_at_points = _sample_dem_at_points(dem, grid, x, y)
    normalized_z = z - dtm_at_points
    band_min, band_max = params.uoi_height_band
    height_mask = (normalized_z >= band_min) & (normalized_z <= band_max)
    if not np.any(height_mask):
        return np.zeros((int(grid["ny"]), int(grid["nx"])), dtype=np.float32)

    band_x = x[height_mask]
    band_y = y[height_mask]
    band_z = normalized_z[height_mask]
    ix, iy, valid = _bin_points_to_grid(band_x, band_y, grid, params.grid_size)
    nx = int(grid["nx"])
    ny = int(grid["ny"])
    sum_vals = np.zeros((ny, nx), dtype=np.float64)
    sum_sq = np.zeros((ny, nx), dtype=np.float64)
    counts = np.zeros((ny, nx), dtype=np.float64)

    np.add.at(sum_vals, (iy[valid], ix[valid]), band_z[valid])
    np.add.at(sum_sq, (iy[valid], ix[valid]), band_z[valid] ** 2)
    np.add.at(counts, (iy[valid], ix[valid]), 1)

    mean = np.zeros_like(sum_vals)
    nonzero = counts > 0
    mean[nonzero] = sum_vals[nonzero] / counts[nonzero]
    variance = np.zeros_like(sum_vals)
    variance[nonzero] = (sum_sq[nonzero] / counts[nonzero]) - (mean[nonzero] ** 2)
    std = np.zeros_like(sum_vals)
    std[nonzero] = np.sqrt(np.clip(variance[nonzero], 0.0, None))

    openness = 1.0 - _normalize_percentile(std, 5.0, params.flatness_percentile)
    return np.clip(openness, 0.0, 1.0).astype(np.float32)


def compute_trail_score(
    ri: NDArray[np.float32],
    gpd: NDArray[np.float32],
    uoi: NDArray[np.float32],
) -> NDArray[np.float32]:
    """Combine three metrics into a final trail-likelihood score."""
    return np.clip((ri + gpd + uoi) / 3.0, 0.0, 1.0).astype(np.float32)


def run_trail_detection(
    las_files: List[str],
    params: TrailParams,
) -> Dict[str, NDArray[np.float32]]:
    """Execute the full pipeline from LAS input to normalized rasters."""
    point_data = _load_point_cloud(las_files)
    dem, grid = compute_dem_from_las(las_files, params, point_data=point_data)
    ri = compute_ri(dem, grid, params)
    gpd = compute_gpd(las_files, grid, params, point_data=point_data)
    uoi = compute_uoi(las_files, dem, grid, params, point_data=point_data)
    score = compute_trail_score(ri, gpd, uoi)
    return {
        "dem": dem,
        "ri": ri,
        "gpd": gpd,
        "uoi": uoi,
        "trail_score": score,
        "grid": grid,
    }
