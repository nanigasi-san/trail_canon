import { colorRamp } from '../utils/colorRamp.js';

export class CanvasRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
  }

  clear() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  render(grid, stats) {
    if (!grid || !stats) {
      this.clear();
      return;
    }

    const { data, width, height } = grid;
    const min = stats.minZ;
    const max = stats.maxZ;
    const range = max - min || 1;

    this.canvas.width = width;
    this.canvas.height = height;

    const imageData = this.ctx.createImageData(width, height);
    for (let i = 0; i < data.length; i += 1) {
      const normalized = Math.min(1, Math.max(0, (data[i] - min) / range));
      const [r, g, b] = colorRamp(normalized);
      imageData.data[i * 4 + 0] = r;
      imageData.data[i * 4 + 1] = g;
      imageData.data[i * 4 + 2] = b;
      imageData.data[i * 4 + 3] = 255;
    }

    this.ctx.putImageData(imageData, 0, 0);
  }
}
