const loadButton = document.getElementById('load-button');
const fileNameLabel = document.getElementById('file-name');
const pointCountLabel = document.getElementById('point-count');
const elevationRangeLabel = document.getElementById('elevation-range');
const extentLabel = document.getElementById('extent');
const meshSizeSelect = document.getElementById('mesh-size');
const gridSizeLabel = document.getElementById('grid-size');
const canvas = document.getElementById('dem-canvas');
const ctx = canvas.getContext('2d');

let currentPoints = [];
let currentStats = null;

const parsePointCloud = (raw) => {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
    .map((line) => {
      const values = line
        .split(/[\s,]+/)
        .map((value) => Number.parseFloat(value))
        .filter((value) => !Number.isNaN(value));

      if (values.length < 3) {
        return null;
      }

      return { x: values[0], y: values[1], z: values[2] };
    })
    .filter(Boolean);
};

const computeStats = (points) => {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const zs = points.map((p) => p.z);

  const min = (arr) => Math.min(...arr);
  const max = (arr) => Math.max(...arr);

  return {
    minX: min(xs),
    maxX: max(xs),
    minY: min(ys),
    maxY: max(ys),
    minZ: min(zs),
    maxZ: max(zs),
  };
};

const colorRamp = (t) => {
  // Smooth gradient from deep blue -> teal -> orange -> white
  const stops = [
    [0, [15, 23, 42]],
    [0.25, [34, 197, 94]],
    [0.5, [251, 191, 36]],
    [0.75, [249, 115, 22]],
    [1, [255, 255, 255]],
  ];

  let lower = stops[0];
  let upper = stops[stops.length - 1];

  for (let i = 0; i < stops.length - 1; i += 1) {
    if (t >= stops[i][0] && t <= stops[i + 1][0]) {
      lower = stops[i];
      upper = stops[i + 1];
      break;
    }
  }

  const localT = (t - lower[0]) / (upper[0] - lower[0]);
  const mix = (a, b) => Math.round(a + (b - a) * localT);

  return [mix(lower[1][0], upper[1][0]), mix(lower[1][1], upper[1][1]), mix(lower[1][2], upper[1][2])];
};

const buildGrid = (points, meshSize, stats) => {
  const width = Math.max(2, Math.round((stats.maxX - stats.minX) / meshSize) + 1);
  const height = Math.max(2, Math.round((stats.maxY - stats.minY) / meshSize) + 1);
  const xScale = (width - 1) / (stats.maxX - stats.minX || 1);
  const yScale = (height - 1) / (stats.maxY - stats.minY || 1);

  const grid = new Array(width * height).fill(null).map(() => ({ sum: 0, count: 0 }));

  points.forEach((point) => {
    const xIndex = Math.min(width - 1, Math.max(0, Math.round((point.x - stats.minX) * xScale)));
    const yIndex = Math.min(height - 1, Math.max(0, Math.round((point.y - stats.minY) * yScale)));
    const idx = yIndex * width + xIndex;
    grid[idx].sum += point.z;
    grid[idx].count += 1;
  });

  const heights = new Float32Array(width * height);
  const defaultHeight = (stats.minZ + stats.maxZ) / 2;

  grid.forEach((cell, idx) => {
    heights[idx] = cell.count > 0 ? cell.sum / cell.count : defaultHeight;
  });

  // simple smoothing to remove holes
  const smoothed = new Float32Array(width * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let sum = 0;
      let count = 0;
      for (let ky = -1; ky <= 1; ky += 1) {
        for (let kx = -1; kx <= 1; kx += 1) {
          const nx = x + kx;
          const ny = y + ky;
          if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
            sum += heights[ny * width + nx];
            count += 1;
          }
        }
      }
      smoothed[y * width + x] = sum / count;
    }
  }

  return { data: smoothed, width, height };
};

const renderDem = (grid, stats) => {
  const { data, width, height } = grid;
  const min = stats.minZ;
  const max = stats.maxZ;
  const range = max - min || 1;

  canvas.width = width;
  canvas.height = height;

  const imageData = ctx.createImageData(width, height);
  for (let i = 0; i < data.length; i += 1) {
    const normalized = Math.min(1, Math.max(0, (data[i] - min) / range));
    const [r, g, b] = colorRamp(normalized);
    imageData.data[i * 4 + 0] = r;
    imageData.data[i * 4 + 1] = g;
    imageData.data[i * 4 + 2] = b;
    imageData.data[i * 4 + 3] = 255;
  }

  ctx.putImageData(imageData, 0, 0);
};

const formatNumber = (value) => value.toLocaleString('ja-JP', { maximumFractionDigits: 0 });

const formatRange = (min, max, unit = 'm') => `${min.toFixed(2)}〜${max.toFixed(2)} ${unit}`;

const formatExtent = (stats) => {
  const dx = stats.maxX - stats.minX;
  const dy = stats.maxY - stats.minY;
  return `${dx.toFixed(1)} × ${dy.toFixed(1)} m`;
};

const refresh = () => {
  if (!currentPoints.length || !currentStats) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    gridSizeLabel.textContent = '-';
    return;
  }

  const meshSize = Number.parseFloat(meshSizeSelect.value);
  const grid = buildGrid(currentPoints, meshSize, currentStats);
  gridSizeLabel.textContent = `${grid.width} × ${grid.height}`;
  renderDem(grid, currentStats);
};

const handleLoad = async () => {
  const response = await window.pointCloudApi.chooseFile();
  if (!response || response.canceled) {
    return;
  }

  const points = parsePointCloud(response.raw);
  if (!points.length) {
    alert('点群を正しく読み込めませんでした。x y z 形式のテキストであることを確認してください。');
    return;
  }

  currentPoints = points;
  currentStats = computeStats(points);

  fileNameLabel.textContent = response.fileName;
  pointCountLabel.textContent = formatNumber(points.length);
  elevationRangeLabel.textContent = formatRange(currentStats.minZ, currentStats.maxZ);
  extentLabel.textContent = formatExtent(currentStats);

  refresh();
};

loadButton.addEventListener('click', handleLoad);
meshSizeSelect.addEventListener('change', refresh);
