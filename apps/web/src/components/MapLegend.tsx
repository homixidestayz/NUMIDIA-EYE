import type { Dict } from "../i18n";

interface Props {
  dict: Dict;
}

/**
 * Compact legend describing exactly what the map layers mean.
 *
 * A cluster count is a number of satellite detections grouped in view. It is
 * not a count of fires, incidents, or AI-verified anything, and the wording
 * deliberately says so.
 */
export default function MapLegend({ dict }: Props) {
  return (
    <div className="legend" aria-label={dict.legend_title}>
      <div className="legend-title">{dict.legend_title}</div>
      <div className="legend-item">
        <span className="legend-swatch legend-swatch-live" aria-hidden="true" />
        <span>{dict.legend_live}</span>
      </div>
      <div className="legend-item">
        <span className="legend-swatch legend-swatch-historical" aria-hidden="true" />
        <span>{dict.legend_historical}</span>
      </div>
      <div className="legend-item">
        <span className="legend-swatch legend-swatch-cluster" aria-hidden="true" />
        <span>{dict.legend_cluster}</span>
      </div>
    </div>
  );
}