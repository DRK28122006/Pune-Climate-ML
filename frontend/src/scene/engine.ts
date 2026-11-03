/**
 * Canvas scene engine, adapted from the supplied "Growing Pune" prototype.
 * `p` is greenness from 0 (dusty, polluted) to 1 (clear, green).
 */
import { clamp, hexToRgb, lerpRgb, rgbCss, rng, type RGB } from '../lib/math';

const SKY_T0 = hexToRgb('#a89b8a'), SKY_T1 = hexToRgb('#8dbbd6');
const SKY_H0 = hexToRgb('#d3c2ab'), SKY_H1 = hexToRgb('#e4f0ea');
const SUN0 = hexToRgb('#e69a5c'), SUN1 = hexToRgb('#fff4c4');
const CL0 = hexToRgb('#a89a89'), CL1 = hexToRgb('#ffffff');
const HILL = [
  [hexToRgb('#b0a696'), hexToRgb('#9cc3a0')],
  [hexToRgb('#a2988a'), hexToRgb('#7dae88')],
  [hexToRgb('#8f8676'), hexToRgb('#5e9a71')],
];
const SOIL = hexToRgb('#7d7061'), GRASS = hexToRgb('#4a8a5f');
const BARK = hexToRgb('#6b5240'), TWIG = hexToRgb('#2e7d4f');
const BLD0 = hexToRgb('#625a54'), BLD1 = hexToRgb('#5f7b82');
const GREENS = ['#2e7d4f', '#4a9a68', '#6fb27a', '#216a42'];
const TAU = 6.2832;

interface Seg { x: number; y: number; x2: number; y2: number; d: number; t0: number; t1: number }
interface Leaf { x: number; y: number; t: number; s: number; k: number; rot: number; ci: number }
interface Block { x: number; w: number; h: number; th: number; id: number; bush: number }
interface Cloud { x0: number; y: number; s: number; v: number }
interface Dust { x: number; y: number; s: number; vx: number; vy: number }

export interface SceneEngine {
  /** Landing mode: polluted on the left, green on the right. Call resize() after changing it. */
  setSpatial(on: boolean): void;
  resize(): void;
  draw(p: number, time: number): void;
}

export function skyBackground(p: number): { sky: string; hazeOpacity: number } {
  const q = clamp(p * 1.2, 0, 1);
  const sx = 24 + p * 8, sy = 58 - p * 40;
  const sun = lerpRgb(SUN0, SUN1, p);
  const sky =
    `radial-gradient(circle 42vmin at ${sx.toFixed(1)}% ${sy.toFixed(1)}%, ${rgbCss(sun, 0.8)} 0, ${rgbCss(sun, 0.35)} 14%, ${rgbCss(sun, 0)} 100%), ` +
    `linear-gradient(${rgbCss(lerpRgb(SKY_T0, SKY_T1, q))}, ${rgbCss(lerpRgb(SKY_H0, SKY_H1, q))} 78%)`;
  return { sky, hazeOpacity: 1 - clamp(p / 0.7, 0, 1) };
}

export function createScene(fx: HTMLCanvasElement, tree: HTMLCanvasElement, reduce: boolean): SceneEngine {
  const fctx = fx.getContext('2d')!;
  const tctx = tree.getContext('2d')!;
  let FW = 0, FH = 0, TW = 0, TH = 0, dpr = 1, ground = 0, bx = 0;
  let spatial = false;
  let clouds: Cloud[] = [], dust: Dust[] = [], segs: Seg[] = [], leaves: Leaf[] = [], blocks: Block[] = [];

  function initFx() {
    const r = rng(5);
    clouds = []; dust = [];
    for (let i = 0; i < 5; i++) clouds.push({ x0: r() * (FW + 360), y: FH * (0.06 + r() * 0.28), s: 0.7 + r() * 0.8, v: 4 + r() * 6 });
    const N = FW < 700 ? 22 : 46;
    for (let i = 0; i < N; i++) dust.push({ x: r() * FW, y: r() * FH, s: 1 + r() * 1.6, vx: -0.1 + r() * 0.2, vy: 0.05 + r() * 0.15 });
  }

  function buildTree() {
    segs = []; leaves = []; blocks = [];
    const r = rng(11);
    ground = TH - 32;
    bx = TW * (spatial ? 0.8 : 0.58);
    const grow = (x: number, y: number, ang: number, len: number, d: number, t0: number) => {
      const t1 = t0 + (0.2 - d * 0.02);
      const x2 = x + Math.sin(ang) * len, y2 = y - Math.cos(ang) * len;
      segs.push({ x, y, x2, y2, d, t0, t1 });
      if (d >= 4) leaves.push({ x: x2, y: y2, t: t1, s: 2.6 + r() * 3.4, k: r(), rot: r() * 3.14, ci: Math.floor(r() * 4) });
      if (d >= 7) return;
      const n = d < 2 ? 2 : r() < 0.3 ? 3 : 2;
      for (let k = 0; k < n; k++) {
        const spread = (k - (n - 1) / 2) * (0.5 + r() * 0.25) + (r() - 0.5) * 0.2;
        grow(x2, y2, (ang + spread) * 0.92, len * (0.72 + r() * 0.06), d + 1, t1);
      }
    };
    grow(bx, ground, 0, TH * 0.19, 0, 0);
    let m = 0;
    segs.forEach((s) => (m = Math.max(m, s.t1)));
    const kk = 0.8 / m;
    segs.forEach((s) => { s.t0 *= kk; s.t1 *= kk; });
    leaves.forEach((l) => (l.t *= kk));
    let x = TW * 0.03, idx = 0;
    while (x < TW * 0.98) {
      const w = 22 + r() * 26;
      if (Math.abs(x + w / 2 - bx) > 30) {
        blocks.push({ x, w, h: TH * (0.07 + r() * r() * 0.17), th: 0.15 + r() * 0.65, id: idx++, bush: r() });
      }
      x += w + 3 + r() * 6;
    }
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    FW = fx.clientWidth; FH = fx.clientHeight;
    fx.width = Math.round(FW * dpr); fx.height = Math.round(FH * dpr);
    TW = tree.clientWidth; TH = tree.clientHeight;
    tree.width = Math.round(TW * dpr); tree.height = Math.round(TH * dpr);
    initFx(); buildTree();
  }

  const sway = (x: number, y: number, time: number) => {
    const h = (ground - y) / TH;
    return x + (reduce ? 0 : Math.sin(time * 0.0009 + y * 0.008) * h * h * 9);
  };

  /** Horizontal fill that stays `a` on the left, fades to `b`, and is `b` on the right (spatial mode). */
  function hGrad(c: CanvasRenderingContext2D, a: RGB, b: RGB, alpha: number, width: number) {
    const g = c.createLinearGradient(0, 0, width, 0);
    g.addColorStop(0, rgbCss(a, alpha));
    g.addColorStop(0.22, rgbCss(a, alpha));
    g.addColorStop(0.85, rgbCss(b, alpha));
    g.addColorStop(1, rgbCss(b, alpha));
    return g;
  }

  function drawFx(p: number, time: number) {
    const c = fctx;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, FW, FH);
    c.fillStyle = spatial ? hGrad(c, CL0, CL1, 0.75, FW) : rgbCss(lerpRgb(CL0, CL1, p), 0.75);
    clouds.forEach((cl) => {
      const x = ((cl.x0 + time * 0.001 * cl.v) % (FW + 360)) - 180, s = cl.s * 30;
      c.beginPath();
      c.arc(x, cl.y, s * 0.9, 0, TAU); c.arc(x + s * 1.1, cl.y - s * 0.4, s * 1.15, 0, TAU);
      c.arc(x + s * 2.3, cl.y, s * 0.85, 0, TAU); c.arc(x + s * 1.2, cl.y + s * 0.25, s * 1.0, 0, TAU);
      c.fill();
    });
    for (let i = 0; i < 3; i++) {
      c.beginPath(); c.moveTo(0, FH);
      const base = FH * (0.76 + i * 0.065), A = FH * 0.045;
      for (let x = 0; x <= FW + 12; x += 12) {
        c.lineTo(x, base - A * (Math.sin(x * 0.0042 * (1 + i * 0.35) + i * 2 + p * 3) + 0.5 * Math.sin(x * 0.011 + i + p * 5)));
      }
      c.lineTo(FW, FH); c.closePath();
      c.fillStyle = spatial ? hGrad(c, HILL[i][0], HILL[i][1], 0.8, FW) : rgbCss(lerpRgb(HILL[i][0], HILL[i][1], p), 0.8);
      c.fill();
    }
    c.fillStyle = spatial ? hGrad(c, SOIL, GRASS, 1, FW) : rgbCss(lerpRgb(SOIL, GRASS, p), 1);
    c.fillRect(0, FH - 32, FW, 32);
    const da = clamp(1 - p / 0.55, 0, 1);
    if (da > 0.01) {
      c.fillStyle = `rgba(110,98,88,${(da * 0.5).toFixed(3)})`;
      dust.forEach((q) => {
        if (!reduce) { q.x += q.vx; q.y += q.vy; }
        if (q.y > FH - 30) q.y = -4;
        if (q.x > FW + 6) q.x = -6; else if (q.x < -6) q.x = FW + 6;
        if (spatial) c.fillStyle = `rgba(110,98,88,${(da * 0.5 * clamp(1 - (q.x / FW - 0.2) / 0.5, 0, 1)).toFixed(3)})`;
        c.beginPath(); c.arc(q.x, q.y, q.s, 0, TAU); c.fill();
      });
    }
  }

  function drawTree(p: number, time: number) {
    const c = tctx;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, TW, TH);
    const bc = lerpRgb(BLD0, BLD1, p);
    const tp = spatial ? 0.9 : p; // the landing tree is already grown
    blocks.forEach((b) => {
      const lp = spatial ? clamp(((b.x + b.w / 2) / TW - 0.2) / 0.65, 0, 1) : p; // local greenness
      const top = ground - b.h;
      c.fillStyle = rgbCss(spatial ? lerpRgb(BLD0, BLD1, lp) : bc, 1); c.fillRect(b.x, top, b.w, b.h);
      c.fillStyle = 'rgba(255,246,214,0.7)';
      for (let wy = top + 8, row = 0; wy < ground - 8; wy += 12, row++) {
        for (let wx = b.x + 5, col = 0; wx < b.x + b.w - 7; wx += 9, col++) {
          if ((b.id * 7 + row * 13 + col * 5) % 3 === 0) c.fillRect(wx, wy, 4, 5);
        }
      }
      if (lp > b.th) {
        const g = clamp((lp - b.th) / 0.1, 0, 1), cx = b.x + b.w / 2, rs = (5 + b.bush * 4) * g;
        c.fillStyle = GREENS[b.id % 4];
        c.beginPath(); c.arc(cx - rs * 0.8, top, rs, 0, TAU); c.arc(cx + rs * 0.8, top, rs, 0, TAU); c.arc(cx, top - rs * 0.7, rs * 1.05, 0, TAU); c.fill();
      }
    });
    c.lineCap = 'round'; c.lineJoin = 'round';
    segs.forEach((s) => {
      if (tp <= s.t0) return;
      const f = Math.min(1, (tp - s.t0) / (s.t1 - s.t0));
      const ex = s.x + (s.x2 - s.x) * f, ey = s.y + (s.y2 - s.y) * f;
      c.beginPath();
      c.moveTo(sway(s.x, s.y, time), s.y); c.lineTo(sway(ex, ey, time), ey);
      c.lineWidth = Math.max(1, 9 - s.d * 1.1);
      c.strokeStyle = rgbCss(lerpRgb(BARK, TWIG, s.d / 7), 1);
      c.stroke();
    });
    leaves.forEach((l) => {
      if (tp <= l.t) return;
      const a = clamp((tp - l.t) / 0.1, 0, 1);
      c.globalAlpha = a * (0.72 + l.k * 0.28);
      c.fillStyle = GREENS[l.ci];
      c.beginPath(); c.ellipse(sway(l.x, l.y, time), l.y, l.s * 1.5 * (0.4 + 0.6 * a), l.s * 0.9 * (0.4 + 0.6 * a), l.rot, 0, TAU); c.fill();
    });
    c.globalAlpha = 1;
    // ground-level smog that lifts as the city greens
    const smog = clamp(1 - p / 0.6, 0, 1) * 0.5;
    if (smog > 0.01) {
      const g = c.createLinearGradient(0, ground - TH * 0.35, 0, ground + 32);
      g.addColorStop(0, 'rgba(140,118,96,0)');
      g.addColorStop(1, `rgba(140,118,96,${smog.toFixed(3)})`);
      c.fillStyle = g;
      if (spatial) {
        // smog hangs over the left of the skyline and thins out toward the right
        const N = 24, sw = TW / N;
        for (let i = 0; i < N; i++) {
          c.globalAlpha = clamp(1 - ((i + 0.5) / N - 0.2) / 0.5, 0, 1);
          c.fillRect(i * sw, ground - TH * 0.35, sw + 1, TH * 0.35 + 32);
        }
        c.globalAlpha = 1;
      } else {
        c.fillRect(0, ground - TH * 0.35, TW, TH * 0.35 + 32);
      }
    }
  }

  return {
    setSpatial(on) {
      spatial = on;
    },
    resize,
    draw(p, time) {
      if (!FW || !TW) return;
      drawFx(p, time);
      drawTree(p, time);
    },
  };
}
