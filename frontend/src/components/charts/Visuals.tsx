import { hexToRgb, lerpRgb, rgbCss, clamp } from '../../lib/math';

/* ---------- colour helpers ---------- */
export const heatColor = (v: number, lo: number, hi: number) =>
  rgbCss(lerpRgb(hexToRgb('#e4b95a'), hexToRgb('#b8402a'), clamp((v - lo) / (hi - lo), 0, 1)));
export const greenColor = (v: number, lo: number, hi: number) =>
  rgbCss(lerpRgb(hexToRgb('#d9c9a0'), hexToRgb('#2e7d4f'), clamp((v - lo) / (hi - lo), 0, 1)));
export const waterColor = (v: number) =>
  rgbCss(lerpRgb(hexToRgb('#a9c7de'), hexToRgb('#1f5a8c'), clamp(v, 0, 1)));

/* ---------- Bar with value ---------- */
export function BarRow({
  label,
  value,
  max,
  display,
  color = 'var(--leaf)',
  marker,
  right,
}: {
  label: string;
  value: number;
  max: number;
  display: string;
  color?: string;
  /** Optional marker position, same scale as value (for a target line) */
  marker?: number;
  right?: string;
}) {
  return (
    <div className="barrow">
      <span className="barrow__label">{label}</span>
      <div className="barrow__track" role="img" aria-label={`${label}: ${display}`}>
        <i style={{ width: `${clamp((value / max) * 100, 0, 100)}%`, background: color }} />
        {marker !== undefined && <u style={{ left: `${clamp((marker / max) * 100, 0, 100)}%` }} />}
      </div>
      <span className="barrow__val">{display}</span>
      {right && <span className="barrow__right">{right}</span>}
    </div>
  );
}

/* ---------- Ring ---------- */
export function Ring({ value, target, caption }: { value: number; target: number; caption: string }) {
  const C = 2 * Math.PI * 50;
  const frac = clamp(value / target, 0, 1);
  return (
    <div className="ring">
      <svg viewBox="0 0 120 120" role="img" aria-label={`${value.toFixed(1)}% of ${target}% target`}>
        <circle className="ring__t" cx="60" cy="60" r="50" />
        <circle className="ring__a" cx="60" cy="60" r="50" strokeDasharray={`${(C * frac).toFixed(1)} ${C.toFixed(1)}`} />
      </svg>
      <div className="ring__c">
        {value.toFixed(1)}%<small>{caption}</small>
      </div>
    </div>
  );
}

/* ---------- Conceptual tile map ---------- */
export interface Tile {
  id: string;
  label: string;
  display: string;
  color: string;
  col: number;
  row: number;
  dimmed?: boolean;
  /** dark text on light tiles */
  darkText?: boolean;
}

export function ConceptMap({
  tiles,
  selectedId,
  onSelect,
  ariaLabel,
  cols = 3,
  rows = 2,
}: {
  tiles: Tile[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  ariaLabel: string;
  cols?: number;
  rows?: number;
}) {
  return (
    <figure className="cmap">
      <div className="cmap__grid" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${rows}, 1fr)` }} role="group" aria-label={ariaLabel}>
        {tiles.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`cmap__tile${selectedId === t.id ? ' is-on' : ''}${t.dimmed ? ' is-dim' : ''}${t.darkText ? ' dark' : ''}`}
            style={{ gridColumn: t.col + 1, gridRow: t.row + 1, background: t.color }}
            aria-pressed={selectedId === t.id}
            onClick={() => onSelect(t.id)}
          >
            <span>{t.label}</span>
            <b>{t.display}</b>
          </button>
        ))}
      </div>
      <figcaption className="note">
        Conceptual tile layout. Tile positions are illustrative and do not show real geography; values are the measured ward figures listed below.
      </figcaption>
    </figure>
  );
}

/* ---------- Street scene (before/after illustration, adapted from the prototype) ---------- */
const BUILDINGS = [[14, 44, 70], [66, 36, 98], [110, 50, 62], [168, 40, 112], [216, 46, 80], [270, 38, 94], [316, 50, 68], [374, 40, 102], [422, 44, 76]];
const TREE_GREENS = ['#2e7d4f', '#4a9a68', '#6fb27a'];

/** g: 0 = dusty and bare, 1 = green, clear and cool roofs. Illustration only. */
export function StreetScene({ greenness, label }: { greenness: number; label: string }) {
  const g = clamp(greenness, 0, 1);
  const sky0 = rgbCss(lerpRgb(hexToRgb('#b9a98f'), hexToRgb('#cfe4ee'), g));
  const sky1 = rgbCss(lerpRgb(hexToRgb('#d8c6a8'), hexToRgb('#eef4ee'), g));
  const bld = rgbCss(lerpRgb(hexToRgb('#5d5650'), hexToRgb('#6b7b84'), g));
  const ground = rgbCss(lerpRgb(hexToRgb('#8a7a66'), hexToRgb('#8fae94'), g));
  const coolN = Math.round(g * BUILDINGS.length);
  const trees = Math.round(g * 14);
  const gid = `sky-${Math.round(g * 100)}-${label.length}`;
  return (
    <svg className="scene" viewBox="0 0 480 160" role="img" aria-label={label}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={sky0} />
          <stop offset="1" stopColor={sky1} />
        </linearGradient>
      </defs>
      <rect width="480" height="160" fill={`url(#${gid})`} />
      <rect y="142" width="480" height="18" fill={ground} />
      {BUILDINGS.map((b, i) => {
        const top = 142 - b[2];
        const windows: JSX.Element[] = [];
        for (let wy = top + 12; wy < 134; wy += 16)
          for (let wx = b[0] + 7; wx < b[0] + b[1] - 8; wx += 12)
            windows.push(<rect key={`${wx}-${wy}`} x={wx} y={wy} width="6" height="8" fill="#f1ead8" opacity="0.7" />);
        return (
          <g key={i}>
            <rect x={b[0]} y={top} width={b[1]} height={b[2]} fill={bld} />
            {windows}
            <rect x={b[0] - 2} y={top - 6} width={b[1] + 4} height="7" fill={i < coolN ? '#f4f7f6' : '#3a3f43'} />
          </g>
        );
      })}
      {Array.from({ length: trees }).map((_, i) => {
        const tx = 10 + i * 34 + (i % 2) * 6;
        return (
          <g key={i}>
            <rect x={tx - 2} y="128" width="4" height="16" fill="#6b5240" />
            <circle cx={tx} cy="122" r={10 + (i % 3) * 2} fill={TREE_GREENS[i % 3]} />
          </g>
        );
      })}
      <rect width="480" height="160" fill="#8a735a" opacity={(1 - g) * 0.28} />
    </svg>
  );
}
