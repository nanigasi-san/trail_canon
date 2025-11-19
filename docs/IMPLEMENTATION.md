# Trail Canon 実装ガイド

このドキュメントでは、Electron アプリとして構成された Trail Canon の主要コンポーネントと拡張ポイントを説明します。レイヤーごとの責務を把握しておくことで、機能追加や保守を安全に行えます。

## プロセス構成

| レイヤー | ファイル | 役割 |
| --- | --- | --- |
| メインプロセス | `src/main.js` | アプリライフサイクル管理、ウィンドウ生成、IPC ハンドラー登録。|
| プリロード | `src/preload.js` | セキュアな contextBridge を介してレンダラーへ API を公開。|
| レンダラープロセス | `src/renderer/**/*.js` | UI レンダリング、点群解析、DEM 生成。|

## メインプロセス

- `CHANNELS` オブジェクトで IPC チャネルを集中管理し、名前衝突を避けています。
- `registerAppEvents()` がライフサイクルイベント（`ready`, `activate`, `window-all-closed`）をまとめてセットアップし、マルチウィンドウ化にも対応しやすい構造です。
- `registerIpcHandlers()` で IPC を一元登録。ハンドラーは純粋関数（`handleChoosePointCloud`）として分離しているため、ユニットテストや別チャネル追加が容易です。

## プリロード

`src/preload.js` では `pointCloudApi` を `window` に公開しています。Electron セキュリティガイドラインに沿い、IPC で必要最小限のメソッド（`choosePointCloud`）のみを提供しています。今後 API を増やす場合はここに追加し、レンダラーとは Promise ベースでやり取りします。

## レンダラーの構造

レンダラーは「状態管理」「サービス」「ビュー」「エントリポイント」に分割されています。`index.html` からは `app.js` を ES Modules として読み込み、そこから各モジュールを compose します。

### 状態管理
- `core/appState.js` の `AppState` がアプリ全体の状態を保持します。
- `subscribe(listener)` でリアクティブに状態を監視でき、今後の機能追加でも同じ仕組みを流用できます。
- `update(patch)` は部分更新のほか関数を受け取れるため、複雑なトランザクションも表現できます。

### サービス層
- `services/pointCloudService.js` が点群のパースと統計値算出を担当。
- `services/demService.js` がメッシュ生成とスムージングを行い、描画に依存しない形のグリッドデータを返します。
- これらは純粋ロジックで副作用を持たないため、別 UI への転用やテストが容易です。

### ビュー層
- `view/panelView.js` はファイル情報やステータスメッセージ等の UI 更新のみを担当。
- `view/canvasRenderer.js` はキャンバス描画とカラーマップ適用に責務を限定し、`utils/colorRamp.js` と連携します。
- 書式処理や共通関数は `utils/format.js` に集約しています。

### エントリポイント
- `app.js` がイベントバインディングやサービス呼び出しを調整するオーケストレーターです。
- 状態変更に応じて PanelView／CanvasRenderer を再描画し、メッシュ解像度の切り替えもここから `DemService` を呼び出します。

## データフロー

1. ユーザーが「点群を読み込む」を押すと、`pointCloudApi.choosePointCloud()` 経由でファイルを取得。
2. `PointCloudService` がパースし、`AppState` に点群と統計値を保存。
3. `DemService.buildGrid()` が選択メッシュに合わせた `grid` を生成。
4. 状態更新を購読している `PanelView` と `CanvasRenderer` が自動的に再描画。
5. メッシュサイズ変更時も同様のフローで `grid` を再計算します。

## 拡張ガイド

- **分析ロジック追加:** 新しい解析を行いたい場合は `services/` 配下にクラスを追加し、`app.js` で生成・状態へ保存してください。ビューは状態のサブセットを描画するだけに保ちます。
- **UI 機能追加:** 新しいパネルやコントロールを追加する際は、専用の View クラスを `view/` に置き、`app.js` から状態更新・イベント連携を行います。
- **IPC 拡張:** 追加のファイル操作やネイティブ機能が必要な場合は `CHANNELS` に識別子を追加し、`preload.js` と `pointCloudApi` を通して公開してください。

この構造を守ることで、機能が増えても各レイヤーの責務を明確に保てます。
