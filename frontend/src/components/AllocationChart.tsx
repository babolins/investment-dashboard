import { useState } from "react";
import type { AllocationBreakdown } from "../types";

const BUCKET_COLORS: Record<string, string> = {
  VTI: "#1B3A6B",
  VXUS: "#4AACE8",
  BND: "#6B7A23",
};

const fmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

interface Props {
  breakdown: AllocationBreakdown;
  bucketSymbols?: Record<string, string[]>;
}

const CX = 110, CY = 110, INNER_R = 60, OUTER_R = 100;

function polar(cx: number, cy: number, r: number, deg: number) {
  const rad = ((deg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function donutSlice(startDeg: number, endDeg: number): string {
  const s = polar(CX, CY, OUTER_R, startDeg);
  const e = polar(CX, CY, OUTER_R, endDeg);
  const si = polar(CX, CY, INNER_R, endDeg);
  const ei = polar(CX, CY, INNER_R, startDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return [
    `M ${s.x} ${s.y}`,
    `A ${OUTER_R} ${OUTER_R} 0 ${large} 1 ${e.x} ${e.y}`,
    `L ${si.x} ${si.y}`,
    `A ${INNER_R} ${INNER_R} 0 ${large} 0 ${ei.x} ${ei.y}`,
    "Z",
  ].join(" ");
}

export default function AllocationChart({ breakdown, bucketSymbols = {} }: Props) {
  const { buckets, included_value, excluded_value } = breakdown;
  const [hovered, setHovered] = useState<string | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);

  const total = buckets.reduce((s, b) => s + b.current_value, 0);

  let angle = 0;
  const slices = buckets.map((b) => {
    const sweep = total > 0 ? (b.current_value / total) * 360 : 0;
    const start = angle;
    angle += sweep;
    return { ...b, start, end: angle };
  });

  const hb = hovered ? buckets.find((b) => b.bucket === hovered) : null;
  const tickers = hovered ? (bucketSymbols[hovered] ?? []) : [];

  return (
    <div className="card allocation-card">
      <h2>Asset Allocation</h2>
      <p className="hint">As of today · included value {fmt.format(included_value)}</p>

      <div className="chart-layout">
        <div style={{ position: "relative", width: 220, height: 220 }}>
          <svg
            width={220}
            height={220}
            onMouseLeave={() => { setHovered(null); setTip(null); }}
          >
            {slices.map((s) => (
              <path
                key={s.bucket}
                d={donutSlice(s.start, s.end)}
                fill={BUCKET_COLORS[s.bucket] ?? "#ccc"}
                stroke="#fff"
                strokeWidth={2}
                opacity={hovered && hovered !== s.bucket ? 0.6 : 1}
                style={{ cursor: "pointer" }}
                onMouseEnter={(e) => {
                  setHovered(s.bucket);
                  const r = (e.currentTarget.closest("svg") as SVGSVGElement).getBoundingClientRect();
                  setTip({ x: e.clientX - r.left, y: e.clientY - r.top });
                }}
                onMouseMove={(e) => {
                  const r = (e.currentTarget.closest("svg") as SVGSVGElement).getBoundingClientRect();
                  setTip({ x: e.clientX - r.left, y: e.clientY - r.top });
                }}
              />
            ))}
          </svg>

          {hb && tip && (
            <div
              className="chart-tooltip"
              style={{ position: "absolute", left: tip.x + 12, top: tip.y - 10, pointerEvents: "none" }}
            >
              <strong>{hb.bucket}</strong>
              <div>{fmt.format(hb.current_value)}</div>
              <div>{hb.percent_of_included.toFixed(1)}%</div>
              {tickers.length > 0 && <div className="tooltip-tickers">{tickers.join(", ")}</div>}
            </div>
          )}
        </div>

        <div className="chart-legend">
          {buckets.map((b) => (
            <div key={b.bucket} className="legend-row">
              <span className="legend-dot" style={{ background: BUCKET_COLORS[b.bucket] ?? "#999" }} />
              <span className="legend-label">{b.bucket}</span>
              <span className="legend-pct">{b.percent_of_included.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>

      {excluded_value > 0 && (
        <p className="hint excluded-note">
          {fmt.format(excluded_value)} in excluded symbols (cash / money-market) not shown.
        </p>
      )}
    </div>
  );
}
