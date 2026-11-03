import { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Popup } from 'react-leaflet';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import 'leaflet/dist/leaflet.css';

interface WardScore {
  impact: number | null;
  risk_band: string;
  evidence_status: string;
  green_verified: boolean;
}

interface Props {
  scores: Record<string, WardScore>;
  onSelect: (ward: number) => void;
  selected: number | null;
}

function impactColor(impact: number | null, verified: boolean): string {
  if (impact === null) return '#c9b9a3';
  if (!verified) return '#c9b9a3';
  if (impact < 30) return '#2e7d4f';
  if (impact < 60) return '#7d5400';
  return '#a8371f';
}

export default function EngineMap({ scores, onSelect, selected }: Props) {
  const [geojson, setGeojson] = useState<FeatureCollection | null>(null);

  useEffect(() => {
    fetch('/wards.geojson')
      .then((r) => r.json())
      .then((g) => setGeojson(g))
      .catch(() => setGeojson(null));
  }, []);

  const center: [number, number] = [18.52, 73.85];

  const styleFeature = useMemo(() => {
    return (feature: Feature<Geometry, any> | undefined) => {
      if (!feature) return {};
      const ward = feature.properties?.ward_no;
      const s = ward ? scores[String(ward)] : null;
      const color = s ? impactColor(s.impact, s.green_verified) : '#c9b9a3';
      return {
        fillColor: color,
        weight: selected === ward ? 3 : 1,
        opacity: 1,
        color: selected === ward ? '#1b2a26' : '#4a5a55',
        fillOpacity: 0.7,
      };
    };
  }, [scores, selected]);

  const onEachFeature = (feature: Feature<Geometry, { ward_no: number }>, layer: any) => {
    const ward = feature.properties?.ward_no;
    const s = ward ? scores[String(ward)] : null;
    if (s) {
      layer.bindPopup(
        `<b>Ward ${ward}</b><br/>Impact: ${s.impact ?? '—'}<br/>Risk: ${s.risk_band}<br/>Evidence: ${s.evidence_status}<br/>${s.green_verified ? 'Complete (4/4)' : 'Partial (3/4 — green unavailable)'}`,
      );
    }
    layer.on('click', () => {
      if (ward) onSelect(ward);
    });
  };

  if (!geojson) {
    return (
      <div style={{ height: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4a5a55' }}>
        Loading map...
      </div>
    );
  }

  return (
    <MapContainer center={center} zoom={11} style={{ height: '480px', width: '100%', borderRadius: '10px' }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <GeoJSON data={geojson} style={styleFeature} onEachFeature={onEachFeature} />
    </MapContainer>
  );
}
