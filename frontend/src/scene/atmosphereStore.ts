import { useEffect, useSyncExternalStore } from 'react';
import { clamp } from '../lib/math';

/**
 * Tiny external store that pages use to say how green the background should be.
 * Pages set the target; the Atmosphere component eases toward it.
 * Pages must never raise the target above 0 unless an optimization has succeeded.
 */
let target = 0;
let wide = false;
let spatial = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const atmosphere = {
  getTarget: () => target,
  setTarget(p: number) {
    target = clamp(p, 0, 1);
  },
  getWide: () => wide,
  setWide(w: boolean) {
    if (w !== wide) {
      wide = w;
      emit();
    }
  },
  getSpatial: () => spatial,
  /** Landing-only: greenness varies left to right instead of with a single value. */
  setSpatial(s: boolean) {
    if (s !== spatial) {
      spatial = s;
      emit();
    }
  },
  subscribe(l: () => void) {
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  },
};

export function useAtmosphereWide(): boolean {
  return useSyncExternalStore(atmosphere.subscribe, atmosphere.getWide);
}

export function useAtmosphereSpatial(): boolean {
  return useSyncExternalStore(atmosphere.subscribe, atmosphere.getSpatial);
}

/** Set a fixed greenness for the current page. */
export function useAtmosphere(p: number, wideScene = false, spatialScene = false) {
  useEffect(() => {
    atmosphere.setTarget(p);
    atmosphere.setWide(wideScene);
    atmosphere.setSpatial(spatialScene);
    return () => {
      if (spatialScene) atmosphere.setSpatial(false);
    };
  }, [p, wideScene, spatialScene]);
}
