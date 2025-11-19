import { useState, type ChangeEvent } from "react";
import "./Controls.css";

export interface FormState {
  gridSize: string;
  outputDir: string;
  ridgeScales: string;
  tpiScale: string;
  slopePref: string;
  densityPercentile: string;
  gpdGridSize: string;
  gpdClasses: string;
  uoiHeightBand: string;
  uoiFlatGridSize: string;
  uoiClasses: string;
  uoiPercentile: string;
  showLegend: boolean;
}

interface ControlsProps {
  formState: FormState;
  onChange: (next: Partial<FormState>) => void;
  onSubmit: () => void;
  disabled: boolean;
  onFilesPicked: (files: FileList | null) => void;
  selectedFiles: File[];
}

/**
 * Form component responsible for collecting point cloud paths and parameter overrides.
 */
export function Controls({
  formState,
  onChange,
  onSubmit,
  disabled,
  onFilesPicked,
  selectedFiles,
}: ControlsProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  /**
   * Update text/number fields by name while preserving other form inputs.
   */
  const handleInput = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    onChange({ [name]: value });
  };

  /**
   * Special-case handler for boolean toggles (checkboxes) to keep typing explicit.
   */
  const handleCheckbox = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, checked } = event.target;
    onChange({ [name]: checked } as Partial<FormState>);
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
            placeholder="1.0"
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

      <label className="field checkbox-field">
        <span>凡例（0-1 カラーバー）を表示</span>
        <input
          type="checkbox"
          name="showLegend"
          checked={formState.showLegend}
          onChange={handleCheckbox}
        />
      </label>

      <button
        type="button"
        className={`advanced-toggle ${advancedOpen ? "open" : ""}`}
        onClick={() => setAdvancedOpen((prev) => !prev)}
      >
        <span>Advanced parameters</span>
        <span className="chevron" aria-hidden="true" />
      </button>
      <div className={`advanced-panel ${advancedOpen ? "open" : ""}`}>
        <div className="metric-section">
          <h4>尾根度 (Ridge Index / RI)</h4>
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
                placeholder="15"
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
                placeholder="20"
              />
            </label>
          </div>
        </div>

        <div className="metric-section">
          <h4>地表点密度 (Ground Point Density / GPD)</h4>
          <div className="field-grid">
            <label className="field">
              <span>Density percentile</span>
              <input
                type="number"
                step="1"
                name="densityPercentile"
                value={formState.densityPercentile}
                onChange={handleInput}
                placeholder="99"
              />
            </label>
            <label className="field">
              <span>Density grid size (m)</span>
              <input
                type="number"
                step="0.1"
                name="gpdGridSize"
                value={formState.gpdGridSize}
                onChange={handleInput}
                placeholder="1.0"
              />
            </label>
            <label className="field">
              <span>Density classes</span>
              <input
                type="text"
                name="gpdClasses"
                value={formState.gpdClasses}
                onChange={handleInput}
                placeholder="2"
              />
            </label>
          </div>
        </div>

        <div className="metric-section">
          <h4>下草開放度 (Undergrowth Openness / UOI)</h4>
          <div className="field-grid">
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
              <span>Flat grid size (m)</span>
              <input
                type="number"
                step="0.1"
                name="uoiFlatGridSize"
                value={formState.uoiFlatGridSize}
                onChange={handleInput}
                placeholder="1.0"
              />
            </label>
            <label className="field">
              <span>Flatness classes</span>
              <input
                type="text"
                name="uoiClasses"
                value={formState.uoiClasses}
                onChange={handleInput}
                placeholder="2,4,22"
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
                placeholder="95"
              />
            </label>
          </div>
        </div>
      </div>

      <button className="primary" type="button" onClick={onSubmit} disabled={disabled}>
        {disabled ? "Processing…" : "Run Trail Detection"}
      </button>
    </section>
  );
}
