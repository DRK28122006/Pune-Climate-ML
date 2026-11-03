import { useId, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { clamp } from '../../lib/math';

export interface Band {
  from: number;
  to: number;
  label: string;
  fill: string;
}

interface Props {
  values: number[];
  xLabels: string[];
  /** Show every n-th x label */
  labelEvery?: number;
  yMax: number;
  yMin?: number;
  yTicks: number[];
  unit?: string;
  yLabel: string;
  xLabel: string;
  ariaLabel: string;
  bands?: Band[];
  compare?: { values: number[]; label: string };
  seriesLabel?: string;
  decimals?: number;
}

const W = 640, H = 280, L = 52, R = 24, T = 16, B = 46;

/** Responsive SVG line chart with bands, hover/touch/keyboard readout and optional comparison series. */
export default function LineChart(p: Props) {
  const uid = useId();
  const n = p.values.length;
  const yMin = p.yMin ?? 0;
  const [hover, setHover] = useState<number | null>(null);
  const x = (i: number) => L + (n === 1 ? 0 : (i * (W - L - R)) / (n - 1));
  const y = (v: number) => T + (1 - (v - yMin) / (p.yMax - yMin)) * (H - T - B);
  const dec = p.decimals ?? 0;

  if (n === 0) return <div className="state state--empty">No data available for this chart.</div>;

  const idxFromEvent = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const ux = ((e.clientX - r.left) / r.width) * W;
    return clamp(Math.round(((ux - L) / (W - L - R)) * (n - 1)), 0, n - 1);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === 'ArrowRight') { setHover((h) => clamp((h ?? -1) + 1, 0, n - 1)); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') { setHover((h) => clamp((h ?? n) - 1, 0, n - 1)); e.preventDefault(); }
    else if (e.key === 'Escape') setHover(null);
  };

  const path = (vals: number[]) => vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const every = p.labelEvery ?? 1;
  const hi = hover;
  const textRight = hi !== null && hi < n * 0.65;

  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={p.ariaLabel}
        tabIndex={0}
        onPointerMove={(e) => setHover(idxFromEvent(e))}
        onPointerDown={(e) => setHover(idxFromEvent(e))}
        onPointerLeave={() => setHover(null)}
        onKeyDown={onKey}
        onBlur={() => setHover(null)}
      >
        <title id={`${uid}-t`}>{p.ariaLabel}</title>
        {p.bands?.map((b) => (
          <g key={b.label}>
            <rect x={L} y={y(Math.min(b.to, p.yMax))} width={W - L - R} height={y(b.from) - y(Math.min(b.to, p.yMax))} fill={b.fill} />
            <text className="c-band" x={L + 8} y={y(Math.min(b.to, p.yMax)) + 15}>{b.label}</text>
          </g>
        ))}
        {p.yTicks.map((t) => (
          <g key={t}>
            <line className="c-grid" x1={L} x2={W - R} y1={y(t)} y2={y(t)} />
            <text className="c-axis" x={L - 8} y={y(t) + 4} textAnchor="end">{t}</text>
          </g>
        ))}
        {p.xLabels.map((l, i) =>
          i % every === 0 ? (
            <text key={i} className="c-axis" x={x(i)} y={H - B + 18} textAnchor="middle">{l}</text>
          ) : null,
        )}
        <text className="c-axis c-title" x={(L + W - R) / 2} y={H - 6} textAnchor="middle">{p.xLabel}</text>
        <text className="c-axis c-title" transform={`translate(14 ${(T + H - B) / 2}) rotate(-90)`} textAnchor="middle">{p.yLabel}</text>

        {p.compare && <polyline className="c-line c-line--ghost" points={path(p.compare.values)} />}
        <polyline className="c-line" points={path(p.values)} />
        <circle className="c-dot" cx={x(n - 1)} cy={y(p.values[n - 1])} r="5" />

        {hi !== null && (
          <g>
            <line className="c-hov" x1={x(hi)} x2={x(hi)} y1={T} y2={H - B} />
            <circle className="c-dot" cx={x(hi)} cy={y(p.values[hi])} r="5.5" />
            <text
              className="c-label"
              x={textRight ? x(hi) + 12 : x(hi) - 12}
              y={clamp(y(p.values[hi]) - 12, T + 12, H - B - 6)}
              textAnchor={textRight ? 'start' : 'end'}
            >
              {p.xLabels[hi]}: {p.values[hi].toFixed(dec)}{p.unit ?? ''}
              {p.compare ? ` (${p.compare.label} ${p.compare.values[hi].toFixed(dec)}${p.unit ?? ''})` : ''}
            </text>
          </g>
        )}
      </svg>
      <p className="note chart__hint">Hover, tap, or use the arrow keys to read a value.{p.compare ? ` Dashed line: ${p.compare.label}.` : ''}</p>
    </div>
  );
}
