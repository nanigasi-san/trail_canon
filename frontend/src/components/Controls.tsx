import type { ChangeEvent } from "react";
import "./Controls.css";

export interface FormState {
  gridSize: string;
  outputDir: string;
  ridgeScales: string;
  tpiScale: string;
  slopePref: string;
  densityPercentile: string;
  uoiHeightBand: string;
  uoiPercentile: string;
}

interface ControlsProps {
  formState: FormState;
  onChange: (next: Partial<FormState>) => void;
  onSubmit: () => void;
  disabled: boolean;
  onFilesPicked: (files: FileList | null) => void;
  selectedFiles: File[];
}

export function Controls({
  formState,
  onChange,
  onSubmit,
  disabled,
  onFilesPicked,
  selectedFiles,
}: ControlsProps) {
  const handleInput = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    onChange({ [name]: value });
  };

  return (
    <section className="controls">
      <h2>Point Cloud Input</h2>
      <label className="field file-picker">
        <span>LAS / LAZ ファイルを選択</span>
        <input type="file" multiple accept=".las,.laz" onChange={(e) => onFilesPicked(e.target.files)} />
        {selectedFiles.length > 0 && (
          <ul className="file-list">
            {selectedFiles.map((file) => (
              <li key={`${file.name}-${file.lastModified}`}>{file.name}</li>
            ))}
          </ul>
        )}
      </label>

      <div className="field-grid">
        <label className="field">
          <span>Grid size (m)</span>
          <input
            type="number"
            step="0.1"
            min="0.1"
            name="gridSize"
            value={formState.gridSize}
            onChange={handleInput}
          />
        </label>

        <label className="field">
          <span>Output directory</span>
          <input
            type="text"
            name="outputDir"
            value={formState.outputDir}
            onChange={handleInput}
            placeholder="C:\results\trail_detector"
          />
        </label>
      </div>

      <h3>Advanced parameters</h3>
      <div className="field-grid">
        <label className="field">
          <span>Ridge scales (m)</span>
          <input
            type="text"
            name="ridgeScales"
            value={formState.ridgeScales}
            onChange={handleInput}
            placeholder="3,6,9"
          />
        </label>
        <label className="field">
          <span>TPI scale (m)</span>
          <input
            type="number"
            step="1"
            name="tpiScale"
            value={formState.tpiScale}
            onChange={handleInput}
          />
        </label>
        <label className="field">
          <span>Slope preference (deg)</span>
          <input
            type="number"
            step="1"
            name="slopePref"
            value={formState.slopePref}
            onChange={handleInput}
          />
        </label>
        <label className="field">
          <span>Density percentile</span>
          <input
            type="number"
            step="1"
            name="densityPercentile"
            value={formState.densityPercentile}
            onChange={handleInput}
          />
        </label>
        <label className="field">
          <span>UOI height band (m)</span>
          <input
            type="text"
            name="uoiHeightBand"
            value={formState.uoiHeightBand}
            onChange={handleInput}
            placeholder="0,1"
          />
        </label>
        <label className="field">
          <span>UOI percentile</span>
          <input
            type="number"
            step="1"
            name="uoiPercentile"
            value={formState.uoiPercentile}
            onChange={handleInput}
          />
        </label>
      </div>

      <button className="primary" type="button" onClick={onSubmit} disabled={disabled}>
        {disabled ? "Processing…" : "Run Trail Detection"}
      </button>
    </section>
  );
}
