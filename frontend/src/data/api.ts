/**
 * Data access layer — real data from baked artefacts.
 * No mock values. Unavailable data returns explicit unavailable markers.
 */
import * as real from './realApi';

const later = <T,>(v: T, ms = 100): Promise<T> => new Promise((r) => setTimeout(() => r(v), ms));

export const getCityOverview = () => real.getCityOverview();
export const getWards = () => real.getWards();
export const getAirSeries = () => real.getAirSeries();
export const getFloodAreas = () => real.getFloodAreas();
export const getCityBaseline = () => real.getCityBaseline();
