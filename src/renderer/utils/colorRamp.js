export const colorRamp = (t) => {
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

  const localT = (t - lower[0]) / (upper[0] - lower[0] || 1);
  const mix = (a, b) => Math.round(a + (b - a) * localT);

  return [mix(lower[1][0], upper[1][0]), mix(lower[1][1], upper[1][1]), mix(lower[1][2], upper[1][2])];
};
