export const formatNumber = (value) =>
  value.toLocaleString('ja-JP', {
    maximumFractionDigits: 0,
  });

export const formatRange = (min, max, unit = 'm') => {
  if (Number.isNaN(min) || Number.isNaN(max)) {
    return '-';
  }
  return `${min.toFixed(2)}〜${max.toFixed(2)} ${unit}`;
};

export const formatExtent = (stats) => {
  if (!stats) {
    return '-';
  }
  const dx = stats.maxX - stats.minX;
  const dy = stats.maxY - stats.minY;
  return `${dx.toFixed(1)} × ${dy.toFixed(1)} m`;
};
