import { useState } from "react";
import "./App.css";
import { detectTrails, type TrailImages } from "./api";
import { Controls, type FormState } from "./components/Controls";
import { ResultGrid } from "./components/ResultGrid";

const initialFormState: FormState = {
  gridSize: "1",
  outputDir: "./trail_results",
  ridgeScales: "3,6,9",
  tpiScale: "15",
  slopePref: "20",
  densityPercentile: "99",
  uoiHeightBand: "0,1",
  uoiPercentile: "95",
  showLegend: false,
};

function App() {
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [images, setImages] = useState<TrailImages | null>(null);
  const [extent, setExtent] = useState<number[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("Provide point cloud paths to begin.");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  const handleFormChange = (next: Partial<FormState>) => {
    setFormState((prev) => ({ ...prev, ...next }));
  };

  const handleFilesPicked = (fileList: FileList | null) => {
    const files = fileList ? Array.from(fileList) : [];
    setSelectedFiles(files);
  };

  const parseList = (value: string): number[] | undefined => {
    const parts = value
      .split(/[, \r\n]+/)
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => Number(part));
    return parts.length ? parts : undefined;
  };

  const handleSubmit = async () => {
    if (!selectedFiles.length) {
      setError("LAS/LAZ ファイルを選択してください。");
      return;
    }

    const gridSize = Number(formState.gridSize) || 1;
    const payload = {
      files: selectedFiles,
      gridSize,
      outputDir: formState.outputDir.trim() || undefined,
      showLegend: formState.showLegend,
      params: {
        ridge_scales_m: parseList(formState.ridgeScales),
        tpi_scale_m: Number(formState.tpiScale) || undefined,
        slope_pref_deg: Number(formState.slopePref) || undefined,
        density_percentile: Number(formState.densityPercentile) || undefined,
        uoi_height_band: parseList(formState.uoiHeightBand),
        uoi_percentile: Number(formState.uoiPercentile) || undefined,
      },
    };

    setLoading(true);
    setImages(null);
    setExtent(null);
    setError(null);
    setStatus("Processing...");

    try {
      const response = await detectTrails(payload);
      setImages(response.images);
      setExtent(response.extent);
      setStatus("Completed successfully.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setStatus("Failed to process data.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header>
        <div>
          <p className="eyebrow">TrailDetector v0.1</p>
          <h1>LiDAR Trail Metric Dashboard</h1>
          <p className="status">{status}</p>
        </div>
        {error && <p className="error">{error}</p>}
      </header>
      <main>
        <Controls
          formState={formState}
          onChange={handleFormChange}
          onSubmit={handleSubmit}
          disabled={loading}
          onFilesPicked={handleFilesPicked}
          selectedFiles={selectedFiles}
        />
        {images && <ResultGrid images={images} extent={extent ?? undefined} />}
      </main>
    </div>
  );
}

export default App;
