# Trail Canon

Electron ベースのデスクトップアプリとして、オリエンテーリング用の地図作成で役立つ DEM プレビューを素早く生成します。点群ファイル（`.xyz`, `.csv`, `.txt` などの x y z 形式）を読み込むと、ヒートマップ表現の DEM を表示し、データ件数や標高範囲などの指標を確認できます。

## 機能

- デスクトップアプリ（Electron）として動作
- 点群ファイルの読み込み（数値 3 列形式）
- DEM のラスタライズとスムージング
- 0.1〜10m のメッシュサイズを切り替えて DEM を再生成
- シンプルで情報量の多い UI とメッシュ設定パネル
- ステータスメッセージでファイル読込状況やエラーを通知

## セットアップ

```bash
npm install
npm start
```

### Codex 環境での `npm install` 失敗について

Codex の実行環境では `https://registry.npmjs.org/electron` へのアクセスがセキュリティポリシーでブロックされており、`npm install` 実行時に `npm ERR! code E403` で停止します。これは Electron のメタデータそのものがダウンロードできないために起こるもので、`npm config` や `.npmrc` を書き換えても解消できません。

- **Codex 上ではビルド不可:** 依存解決の前段階で拒否されるため、コンテナ内での `npm install` は失敗したままになります。
- **手元では問題なし:** インターネットに直接接続できるローカル PC 等で `npm install` を実行すれば通常通り Electron を取得できます。
- **Electron を個別取得する場合:** もし社内リポジトリやキャッシュがある場合は、Electron の tarball をあらかじめダウンロードし、`ELECTRON_CUSTOM_DIR` と `ELECTRON_MIRROR` を利用して参照する方法があります（詳細は [Electron ドキュメント](https://www.electronjs.org/docs/latest/tutorial/installation#custom-mirrors-and-caches) を参照してください）。

したがって Codex での検証はアプリのソース閲覧に留め、動作確認やビルドはローカル環境で実行してください。

### サンプルデータ

`samples/sample_hill.xyz` に簡単な点群を用意しています。フォーマット確認や DEM 描画のテストに利用できます。

## 点群データのフォーマット

- 1 行につき `x y z`（スペース区切り）または `x,y,z`（カンマ区切り）
- コメント行がある場合は `#` で始まる行として扱います
- 単位はメートルを想定しています

## 今後のアイデア

- 点群の属性（反射強度など）の取り込み
- 斜面解析や陰影起伏図の追加
- GeoTIFF などへのエクスポート

## アーキテクチャと拡張

- メイン／プリロード／レンダラーの責務分離やサービス・ビュークラス構成など、詳細な実装ガイドは [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) に記載しています。
- 新しい解析処理は `src/renderer/services/`、UI パネルは `src/renderer/view/` に追加し、`src/renderer/app.js` から状態連携する構造になっています。
