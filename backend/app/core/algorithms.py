"""LiDAR 点群からトレイル指標 (RI/GPD/UOI/Score) を生成するための計算群。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import laspy
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, field_validator
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter, gaussian_laplace, zoom


# ---- データ構造と設定パラメータ -------------------------------------------------
@dataclass(slots=True)
class Grid:
    """DEM や派生ラスタの格子情報を表すシンプルな構造体。"""

    xmin: float
    xmax: float
    ymin: float
    ymax: float
    nx: int
    ny: int
    grid_size: float

    @property
    def extent(self) -> Tuple[float, float, float, float]:
        return (self.xmin, self.xmax, self.ymin, self.ymax)

    @property
    def shape(self) -> Tuple[int, int]:
        return (self.ny, self.nx)

    def to_metadata(self) -> Dict[str, float | int | Tuple[float, float, float, float]]:
        return {
            "xmin": self.xmin,
            "xmax": self.xmax,
            "ymin": self.ymin,
            "ymax": self.ymax,
            "nx": self.nx,
            "ny": self.ny,
            "grid_size": self.grid_size,
            "extent": self.extent,
        }


@dataclass(slots=True)
class PointCloud:
    """LAS/LAZ を numpy 配列に展開して保持する軽量キャッシュ。"""

    x: NDArray[np.float64]
    y: NDArray[np.float64]
    z: NDArray[np.float64]
    classification: NDArray[np.int32]


class TrailParams(BaseModel):
    """トレイル検出のチューニング項目。UI からの入力をそのまま保持する。"""

    # --- DEM/ラスタ解像度 ---
    grid_size: float = Field(1.0, gt=0)
    sample_max_points: int = Field(5_000_000, gt=0)
    # --- リッジ検出 (RI) ---
    ridge_scales_m: Tuple[float, float, float] = (3.0, 6.0, 9.0)
    tpi_scale_m: float = Field(15.0, gt=0)
    tpi_percentiles: Tuple[float, float] = (5.0, 95.0)
    log_percentiles: Tuple[float, float] = (5.0, 95.0)
    slope_pref_deg: float = Field(20.0, gt=0.0)
    slope_sigma_deg: float = Field(20.0, gt=0.0)
    # --- 地上点密度 (GPD) ---
    density_percentile: float = Field(99.0, gt=0.0, le=100.0)
    density_grid_size: float = Field(1.0, gt=0.0)
    density_classes: Tuple[int, ...] = (2,)
    # --- DEM 作成時に地面とみなす分類 ---
    ground_classes: Tuple[int, ...] = (2, 22)
    # --- 低木帯 (UOI/フラットネス) ---
    uoi_height_band: Tuple[float, float] = (0.0, 1.0)
    uoi_percentile: float = Field(95.0, gt=0.0, le=100.0)
    flat_grid_size: float = Field(1.0, gt=0.0)
    flatness_classes: Tuple[int, ...] = (2, 4, 22)
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


# ---- 入出力ヘルパー -----------------------------------------------------------
def _load_point_cloud(las_files: Sequence[str]) -> PointCloud:
    """複数 LAS/LAZ を読み込み、後段の計算が扱いやすい numpy 配列へ展開する。

    Args:
        las_files: 読み込む LAS/LAZ ファイルパスのシーケンス。

    Returns:
        PointCloud: x/y/z 座標と classification を numpy 配列で保持した構造体。
    """
    xs: List[NDArray[np.float64]] = []
    ys: List[NDArray[np.float64]] = []
    zs: List[NDArray[np.float64]] = []
    classes: List[NDArray[np.int32]] = []

    for file_path in las_files:
        # 各ファイルを絶対パス化して存在チェック
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Point cloud file not found: {path}")
        las = laspy.read(path)
        # laspy の lazio オブジェクトから生配列を一気に取り出す
        xs.append(np.asarray(las.x, dtype=np.float64))
        ys.append(np.asarray(las.y, dtype=np.float64))
        zs.append(np.asarray(las.z, dtype=np.float64))
        classes.append(np.asarray(las.classification, dtype=np.int32))

    if not xs:
        raise ValueError("No LAS/LAZ files supplied.")

    # リスト化したチャンクを 1 本の配列へ結合
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    z = np.concatenate(zs)
    classification = np.concatenate(classes)
    return PointCloud(x=x, y=y, z=z, classification=classification)


def _filter_by_classes(
    point_cloud: PointCloud, classes: Iterable[int]
) -> NDArray[np.bool_]:
    """LAS 分類コードから対象クラスのみ True になるブーリアンマスクを作る。

    Args:
        point_cloud: 全 LAS 点群を格納した PointCloud。
        classes: True にしたい分類コードのイテラブル。

    Returns:
        np.ndarray: 元配列と同じ長さの bool マスク。
    """
    class_array = np.array(list(classes), dtype=np.int32)
    return np.isin(point_cloud.classification, class_array)


def _build_grid(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    grid_size: float,
) -> Tuple[NDArray[np.float64], NDArray[np.float64], Grid]:
    """点群の外接矩形から DEM 用の規則グリッドを生成する。

    Args:
        x: 点群の X 座標配列。
        y: 点群の Y 座標配列。
        grid_size: セルサイズ（メートル）。

    Returns:
        tuple: meshgrid 結果 (grid_x, grid_y) と Grid メタデータ。
    """
    xmin = float(np.min(x))
    xmax = float(np.max(x))
    ymin = float(np.min(y))
    ymax = float(np.max(y))

    # 最低 2x2 を確保しつつ、端を含むよう +1 セルする
    nx = max(int(np.ceil((xmax - xmin) / grid_size)) + 1, 2)
    ny = max(int(np.ceil((ymax - ymin) / grid_size)) + 1, 2)

    x_coords = xmin + np.arange(nx, dtype=np.float64) * grid_size
    y_coords = ymin + np.arange(ny, dtype=np.float64) * grid_size
    grid_x, grid_y = np.meshgrid(x_coords, y_coords)

    xmax = float(x_coords[-1])
    ymax = float(y_coords[-1])
    grid = Grid(
        xmin=xmin,
        xmax=xmax,
        ymin=ymin,
        ymax=ymax,
        nx=nx,
        ny=ny,
        grid_size=grid_size,
    )
    return grid_x, grid_y, grid


def _grid_from_extent(
    extent: Tuple[float, float, float, float], grid_size: float
) -> Grid:
    """既知の範囲を任意解像度で敷き詰める際のグリッドメタデータを生成する。

    Args:
        extent: (xmin, xmax, ymin, ymax) の範囲。
        grid_size: 解像度（メートル）。

    Returns:
        Grid: 指定範囲を覆う格子情報。
    """
    xmin, xmax, ymin, ymax = extent
    nx = max(int(np.ceil((xmax - xmin) / grid_size)) + 1, 2)
    ny = max(int(np.ceil((ymax - ymin) / grid_size)) + 1, 2)
    xmax = xmin + (nx - 1) * grid_size
    ymax = ymin + (ny - 1) * grid_size
    return Grid(
        xmin=xmin,
        xmax=xmax,
        ymin=ymin,
        ymax=ymax,
        nx=nx,
        ny=ny,
        grid_size=grid_size,
    )


def _normalize(
    array: NDArray[np.floating], lower: float = 5.0, upper: float = 95.0
) -> NDArray[np.float32]:
    """分布の下位/上位パーセンタイルで強制スケーリングし、0-1 正規化する。

    Args:
        array: スカラー値の配列。
        lower: 下側パーセンタイル。
        upper: 上側パーセンタイル。

    Returns:
        np.ndarray: 0〜1 に正規化された配列。
    """
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros_like(array, dtype=np.float32)
    lo = float(np.percentile(finite, lower))
    hi = float(np.percentile(finite, upper))
    if np.isclose(hi, lo):
        hi = lo + 1e-6
    normalized = (array - lo) / (hi - lo)
    return np.clip(normalized, 0.0, 1.0).astype(np.float32)


def _resample_to_grid(
    data: NDArray[np.floating],
    mask: Optional[NDArray[np.bool_]],
    grid: Grid,
) -> NDArray[np.float32]:
    """粗いラスタを最終 DEM と同じ解像度へリサンプリングし、必要に応じてマスクを適用する。

    Args:
        data: リサンプリング対象の 2D 配列。
        mask: 有効セルを示す bool マスク。None ならマスクせずに拡大縮小。
        grid: 出力形状と寸法を持つ Grid。

    Returns:
        np.ndarray: grid.shape に合わせて拡大縮小し、マスク適用後の配列。
    """
    target_shape = grid.shape
    if data.shape != target_shape:
        # SciPy の zoom で連続的にリサンプリングし、エッジを超えないようズーム倍率を計算
        zoom_y = target_shape[0] / data.shape[0]
        zoom_x = target_shape[1] / data.shape[1]
        data = zoom(data, zoom=(zoom_y, zoom_x), order=1)
        if mask is not None:
            # マスクは最近傍で補間することで有効/無効の二値性を保つ
            mask_zoom = zoom(mask.astype(np.float32), zoom=(zoom_y, zoom_x), order=0)
            data *= (mask_zoom >= 0.5).astype(np.float32)
    data = data[: target_shape[0], : target_shape[1]]
    return data.astype(np.float32, copy=False)


def compute_dem_from_las(
    las_files: List[str],
    params: TrailParams,
    *,
    point_data: Optional[PointCloud] = None,
) -> Tuple[NDArray[np.float32], Grid]:
    """地面クラスの点だけを使って DEM を補間する。

    Args:
        las_files: 読み込む LAS/LAZ ファイルパスのリスト。
        params: グリッドサイズや分類フィルタを含む TrailParams。
        point_data: 既に読み込んだ PointCloud があれば再利用、無ければ読み込む。

    Returns:
        tuple: DEM の 2D 配列と対応する Grid。
    """
    # 呼び出し側で点群を共有できるよう point_data を受け取り、無ければ読み込む
    points = point_data or _load_point_cloud(las_files)
    mask = _filter_by_classes(points, params.ground_classes)
    if not np.any(mask):
        raise ValueError("No ground-classified points were found.")

    ground_x = points.x[mask]
    ground_y = points.y[mask]
    ground_z = points.z[mask]

    total = ground_x.size
    if total > params.sample_max_points:
        # 非常に大きい点群はランダムサンプリングして補間コストを抑える
        rng = np.random.default_rng(42)
        idx = rng.choice(total, params.sample_max_points, replace=False)
        ground_x = ground_x[idx]
        ground_y = ground_y[idx]
        ground_z = ground_z[idx]

    grid_x, grid_y, grid = _build_grid(ground_x, ground_y, params.grid_size)
    # 線形補間だけだと NaN が残るので最近傍と組み合わせて穴埋めする
    locations = np.column_stack((ground_x, ground_y))
    dem_linear = griddata(locations, ground_z, (grid_x, grid_y), method="linear")
    dem_nearest = griddata(locations, ground_z, (grid_x, grid_y), method="nearest")
    dem = np.where(np.isnan(dem_linear), dem_nearest, dem_linear)
    fill_value = np.nanmedian(ground_z)
    dem = np.nan_to_num(dem, nan=float(fill_value))
    return dem.astype(np.float32), grid


def compute_ri(
    dem: NDArray[np.float32],
    grid: Grid,
    params: TrailParams,
) -> NDArray[np.float32]:
    """LoG, TPI, 斜面重みを組み合わせてリッジ指数 (RI) を計算する。

    Args:
        dem: 地表高を表す 2D 配列。
        grid: dem に対応する格子情報。
        params: フィルタスケールや傾斜好みなどのパラメータ。

    Returns:
        np.ndarray: 0〜1 に正規化した RI ラスタ。
    """
    # --- LoG によるリッジ強調 (複数スケールで最大値を採用) ---
    log_maps: List[NDArray[np.float32]] = []
    for scale in params.ridge_scales_m:
        sigma = max(scale / grid.grid_size, 1.0)
        response = -gaussian_laplace(dem, sigma=sigma, mode="nearest")
        log_maps.append(
            _normalize(response, params.log_percentiles[0], params.log_percentiles[1])
        )
    log_response = (
        np.maximum.reduce(log_maps)
        if log_maps
        else np.zeros_like(dem, dtype=np.float32)
    )

    # --- Gaussian 平滑で得た局所平均との差分が TPI ---
    sigma_tpi = max(params.tpi_scale_m / grid.grid_size, 1.0)
    local_mean = gaussian_filter(dem, sigma=sigma_tpi, mode="nearest")
    tpi = dem - local_mean
    tpi_norm = _normalize(tpi, params.tpi_percentiles[0], params.tpi_percentiles[1])

    # --- 傾斜が好みの角度から外れるほどペナルティを与える ---
    grad_y, grad_x = np.gradient(local_mean, grid.grid_size, grid.grid_size)
    slope_deg = np.degrees(np.arctan(np.hypot(grad_x, grad_y)))
    slope_pref = max(params.slope_pref_deg, 1e-3)
    slope_weight = np.exp(-np.square(slope_deg / slope_pref)).astype(np.float32)

    # LoG と TPI をブレンドし、最後に 1m スケールで滑らかにする
    raw_score = (0.6 * log_response + 0.4 * np.clip(tpi_norm, 0.0, 1.0)) * slope_weight
    ridge_score = _normalize(raw_score)
    return gaussian_filter(ridge_score, sigma=1.0, mode="nearest").astype(np.float32)


def compute_gpd(
    grid: Grid,
    params: TrailParams,
    *,
    point_data: PointCloud,
) -> NDArray[np.float32]:
    """地上分類の点を数えて密度グリッドを作り、DEM と同じ解像度へ写像する。

    Args:
        grid: 出力を合わせたい最終格子。
        params: 密度の集計解像度や対象クラスを含む TrailParams。
        point_data: フィルタ対象となる PointCloud。

    Returns:
        np.ndarray: DEM 解像度に合わせた正規化済み GPD。
    """
    mask = _filter_by_classes(point_data, params.density_classes)
    if not np.any(mask):
        return np.zeros(grid.shape, dtype=np.float32)

    x = point_data.x[mask].astype(np.float64)
    y = point_data.y[mask].astype(np.float64)
    # GPD は任意のスケールで集計できるよう専用グリッドを作成
    density_grid = _grid_from_extent(grid.extent, params.density_grid_size)

    cols = np.clip(
        np.floor((x - density_grid.xmin) / density_grid.grid_size).astype(np.int64),
        0,
        density_grid.nx - 1,
    )
    rows = np.clip(
        np.floor((y - density_grid.ymin) / density_grid.grid_size).astype(np.int64),
        0,
        density_grid.ny - 1,
    )

    flat_size = density_grid.nx * density_grid.ny
    counts = np.bincount(rows * density_grid.nx + cols, minlength=flat_size).astype(
        np.float32
    )
    density = counts.reshape(density_grid.ny, density_grid.nx)

    valid_mask = density > 0.0
    if not np.any(valid_mask):
        return np.zeros(grid.shape, dtype=np.float32)

    vmax = float(np.percentile(density[valid_mask], params.density_percentile))
    if vmax <= 0:
        vmax = float(np.max(density[valid_mask]))
    if vmax <= 0:
        vmax = 1.0

    density_norm = np.zeros_like(density, dtype=np.float32)
    density_norm[valid_mask] = np.clip(density[valid_mask] / vmax, 0.0, 1.0)
    # GPD は最終レンダリング用の DEM グリッドへリサンプリングして返す
    return _resample_to_grid(density_norm, valid_mask, grid)


def compute_uoi(
    las_files: List[str],
    dem: NDArray[np.float32],
    grid: Grid,
    params: TrailParams,
    *,
    point_data: Optional[PointCloud] = None,
) -> NDArray[np.float32]:
    """低木帯の高さばらつきを標準偏差で測り、開放度 (UOI/平坦度) を算出する。

    Args:
        las_files: LAS/LAZ ファイルパス。point_data が無い場合に使用。
        dem: 地表の標高ラスタ。
        grid: DEM と同じ格子情報。
        params: フラットネス関連パラメータセット。
        point_data: 既に読み込んだ点群があれば渡す。

    Returns:
        np.ndarray: 低木帯の平坦度 (0〜1)。
    """
    points = point_data or _load_point_cloud(las_files)
    mask = _filter_by_classes(points, params.flatness_classes)
    if not np.any(mask):
        return np.zeros(grid.shape, dtype=np.float32)

    x = points.x[mask].astype(np.float64)
    y = points.y[mask].astype(np.float64)
    z = points.z[mask].astype(np.float64)

    cols_main = np.floor((x - grid.xmin) / grid.grid_size).astype(np.int64)
    rows_main = np.floor((y - grid.ymin) / grid.grid_size).astype(np.int64)
    valid = (
        (cols_main >= 0)
        & (cols_main < grid.nx)
        & (rows_main >= 0)
        & (rows_main < grid.ny)
    )
    if not np.any(valid):
        return np.zeros(grid.shape, dtype=np.float32)

    cols_main = cols_main[valid]
    rows_main = rows_main[valid]
    x = x[valid]
    y = y[valid]
    z = z[valid]

    dtm_values = dem[rows_main, cols_main]
    normalized_z = z - dtm_values

    # DEM からの相対高さ (低木の高さ帯) でフィルタする
    band_min, band_max = params.uoi_height_band
    height_mask = (normalized_z >= band_min) & (normalized_z <= band_max)
    if not np.any(height_mask):
        return np.zeros(grid.shape, dtype=np.float32)

    x = x[height_mask]
    y = y[height_mask]
    normalized_z = normalized_z[height_mask]

    # 平坦度の集計解像度 (flat_grid_size) に合わせた粗いグリッドを作る
    flat_grid = _grid_from_extent(grid.extent, params.flat_grid_size)
    cols_flat = np.clip(
        np.floor((x - flat_grid.xmin) / flat_grid.grid_size).astype(np.int64),
        0,
        flat_grid.nx - 1,
    )
    rows_flat = np.clip(
        np.floor((y - flat_grid.ymin) / flat_grid.grid_size).astype(np.int64),
        0,
        flat_grid.ny - 1,
    )

    flat_size = flat_grid.nx * flat_grid.ny
    sum_vals = np.zeros(flat_size, dtype=np.float64)
    sum_sq = np.zeros(flat_size, dtype=np.float64)
    counts = np.zeros(flat_size, dtype=np.float64)
    cell_ids = rows_flat * flat_grid.nx + cols_flat
    np.add.at(sum_vals, cell_ids, normalized_z)
    np.add.at(sum_sq, cell_ids, normalized_z * normalized_z)
    np.add.at(counts, cell_ids, 1.0)

    # 各セルで (平均, 分散, 標準偏差) を手計算することでメモリと速度を確保
    valid_cells = counts > 0
    mean = np.zeros_like(sum_vals)
    mean[valid_cells] = sum_vals[valid_cells] / counts[valid_cells]
    variance = np.zeros_like(sum_vals)
    variance[valid_cells] = np.maximum(
        sum_sq[valid_cells] / counts[valid_cells] - np.square(mean[valid_cells]),
        0.0,
    )
    std = np.full_like(sum_vals, np.nan, dtype=np.float64)
    std[valid_cells] = np.sqrt(variance[valid_cells])

    std_grid = std.reshape(flat_grid.ny, flat_grid.nx).astype(np.float32)
    roughness = _normalize(std_grid, 5.0, params.uoi_percentile)
    flatness = 1.0 - roughness
    flatness[~np.isfinite(flatness)] = 0.0

    # 最後に DEM グリッドへ拡大し、点が存在したセルのみ残す
    mask_coarse = valid_cells.reshape(flat_grid.ny, flat_grid.nx)
    return _resample_to_grid(flatness, mask_coarse, grid)


def compute_trail_score(
    ri: NDArray[np.float32],
    gpd: NDArray[np.float32],
    uoi: NDArray[np.float32],
) -> NDArray[np.float32]:
    """3 つの指標の平均を取り、0〜1 の最終スコアとして返す。

    Args:
        ri: Ridge Index ラスタ。
        gpd: Ground Point Density ラスタ。
        uoi: Undergrowth Openness ラスタ。

    Returns:
        np.ndarray: 3 指標の平均を 0〜1 にクリップした配列。
    """
    return np.clip((ri + gpd + uoi) / 3.0, 0.0, 1.0).astype(np.float32)


def run_trail_detection(
    las_files: List[str],
    params: TrailParams,
) -> Dict[str, object]:
    """LAS 入力から RI/GPD/UOI/Score をまとめて計算し、描画しやすい dict で返す。

    Args:
        las_files: 入力 LAS/LAZ のファイルパス群。
        params: トレイル検出用パラメータ。

    Returns:
        dict: dem/ri/gpd/uoi/trail_score/格子メタデータを含む辞書。
    """
    point_data = _load_point_cloud(las_files)
    # 点群の読み込みは高価なので後続へ参照を共有する
    dem, grid = compute_dem_from_las(las_files, params, point_data=point_data)
    ri = compute_ri(dem, grid, params)
    gpd = compute_gpd(grid, params, point_data=point_data)
    uoi = compute_uoi(las_files, dem, grid, params, point_data=point_data)
    score = compute_trail_score(ri, gpd, uoi)
    return {
        "dem": dem,
        "ri": ri,
        "gpd": gpd,
        "uoi": uoi,
        "trail_score": score,
        "grid": grid.to_metadata(),
    }
