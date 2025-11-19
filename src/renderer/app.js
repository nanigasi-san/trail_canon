import { AppState } from './core/appState.js';
import { DemService } from './services/demService.js';
import { PointCloudService } from './services/pointCloudService.js';
import { PanelView } from './view/panelView.js';
import { CanvasRenderer } from './view/canvasRenderer.js';

const state = new AppState();
const pointCloudService = new PointCloudService();
const demService = new DemService();

const elements = {
  fileName: document.getElementById('file-name'),
  pointCount: document.getElementById('point-count'),
  elevationRange: document.getElementById('elevation-range'),
  extent: document.getElementById('extent'),
  gridSize: document.getElementById('grid-size'),
  message: document.getElementById('status-message'),
};

const panelView = new PanelView(elements);
const canvasRenderer = new CanvasRenderer(document.getElementById('dem-canvas'));
const meshSizeSelect = document.getElementById('mesh-size');
const loadButton = document.getElementById('load-button');
meshSizeSelect.value = state.getSnapshot().meshSize.toString();

const rebuildGrid = () => {
  const snapshot = state.getSnapshot();
  if (!snapshot.points.length || !snapshot.stats) {
    state.update({ grid: null });
    return;
  }

  const grid = demService.buildGrid(snapshot.points, snapshot.meshSize, snapshot.stats);
  state.update({ grid });
};

state.subscribe((snapshot) => {
  panelView.render(snapshot);
  if (snapshot.grid && snapshot.stats) {
    canvasRenderer.render(snapshot.grid, snapshot.stats);
  } else {
    canvasRenderer.clear();
  }
});

const handleLoad = async () => {
  state.update({ message: '点群を読み込んでいます…' });
  let response;
  try {
    response = await window.pointCloudApi.choosePointCloud();
  } catch (error) {
    state.update({ message: `ファイルダイアログでエラーが発生しました: ${error.message}` });
    return;
  }

  if (!response || response.canceled) {
    state.update({ message: '読み込みはキャンセルされました。' });
    return;
  }

  const points = pointCloudService.parse(response.raw);
  if (!points.length) {
    state.update({ message: '点群を正しく読み込めませんでした。フォーマットを確認してください。' });
    return;
  }

  const stats = pointCloudService.computeStats(points);
  state.update({
    fileName: response.fileName,
    points,
    stats,
    message: `${points.length.toLocaleString('ja-JP')} 点を読み込みました。`,
  });

  rebuildGrid();
};

loadButton.addEventListener('click', handleLoad);
meshSizeSelect.addEventListener('change', (event) => {
  const meshSize = Number.parseFloat(event.target.value);
  state.update({ meshSize });
  rebuildGrid();
});
