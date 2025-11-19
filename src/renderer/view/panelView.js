import { formatExtent, formatNumber, formatRange } from '../utils/format.js';

export class PanelView {
  constructor(elements) {
    this.elements = elements;
  }

  render(state) {
    this.updateFile(state);
    this.updateStats(state);
    this.updateGrid(state);
    this.updateMessage(state.message);
  }

  updateFile(state) {
    this.elements.fileName.textContent = state.fileName;
    if (state.points.length) {
      this.elements.pointCount.textContent = formatNumber(state.points.length);
    } else {
      this.elements.pointCount.textContent = '-';
    }
  }

  updateStats(state) {
    if (state.stats) {
      this.elements.elevationRange.textContent = formatRange(state.stats.minZ, state.stats.maxZ);
      this.elements.extent.textContent = formatExtent(state.stats);
    } else {
      this.elements.elevationRange.textContent = '-';
      this.elements.extent.textContent = '-';
    }
  }

  updateGrid(state) {
    if (state.grid) {
      this.elements.gridSize.textContent = `${state.grid.width} × ${state.grid.height}`;
    } else {
      this.elements.gridSize.textContent = '-';
    }
  }

  updateMessage(message) {
    this.elements.message.textContent = message || '';
  }
}
