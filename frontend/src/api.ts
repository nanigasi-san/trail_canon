export interface TrailParams {
  ridge_scales_m?: number[];
  tpi_scale_m?: number;
  slope_pref_deg?: number;
  density_percentile?: number;
  uoi_height_band?: number[];
  uoi_percentile?: number;
}

export interface TrailDetectOptions {
  files: File[];
  gridSize: number;
  outputDir?: string;
  params?: TrailParams;
  showLegend?: boolean;
}

export interface TrailImages {
  ridge: string;
  gpd: string;
  uoi: string;
  trail_score: string;
}

export interface TrailDetectResponse {
  status: "ok";
  extent: number[];
  images: TrailImages;
}

export interface TrailErrorResponse {
  status: "error";
  message: string;
}

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

/**
 * Remove undefined/null entries from the params object so the backend only receives real overrides.
 */
const sanitizeParams = (params?: TrailParams): TrailParams | undefined => {
  if (!params) return undefined;
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== null);
  if (!entries.length) return undefined;
  return Object.fromEntries(entries) as TrailParams;
};

/**
 * Ensure image URLs returned by the API resolve correctly regardless of dev/prod host.
 */
const toAbsoluteUrl = (path: string): string => {
  try {
    return new URL(path, `${API_BASE_URL}/`).toString();
  } catch {
    return path;
  }
};

/**
 * Upload LAS files plus parameter overrides and return the backend's detection payload.
 */
export async function detectTrails(options: TrailDetectOptions): Promise<TrailDetectResponse> {
  const formData = new FormData();
  if (!options.files.length) {
    throw new Error("No files provided.");
  }
  options.files.forEach((file) => {
    formData.append("files", file, file.name);
  });
  formData.append("grid_size", options.gridSize.toString());
  if (options.outputDir) {
    formData.append("output_dir", options.outputDir);
  }
  formData.append("show_legend", options.showLegend ? "true" : "false");
  const params = sanitizeParams(options.params);
  if (params) {
    formData.append("params", JSON.stringify(params));
  }

  const response = await fetch(`${API_BASE_URL}/trail/detect/upload`, {
    method: "POST",
    body: formData,
  });

  const data = await response.json().catch(() => null);

  if (!response.ok || !data) {
    const message =
      (data as TrailErrorResponse | null)?.message ??
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  if (data.status !== "ok") {
    throw new Error((data as TrailErrorResponse).message ?? "Processing failed.");
  }

  const typed = data as TrailDetectResponse;
  const absoluteImages: TrailImages = {
    ridge: toAbsoluteUrl(typed.images.ridge),
    gpd: toAbsoluteUrl(typed.images.gpd),
    uoi: toAbsoluteUrl(typed.images.uoi),
    trail_score: toAbsoluteUrl(typed.images.trail_score),
  };
  return { ...typed, images: absoluteImages };
}
