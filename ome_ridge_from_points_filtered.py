# type: ignore
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import laspy
import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage
from scipy.interpolate import griddata
from matplotlib.colors import BoundaryNorm, ListedColormap

target_las = "merged_ome.las"
DEFAULT_LAS = Path(__file__).resolve().parent.parent / "cut_las" / target_las
OUTPUT_ROOT = Path(__file__).resolve().parent / "ome_trail"

MAP_SUBPLOT_PARAMS = {"left": 0.01, "right": 0.93, "bottom": 0.01, "top": 0.94}


def _log_image_save(out_path: Path) -> None:
    print(f"[save] {out_path}")


def _create_map_figure() -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.subplots_adjust(**MAP_SUBPLOT_PARAMS)
    return fig, ax


@dataclass(frozen=True)
class Params:
    grid_size: float = 1.0  # DEM resolution for ridge/other metrics
    sample_max_points: int = 5_000_000
    ridge_scales_m: Tuple[float, float, float] = (3.0, 6.0, 9.0)
    tpi_scale_m: float = 15.0
    slope_pref_deg: float = 20.0
    ridge_binary_percentile: float = 90.0
    density_grid_size: float = 1.0
    density_percentile: float = 99.0
    flat_band: Tuple[float, float] = (0.0, 1.0)
    flat_grid_size: float = 1.0
    flat_percentile: float = 95.0
    dtm_classes: Tuple[int, ...] = (2, 22)
    density_classes: Tuple[int, ...] = (2,)
    flatness_classes: Tuple[int, ...] = (2, 4, 22)


def load_las(path: Path) -> laspy.LasData:
    if not path.exists():
        raise FileNotFoundError(f"LAS file not found: {path}")
    return laspy.read(str(path))


def compute_grid(x: np.ndarray, y: np.ndarray, gs: float) -> Dict[str, float]:
    xmin, xmax = float(np.min(x)), float(np.max(x))
    ymin, ymax = float(np.min(y)), float(np.max(y))
    nx = int(np.ceil((xmax - xmin) / gs)) + 1
    ny = int(np.ceil((ymax - ymin) / gs)) + 1
    return {
        "xmin": xmin,
        "ymin": ymin,
        "nx": nx,
        "ny": ny,
        "gs": gs,
        "extent": [xmin, xmin + (nx - 1) * gs, ymin, ymin + (ny - 1) * gs],
    }


def compute_grid_from_extent(extent: list[float], gs: float) -> Dict[str, float]:
    xmin, xmax, ymin, ymax = extent
    nx = int(np.ceil((xmax - xmin) / gs)) + 1
    ny = int(np.ceil((ymax - ymin) / gs)) + 1
    return {
        "xmin": xmin,
        "ymin": ymin,
        "nx": nx,
        "ny": ny,
        "gs": gs,
        "extent": [xmin, xmin + (nx - 1) * gs, ymin, ymin + (ny - 1) * gs],
    }


def normalize(array: np.ndarray, lower: float = 5.0, upper: float = 95.0) -> np.ndarray:
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros_like(array, dtype=np.float32)
    lo = np.percentile(finite, lower)
    hi = np.percentile(finite, upper)
    if np.isclose(lo, hi):
        hi = lo + 1e-6
    return np.clip((array - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def build_dtm_from_points(
    las: laspy.LasData, prm: Params, grid: Dict[str, float]
) -> np.ndarray:
    x = np.asarray(las.x, dtype=np.float64)
    y = np.asarray(las.y, dtype=np.float64)
    z = np.asarray(las.z, dtype=np.float64)
    classification = np.asarray(las.classification, dtype=np.uint8)
    ground_mask = np.isin(classification, prm.dtm_classes)
    x = x[ground_mask]
    y = y[ground_mask]
    z = z[ground_mask]

    total = x.size
    if total == 0:
        raise ValueError("No ground points found in LAS.")
    if total > prm.sample_max_points:
        idx = np.random.default_rng(42).choice(
            total, prm.sample_max_points, replace=False
        )
        x = x[idx]
        y = y[idx]
        z = z[idx]

    gx = np.linspace(grid["xmin"], grid["extent"][1], grid["nx"], dtype=np.float64)
    gy = np.linspace(grid["ymin"], grid["extent"][3], grid["ny"], dtype=np.float64)
    grid_x, grid_y = np.meshgrid(gx, gy)

    points = np.column_stack((x, y))

    dtm_linear = griddata(points, z, (grid_x, grid_y), method="linear")
    dtm_nearest = griddata(points, z, (grid_x, grid_y), method="nearest")
    dtm = np.where(np.isnan(dtm_linear), dtm_nearest, dtm_linear)
    return dtm.astype(np.float32)


def compute_ridge_score(
    dtm: np.ndarray, prm: Params, grid: Dict[str, float]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    responses = []
    for scale_m in prm.ridge_scales_m:
        sigma = max(scale_m / grid["gs"], 1.0)
        response = -ndimage.gaussian_laplace(dtm, sigma=sigma, mode="nearest")
        responses.append(normalize(response))
    log_response = np.maximum.reduce(responses)

    sigma_tpi = max(prm.tpi_scale_m / grid["gs"], 1.0)
    local_mean = ndimage.gaussian_filter(dtm, sigma=sigma_tpi, mode="nearest")
    tpi = dtm - local_mean
    tpi_norm = normalize(tpi)

    slope_y, slope_x = np.gradient(local_mean, grid["gs"])
    slope_deg = np.degrees(np.arctan(np.hypot(slope_x, slope_y)))
    slope_weight = np.exp(-np.square(slope_deg / prm.slope_pref_deg))

    raw_score = (0.6 * log_response + 0.4 * np.clip(tpi_norm, 0.0, 1.0)) * slope_weight
    ridge_score = normalize(raw_score)
    ridge_score = ndimage.gaussian_filter(ridge_score, sigma=1.0, mode="nearest")

    finite = ridge_score[np.isfinite(ridge_score)]
    thresh = np.percentile(finite, prm.ridge_binary_percentile) if finite.size else 0.0
    ridge_binary = (ridge_score >= thresh).astype(np.float32)
    ridge_binary = ndimage.binary_opening(
        ridge_binary, structure=np.ones((3, 3), dtype=bool)
    ).astype(np.float32)
    return ridge_score.astype(np.float32), ridge_binary, raw_score.astype(np.float32)


def compute_ground_density(
    las: laspy.LasData, prm: Params, grid: Dict[str, float]
) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(las.x, dtype=np.float32)
    y = np.asarray(las.y, dtype=np.float32)
    classification = np.asarray(las.classification, dtype=np.uint8)
    ground_mask = np.isin(classification, prm.density_classes)
    ground_x = x[ground_mask]
    ground_y = y[ground_mask]

    if ground_x.size == 0:
        return (
            np.zeros((grid["ny"], grid["nx"]), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
        )

    gs = prm.density_grid_size
    density_grid = compute_grid(ground_x, ground_y, gs)

    cols = np.clip(
        ((ground_x - density_grid["xmin"]) / gs).astype(np.int64),
        0,
        density_grid["nx"] - 1,
    )
    rows = np.clip(
        ((ground_y - density_grid["ymin"]) / gs).astype(np.int64),
        0,
        density_grid["ny"] - 1,
    )
    flat_size = density_grid["nx"] * density_grid["ny"]
    counts = np.bincount(rows * density_grid["nx"] + cols, minlength=flat_size).astype(
        np.float32
    )
    density = counts.reshape(density_grid["ny"], density_grid["nx"])
    density_raw = density.astype(np.float32, copy=True)
    valid_mask = density_raw > 0.0

    if not np.any(valid_mask):
        return (
            np.zeros((grid["ny"], grid["nx"]), dtype=np.float32),
            density_raw,
        )

    vmax = np.nanpercentile(density_raw[valid_mask], prm.density_percentile)
    if vmax <= 0:
        vmax = np.nanmax(density_raw[valid_mask])
    if vmax <= 0:
        vmax = 1.0

    density_norm = np.zeros_like(density_raw, dtype=np.float32)
    density_norm[valid_mask] = np.clip(
        density_raw[valid_mask] / vmax,
        0.0,
        1.0,
    )

    zoom_y = grid["ny"] / density_norm.shape[0]
    zoom_x = grid["nx"] / density_norm.shape[1]
    density_resampled = ndimage.zoom(density_norm, zoom=(zoom_y, zoom_x), order=1)
    mask_resampled = ndimage.zoom(
        valid_mask.astype(np.float32), zoom=(zoom_y, zoom_x), order=0
    )
    density_resampled *= (mask_resampled >= 0.5).astype(np.float32)
    density_resampled = density_resampled[: grid["ny"], : grid["nx"]]
    return density_resampled.astype(np.float32), density_raw


def compute_density_counts_grid(
    las: laspy.LasData, prm: Params, grid: Dict[str, float]
) -> np.ndarray:
    x = np.asarray(las.x, dtype=np.float32)
    y = np.asarray(las.y, dtype=np.float32)
    classification = np.asarray(las.classification, dtype=np.uint8)
    ground_mask = np.isin(classification, prm.density_classes)
    if not np.any(ground_mask):
        return np.zeros((grid["ny"], grid["nx"]), dtype=np.int32)

    x = x[ground_mask]
    y = y[ground_mask]
    cols = np.floor((x - grid["xmin"]) / grid["gs"]).astype(np.int64)
    rows = np.floor((y - grid["ymin"]) / grid["gs"]).astype(np.int64)
    valid = (cols >= 0) & (cols < grid["nx"]) & (rows >= 0) & (rows < grid["ny"])
    cols = cols[valid]
    rows = rows[valid]
    counts = np.zeros(grid["ny"] * grid["nx"], dtype=np.int32)
    np.add.at(counts, rows * grid["nx"] + cols, 1)
    return counts.reshape(grid["ny"], grid["nx"])


def compute_flatness_map(
    las: laspy.LasData, dtm: np.ndarray, prm: Params, grid: Dict[str, float]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(las.x, dtype=np.float32)
    y = np.asarray(las.y, dtype=np.float32)
    z = np.asarray(las.z, dtype=np.float32)
    classification = np.asarray(las.classification, dtype=np.uint8)
    flat_mask = np.isin(classification, prm.flatness_classes)
    x = x[flat_mask]
    y = y[flat_mask]
    z = z[flat_mask]
    if x.size == 0:
        empty = np.zeros((grid["ny"], grid["nx"]), dtype=np.float32)
        return empty, np.zeros((0,), dtype=np.float32), empty

    cols_main = np.floor((x - grid["xmin"]) / grid["gs"]).astype(np.int64)
    rows_main = np.floor((y - grid["ymin"]) / grid["gs"]).astype(np.int64)

    valid_mask = (
        (cols_main >= 0)
        & (cols_main < grid["nx"])
        & (rows_main >= 0)
        & (rows_main < grid["ny"])
    )
    cols_main = cols_main[valid_mask]
    rows_main = rows_main[valid_mask]
    x = x[valid_mask]
    y = y[valid_mask]
    z = z[valid_mask]

    dtm_values = dtm[rows_main, cols_main]
    nz = z - dtm_values

    lower, upper = prm.flat_band
    height_mask = (nz >= lower) & (nz <= upper)
    x = x[height_mask]
    y = y[height_mask]
    nz = nz[height_mask]
    if nz.size == 0:
        empty = np.zeros((grid["ny"], grid["nx"]), dtype=np.float32)
        return empty, np.zeros((0,), dtype=np.float32), empty

    flat_grid = compute_grid_from_extent(grid["extent"], prm.flat_grid_size)
    cols_flat = np.clip(
        ((x - flat_grid["xmin"]) / flat_grid["gs"]).astype(np.int64),
        0,
        flat_grid["nx"] - 1,
    )
    rows_flat = np.clip(
        ((y - flat_grid["ymin"]) / flat_grid["gs"]).astype(np.int64),
        0,
        flat_grid["ny"] - 1,
    )

    flat_size = flat_grid["nx"] * flat_grid["ny"]
    sum_z = np.zeros(flat_size, dtype=np.float64)
    sum_sq = np.zeros(flat_size, dtype=np.float64)
    counts = np.zeros(flat_size, dtype=np.float64)

    cell_ids = rows_flat * flat_grid["nx"] + cols_flat
    np.add.at(sum_z, cell_ids, nz)
    np.add.at(sum_sq, cell_ids, nz * nz)
    np.add.at(counts, cell_ids, 1.0)

    mean = np.zeros(flat_size, dtype=np.float64)
    valid = counts > 0
    mean[valid] = sum_z[valid] / counts[valid]
    variance = np.zeros(flat_size, dtype=np.float64)
    variance[valid] = np.maximum(sum_sq[valid] / counts[valid] - mean[valid] ** 2, 0.0)
    std = np.zeros(flat_size, dtype=np.float64)
    std[valid] = np.sqrt(variance[valid], dtype=np.float64)
    std[~valid] = np.nan

    std_grid_coarse = std.reshape(flat_grid["ny"], flat_grid["nx"]).astype(np.float32)
    roughness_norm = normalize(std_grid_coarse, lower=5.0, upper=prm.flat_percentile)
    flatness_coarse = 1.0 - roughness_norm
    flatness_coarse[~np.isfinite(flatness_coarse)] = 0.0

    mask_coarse = valid.reshape(flat_grid["ny"], flat_grid["nx"]).astype(np.float32)

    zoom_y = grid["ny"] / flatness_coarse.shape[0]
    zoom_x = grid["nx"] / flatness_coarse.shape[1]
    flatness_resampled = ndimage.zoom(
        flatness_coarse, zoom=(zoom_y, zoom_x), order=1
    ).astype(np.float32)
    mask_resampled = ndimage.zoom(mask_coarse, zoom=(zoom_y, zoom_x), order=0)
    flatness_resampled *= (mask_resampled >= 0.5).astype(np.float32)
    flatness_resampled = flatness_resampled[: grid["ny"], : grid["nx"]]
    counts_coarse = counts.reshape(flat_grid["ny"], flat_grid["nx"]).astype(np.float32)
    counts_resampled = ndimage.zoom(
        counts_coarse, zoom=(zoom_y, zoom_x), order=0
    ).astype(np.float32)
    counts_resampled = counts_resampled[: grid["ny"], : grid["nx"]]
    return flatness_resampled, std_grid_coarse, counts_resampled


def save_image(
    array: np.ndarray, extent: list[float], out_path: Path, cmap: str = "viridis"
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = _create_map_figure()
    im = ax.imshow(array, origin="lower", extent=extent, cmap=cmap, vmin=0, vmax=1)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(out_path.name)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.savefig(out_path, dpi=220)
    _log_image_save(out_path)
    plt.close(fig)


BINARY_CMAP = ListedColormap(["#ffffff", "#d0021b"])
BINARY_NORM = BoundaryNorm([-0.5, 0.5, 1.5], BINARY_CMAP.N)

DENSITY_LEVEL_STEP = 5
DENSITY_LEVEL_MAX_BIN = 4  # 0~20 grouped into four bins, 20+ is bin 4
DENSITY_LEVEL_COLORS = [
    "#ffffff",  # 0~5
    "#fee0d2",  # 5~10
    "#fcbba1",  # 10~15
    "#fb6a4a",  # 15~20
    "#cb181d",  # 20~
]
DENSITY_LEVEL_LABELS = [
    "[0~5)",
    "[5~10)",
    "[10~15)",
    "[15~20)",
    "[20~)",
]
DENSITY_LEVEL_TICKS = np.arange(DENSITY_LEVEL_MAX_BIN + 1)
DENSITY_LEVEL_NORM = BoundaryNorm(
    np.arange(-0.5, DENSITY_LEVEL_MAX_BIN + 1.5, 1.0),
    len(DENSITY_LEVEL_COLORS),
)
DENSITY_LEVEL_CMAP = ListedColormap(DENSITY_LEVEL_COLORS)


def save_histogram(array: np.ndarray, out_path: Path) -> None:
    data = array[np.isfinite(array)].ravel()
    if data.size == 0:
        return

    iqr = np.subtract(*np.percentile(data, [75, 25]))
    bin_width = 2.0 * iqr / np.cbrt(data.size) if data.size > 1 else 0.0
    if bin_width <= 0.0:
        bins = int(np.clip(np.sqrt(data.size), 10, 160))
    else:
        bins = int(np.clip(np.ceil((data.max() - data.min()) / bin_width), 10, 160))

    hist_vals, _, _ = plt.hist(data, bins=bins)
    plt.close()  # discard temp figure
    y_dynamic = (
        hist_vals.max() / max(hist_vals[hist_vals > 0])
        if np.any(hist_vals > 0)
        else 1.0
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.2, 4.2), constrained_layout=True)
    ax.hist(
        data,
        bins=bins,
        color="#4a90e2",
        edgecolor="#1f3d73",
        alpha=0.9,
    )
    if y_dynamic > 50:
        ax.set_yscale("log")

    mean = float(np.mean(data))
    median = float(np.median(data))
    ax.axvline(mean, color="#d0021b", linestyle="--", linewidth=1.0, label="Mean")
    ax.axvline(median, color="#50e3c2", linestyle=":", linewidth=1.3, label="Median")
    ax.legend(loc="upper right", frameon=False)

    ax.set_xlabel("Value")
    ax.set_ylabel("Count")
    ax.set_title(out_path.name)
    fig.savefig(out_path, dpi=220)
    _log_image_save(out_path)
    plt.close(fig)


def save_binary_mask(array: np.ndarray, extent: list[float], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = _create_map_figure()
    im = ax.imshow(
        array,
        origin="lower",
        extent=extent,
        cmap=BINARY_CMAP,
        norm=BINARY_NORM,
        interpolation="nearest",
    )
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(out_path.name)
    fig.colorbar(im, ax=ax, ticks=[0, 1], fraction=0.046, pad=0.04)
    fig.savefig(out_path, dpi=220)
    _log_image_save(out_path)
    plt.close(fig)
    np.save(out_path.with_suffix(".npy"), array.astype(np.uint8))


def save_density_level_map(
    counts: np.ndarray, extent: list[float], out_path: Path
) -> None:
    if counts.size == 0:
        return

    level_map = np.floor_divide(np.clip(counts, 0, None), DENSITY_LEVEL_STEP).astype(
        np.int16
    )
    level_map = np.clip(level_map, 0, DENSITY_LEVEL_MAX_BIN)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = _create_map_figure()
    im = ax.imshow(
        level_map,
        origin="lower",
        extent=extent,
        cmap=DENSITY_LEVEL_CMAP,
        norm=DENSITY_LEVEL_NORM,
        interpolation="nearest",
    )
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(out_path.name)
    cbar = fig.colorbar(
        im,
        ax=ax,
        fraction=0.046,
        pad=0.04,
        ticks=DENSITY_LEVEL_TICKS,
    )
    cbar.ax.set_yticklabels(DENSITY_LEVEL_LABELS)
    fig.savefig(out_path, dpi=220)
    _log_image_save(out_path)
    plt.close(fig)


def save_counts_heatmap(
    counts: np.ndarray, extent: list[float], out_path: Path, cmap: str = "Reds"
) -> None:
    if counts.size == 0:
        return

    vmax = float(np.max(counts))
    if vmax <= 0.0:
        vmax = 1.0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = _create_map_figure()
    im = ax.imshow(
        counts,
        origin="lower",
        extent=extent,
        cmap=cmap,
        vmin=0.0,
        vmax=vmax,
    )
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(out_path.name)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Point count")
    fig.savefig(out_path, dpi=220)
    _log_image_save(out_path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ridge extraction from point cloud DEM (merged_ome.las)."
    )
    parser.add_argument(
        "--las", type=Path, default=DEFAULT_LAS, help="Path to LAS/LAZ file."
    )
    parser.add_argument(
        "--out-dir", type=Path, default=OUTPUT_ROOT, help="Output directory."
    )
    args = parser.parse_args()

    prm = Params()
    las_path = args.las
    las = load_las(las_path)

    ground_mask = np.isin(las.classification, prm.dtm_classes)
    x = las.x[ground_mask]
    y = las.y[ground_mask]
    grid = compute_grid(x, y, prm.grid_size)

    dtm = build_dtm_from_points(las, prm, grid)
    ridge_score, ridge_binary, ridge_raw = compute_ridge_score(dtm, prm, grid)
    density, density_raw = compute_ground_density(las, prm, grid)
    density_counts = compute_density_counts_grid(las, prm, grid)
    flatness, flatness_raw, flat_counts = compute_flatness_map(las, dtm, prm, grid)
    combined = np.clip((ridge_score + density + flatness) / 3.0, 0.0, 1.0)

    las_name = las_path.stem
    image_dir = args.out_dir / las_name
    save_image(
        ridge_score, grid["extent"], image_dir / "01_ridge_score.png", cmap="magma"
    )
    save_image(
        density, grid["extent"], image_dir / "02_ground_density.png", cmap="viridis"
    )
    save_density_level_map(
        density_counts, grid["extent"], image_dir / "02_ground_density_levels.png"
    )
    save_binary_mask(
        (density_counts >= 10).astype(np.float32),
        grid["extent"],
        image_dir / "02_ground_density_ge10.png",
    )
    save_image(flatness, grid["extent"], image_dir / "03_flatness.png", cmap="cividis")
    save_counts_heatmap(
        flat_counts,
        grid["extent"],
        image_dir / "03_flatness_points.png",
    )
    save_image(
        combined, grid["extent"], image_dir / "04_combined_score.png", cmap="inferno"
    )
    save_histogram(
        ridge_raw,
        image_dir / "00_hist_ridge_raw.png",
    )
    save_histogram(
        density_raw[density_raw > 0],
        image_dir / "00_hist_density_raw.png",
    )
    save_histogram(
        flatness_raw,
        image_dir / "00_hist_flatness_raw.png",
    )

    thresholds = np.round(np.arange(0.5, 1.01, 0.1), 1)
    for thr in thresholds:
        binary = (combined >= thr).astype(np.float32)
        suffix = f"{int(round(thr * 10)):02d}"
        save_binary_mask(
            binary,
            grid["extent"],
            image_dir / f"05_combined_binary_{suffix}.png",
        )

    print(f"[done] outputs written to {image_dir}")


if __name__ == "__main__":
    main()
