import type { TrailImages } from "../api";
import "./ResultGrid.css";

interface ResultGridProps {
  images: TrailImages;
  extent?: number[] | null;
}

const imageMeta = [
  { key: "ridge", label: "Ridge Index" },
  { key: "gpd", label: "Ground Point Density" },
  { key: "uoi", label: "Undergrowth Openness" },
  { key: "trail_score", label: "Trail Score" },
] as const;

export function ResultGrid({ images, extent }: ResultGridProps) {
  return (
    <section className="results">
      <div className="results-header">
        <h2>Results</h2>
        {extent && (
          <p className="extent">
            Extent&nbsp;
            <code>
              xmin {extent[0].toFixed(2)} · xmax {extent[1].toFixed(2)} · ymin {extent[2].toFixed(2)} · ymax{" "}
              {extent[3].toFixed(2)}
            </code>
          </p>
        )}
      </div>
      <div className="result-grid">
        {imageMeta.map(({ key, label }) => (
          <figure key={key}>
            <img src={images[key]} alt={label} loading="lazy" />
            <figcaption>{label}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
