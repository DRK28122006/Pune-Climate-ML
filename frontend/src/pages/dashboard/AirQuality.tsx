import DataGate from '../../components/DataGate';
import { DemoBadge, PageHeader } from '../../components/ui';
import { getAirSeries } from '../../data/api';
import { useAsync } from '../../lib/useAsync';

export default function AirQuality() {
  const state = useAsync(getAirSeries);

  return (
    <>
      <PageHeader
        eyebrow="Air quality"
        title="Air Quality"
        badge={<DemoBadge />}
      />
      <DataGate state={state}>
        {(d) => {
          if (d.unavailable) {
            return (
              <div className="state state--empty" style={{ padding: '32px', textAlign: 'center' }}>
                <p style={{ fontSize: '16px', fontWeight: 600, color: '#1b2a26', marginBottom: '8px' }}>Air quality data is not available</p>
                <p style={{ color: '#4a5a55', maxWidth: '600px', margin: '0 auto' }}>
                  {d.reason}
                </p>
              </div>
            );
          }
          return (
            <div className="state state--empty" style={{ padding: '32px', textAlign: 'center' }}>
              <p style={{ fontSize: '16px', fontWeight: 600, color: '#1b2a26', marginBottom: '8px' }}>Unexpected data format</p>
            </div>
          );
        }}
      </DataGate>
    </>
  );
}
