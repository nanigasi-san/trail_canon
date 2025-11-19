export class DemService {
  buildGrid(points, meshSize, stats) {
    if (!points.length || !stats) {
      return null;
    }

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

    const smoothed = this.smooth(heights, width, height);

    return { data: smoothed, width, height };
  }

  smooth(source, width, height) {
    const result = new Float32Array(width * height);
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        let sum = 0;
        let count = 0;
        for (let ky = -1; ky <= 1; ky += 1) {
          for (let kx = -1; kx <= 1; kx += 1) {
            const nx = x + kx;
            const ny = y + ky;
            if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
              sum += source[ny * width + nx];
              count += 1;
            }
          }
        }
        result[y * width + x] = sum / count;
      }
    }
    return result;
  }
}
