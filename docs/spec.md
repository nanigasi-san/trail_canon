# TrailDetector v0.1 仕様書（FastAPI + React + Vite）

## 1. アプリ概要

### 1.1 目的

本アプリは、航空機 LiDAR 点群データから以下の指標を計算し、トレイル候補を視覚的に確認するためのツールとする。

- RI: Ridge Index（尾根度）
- GPD: Ground Point Density（地表点密度）
- UOI: Undergrowth Openness Index（下草開放度）
- Trail Score: 上記3指標を統合したトレイルスコア

v0.1 では、**点群を読み込み → 4指標を計算 → 4枚の画像として UI 上に表示**するところまでを扱う。トレイルラインの抽出や精度評価（IoU など）はスコープ外とする。

---

## 2. 使用技術と開発環境

### 2.1 バックエンド環境（Python 側）

- 言語: **Python 3.12** 系（uv で管理）
- パッケージマネージャ / 環境管理: **uv**
- 仮想環境名: `trail-detector-backend`
- 想定ライブラリ:
  - `fastapi`
  - `uvicorn[standard]`
  - `laspy`
  - `numpy`
  - `scipy`
  - `matplotlib` または `Pillow`（PNG 出力用途）
  - `pydantic`（FastAPI 経由で入る）

バックエンドは uv プロジェクトとして管理する想定:

```bash
uv init --package trail_detector_backend
uv add fastapi uvicorn[standard] laspy numpy scipy matplotlib
```

### 2.2 フロントエンド環境（React 側）

- 言語: **TypeScript 5 系**
- ライブラリ: **React 18 系**
- ビルドツール: **Vite 5 系**
- パッケージマネージャ: **npm**（標準的な構成。必要なら pnpm/yarn に変更可）

Vite テンプレートからの作成例:

```bash
npm create vite@latest trail-detector-frontend -- --template react-ts
cd trail-detector-frontend
npm install
```

開発中は:

```bash
npm run dev
```

でローカル開発サーバを起動し、バックエンド FastAPI は別プロセスで `http://127.0.0.1:8000` などに立てて連携する。

### 2.3 実行環境

- OS: Windows 10 / 11
- バックエンド: ローカルホスト上で FastAPI（Uvicorn）を起動
- フロントエンド: ブラウザから Vite Dev サーバ経由でアクセス
- 将来的に Electron で統合し、単一のデスクトップアプリにすることを想定

---

## 3. 計算する指標の定義

### 3.1 DEM

- 入力: 地表点（classification 2, 22 等）
- 出力: 規則格子 DEM（float32, 2D 配列）
- 手順:
  1. 点群から地表点のみ抽出
  2. グリッドパラメータ（xmin, xmax, ymin, ymax, nx, ny, grid_size）を算出
  3. `scipy.interpolate.griddata` (linear + nearest 補完) で格子上に標高を補間

### 3.2 RI（Ridge Index: 尾根度）

#### 3.2.1 TPI

- `local_mean(z)` を Gaussian filter（σ = tpi_scale_m / grid_size）で計算
- `TPI = z - local_mean(z)`
- パーセンタイル（例: 5〜95%）でクリップして 0〜1 に線形正規化

#### 3.2.2 LoG 尾根応答

- スケール `ridge_scales_m = (3, 6, 9)` [m] について、
  - σ = scale_m / grid_size
  - `-gaussian_laplace(dtm, sigma)` を計算
  - 各スケールごとに 0〜1 に正規化
- 3スケールの最大値を取って尾根強度マップを作成

#### 3.2.3 斜度ガウス重み

- `local_mean` から勾配を計算し、斜度 `s` [deg] を求める
- ガウス重み: `G(s) = exp(-(s^2) / (2 * σ^2))` （σ = slope_pref_deg, 例: 20°）

#### 3.2.4 RI の最終式

- `LoG_norm`: 3スケールの LoG 応答を正規化し、max を取ったもの
- `TPI_norm`: 正規化した TPI
- `slope_weight`: G(s)

```text
raw_score = (0.6 * LoG_norm + 0.4 * clamp(TPI_norm, 0, 1)) * slope_weight
RI = normalize(raw_score)   # 0〜1 に正規化
```

### 3.3 GPD（Ground Point Density: 地表点密度）

- 定義:

```text
GPD = n / A  [pts/m^2]
```

  - n: セル内の地表点数
  - A: セル面積（grid_size^2）

- 実装:
  - 地表クラス（density_classes, 初期値 (2,)）のみ抽出
  - grid_size 間隔でビンカウントして密度を計算
  - 値の分布の上位パーセンタイル（density_percentile, 例: 99%）を上限として 0〜1 に正規化
  - DEM グリッドと同じ解像度に揃える（必要なら ndimage.zoom でリサンプリング）

### 3.4 UOI（Undergrowth Openness Index: 下草開放度）

- 地表高から一定範囲（例: 0〜1m）の点群の高さ集合 z の標準偏差 std を計算し、

```text
UOI_raw = std(z)  # 各セル内での地表からの相対高さの標準偏差
```

- std が小さいほど下草が少なく「開放度が高い」とみなす
- 実装:
  1. 指定クラス（flatness_classes）から対象点を抽出
  2. DEM からの相対高さ `nz = z - dtm` を計算
  3. 高さバンド（height_band, 例: 0〜1m）内の点のみ残す
  4. 指定グリッドで std を計算
  5. std をパーセンタイル（flat_percentile）で正規化 → [0,1]
  6. `UOI = 1 - normalize(std)` として「開放度」指標に変換

### 3.5 Trail Score（トレイルスコア）

- 正規化済み RI, GPD, UOI を単純平均:

```text
TrailScore = (RI + GPD + UOI) / 3
```

- いずれも 0〜1 の配列として扱う

---

## 4. 機能要件

### 4.1 ユーザーフロー

1. 「点群読み込みモード」で LAS/LAZ ファイル（1つ以上）を指定
2. grid_size（DEM 解像度）など必要なパラメータを入力
3. 「トレイル候補を検出」ボタンを押す
4. バックエンドで RI / GPD / UOI / TrailScore を計算
5. 完了後、以下 4枚の PNG 画像が UI に表示される:
   - 尾根度（RI）
   - 地表点密度（GPD）
   - 下草開放度（UOI）
   - トレイルスコア（TrailScore）

### 4.2 入力

- pointcloud_files: string[] （LAS/LAZ ファイルパスの配列）
- grid_size: float
- output_dir: string
- params: オプションのパラメータセット（無指定時は既定値を使用）

### 4.3 出力

- status: "ok" or "error"
- extent: [xmin, xmax, ymin, ymax]
- images: 4指標ごとの PNG へのパスまたは URL

例:

```json
{
  "status": "ok",
  "extent": [xmin, xmax, ymin, ymax],
  "images": {
    "ridge": "/static/results/20251120/ridge.png",
    "gpd": "/static/results/20251120/gpd.png",
    "uoi": "/static/results/20251120/uoi.png",
    "trail_score": "/static/results/20251120/trail_score.png"
  }
}
```

---

## 5. API 仕様（シンプル版）

### 5.1 POST /trail/detect

点群から DEM・RI・GPD・UOI・TrailScore を計算し、4枚の PNG を生成する。

#### Request Body

```json
{
  "pointcloud_files": [
    "C:/data/ome/merged_ome.las"
  ],
  "grid_size": 1.0,
  "output_dir": "C:/data/ome/output",
  "params": {
    "ridge_scales_m": [3.0, 6.0, 9.0],
    "tpi_scale_m": 15.0,
    "slope_pref_deg": 20.0,
    "density_percentile": 99.0,
    "uoi_height_band": [0.0, 1.0],
    "uoi_percentile": 95.0
  }
}
```

#### Response Body (成功時)

```json
{
  "status": "ok",
  "extent": [xmin, xmax, ymin, ymax],
  "images": {
    "ridge": "/static/results/20251120/ridge.png",
    "gpd": "/static/results/20251120/gpd.png",
    "uoi": "/static/results/20251120/uoi.png",
    "trail_score": "/static/results/20251120/trail_score.png"
  }
}
```

#### Response Body (失敗時)

```json
{
  "status": "error",
  "message": "error reason here"
}
```

---

## 6. フロントエンド仕様

### 6.1 画面構成

1. 上部コントロールエリア
   - 点群ファイルパス入力（テキスト or 単一ファイル）
   - grid_size 入力
   - 「トレイル候補を検出」ボタン
   - 処理中インジケータ

2. 下部結果表示エリア
   - 2×2 グリッドで 4枚の画像表示
     - 左上: RI
     - 右上: GPD
     - 左下: UOI
     - 右下: TrailScore
   - それぞれにタイトルラベル

### 6.2 処理フロー

1. ボタン押下で `POST /trail/detect` を呼ぶ
2. レスポンスの images オブジェクトから PNG のパスを取得
3. `<img>` にセットして表示
4. status が error の場合はメッセージを表示

---

## 7. ディレクトリ構造

### 7.1 ルート構成

```text
trail-detector/
  backend/                  # FastAPI + アルゴリズム（Python, uv 管理）
    app/
      main.py               # FastAPI エントリポイント
      schemas.py            # Pydantic モデル（リクエスト/レスポンス定義）
      core/
        algorithms.py       # 点群→DEM/RI/GPD/UOI/TrailScore の全アルゴリズム
      config.py             # デフォルトパラメータ・パス設定
    pyproject.toml          # uv 用プロジェクト定義

  frontend/                 # React + TypeScript + Vite
    src/
      main.tsx              # React エントリ
      App.tsx               # 画面全体の構成
      api.ts                # POST /trail/detect を叩く HTTP クライアント
      components/
        Controls.tsx        # ファイルパス/グリッドサイズなどの入力 UI
        ResultGrid.tsx      # RI/GPD/UOI/TrailScore 4枚の画像を表示
    index.html
    vite.config.ts
    package.json
    tsconfig.json

  README.md                 # プロジェクト概要とセットアップ手順
  docs/
    spec.md                 # この仕様書
```

### 7.2 バックエンド内部の責務分担

- `app/main.py`
  - FastAPI アプリ生成
  - ルーティング定義（`POST /trail/detect`）
  - 画像保存先ディレクトリの決定

- `app/schemas.py`
  - リクエストボディ（点群ファイルパス、grid_size、各種パラメータ）の Pydantic モデル
  - レスポンス（status, extent, images）の Pydantic モデル

- `app/core/algorithms.py`
  - `TrailParams`（grid_size, ridge_scales_m, 等）の定義
  - `compute_dem_from_las()`
  - `compute_ri()`
  - `compute_gpd()`
  - `compute_uoi()`
  - `compute_trail_score()`
  - `run_trail_detection()`（上記をまとめて呼ぶ高レベル関数）

- `app/config.py`
  - デフォルトのパラメータ値
  - 出力ディレクトリのベースパス設定 など

---

## 8. バックエンド内部仕様（core/algorithms.py）

`core/algorithms.py` に、点群→各種指標→トレイルスコアのロジックを集約する。

### 8.1 公開インターフェース

```python
# core/algorithms.py

from typing import Dict, List, Tuple
import numpy as np

class TrailParams(BaseModel) または dataclass:
    grid_size: float = 1.0
    ridge_scales_m: Tuple[float, float, float] = (3.0, 6.0, 9.0)
    tpi_scale_m: float = 15.0
    slope_pref_deg: float = 20.0
    density_percentile: float = 99.0
    uoi_height_band: Tuple[float, float] = (0.0, 1.0)
    uoi_percentile: float = 95.0
    # classification に関するパラメータもここで管理


def compute_dem_from_las(las_files: List[str], params: TrailParams) -> Tuple[np.ndarray, Dict[str, float]]:
    """地表点から DEM を生成して返す。grid 情報（extent, nx, ny 等）も返す。"""
    ...


def compute_ri(dem: np.ndarray, grid: Dict[str, float], params: TrailParams) -> np.ndarray:
    """DEM から RI(0〜1) を計算する。"""
    ...


def compute_gpd(las_files: List[str], grid: Dict[str, float], params: TrailParams) -> np.ndarray:
    """点群から GPD(0〜1) を計算する。"""
    ...


def compute_uoi(las_files: List[str], dem: np.ndarray, grid: Dict[str, float], params: TrailParams) -> np.ndarray:
    """点群と DEM から UOI(0〜1) を計算する。"""
    ...


def compute_trail_score(ri: np.ndarray, gpd: np.ndarray, uoi: np.ndarray) -> np.ndarray:
    """3指標から TrailScore(0〜1) を計算する。"""
    return np.clip((ri + gpd + uoi) / 3.0, 0.0, 1.0)


def run_trail_detection(las_files: List[str], params: TrailParams) -> Dict[str, np.ndarray]:
    """点群ファイル群から RI/GPD/UOI/TrailScore を一括で計算する高レベル関数。"""
    dem, grid = compute_dem_from_las(las_files, params)
    ri = compute_ri(dem, grid, params)
    gpd = compute_gpd(las_files, grid, params)
    uoi = compute_uoi(las_files, dem, grid, params)
    score = compute_trail_score(ri, gpd, uoi)
    return {
        "dem": dem,
        "ri": ri,
        "gpd": gpd,
        "uoi": uoi,
        "trail_score": score,
        "grid": grid,
    }
```

### 8.2 main.py からの呼び出し

- `POST /trail/detect` で受け取ったファイルパス・パラメータを `TrailParams` に詰める
- `run_trail_detection()` を呼び出し、戻り値の配列を PNG に変換して保存
- PNG のパスをレスポンス JSON に含める

---

## 9. エラー処理

- 点群ファイルが存在しない
- LAS 読み込みに失敗
- 地表点が存在しない
- DEM 生成に失敗
- PNG 出力に失敗

いずれも `status: "error"` としてエラーメッセージを返す。

---

## 10. まとめ

- v0.1 では **点群 → DEM → RI/GPD/UOI → TrailScore → 4枚PNG表示** に限定
- バックエンドは FastAPI、フロントは React + Vite
- アルゴリズムは `core/algorithms.py` に集約し、将来的な拡張に対応できる構造とする

