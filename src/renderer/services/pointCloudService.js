export class PointCloudService {
  parse(raw) {
    if (!raw) {
      return [];
    }

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
  }

  computeStats(points) {
    if (!points.length) {
      return null;
    }

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
  }
}
