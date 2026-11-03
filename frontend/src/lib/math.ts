export type RGB = [number, number, number];

export const clamp = (v: number, a: number, b: number): number => Math.min(b, Math.max(a, v));

export const hexToRgb = (c: string): RGB => [
  parseInt(c.slice(1, 3), 16),
  parseInt(c.slice(3, 5), 16),
  parseInt(c.slice(5, 7), 16),
];

export const lerpRgb = (a: RGB, b: RGB, k: number): RGB => [
  a[0] + (b[0] - a[0]) * k,
  a[1] + (b[1] - a[1]) * k,
  a[2] + (b[2] - a[2]) * k,
];

export const rgbCss = (a: RGB, alpha = 1): string =>
  `rgba(${Math.round(a[0])},${Math.round(a[1])},${Math.round(a[2])},${alpha})`;

/** Small deterministic PRNG so the scene looks identical on every load. */
export function rng(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const fmt = (v: number, digits = 1): string => v.toFixed(digits);
