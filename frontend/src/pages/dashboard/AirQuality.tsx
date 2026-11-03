import { useState } from 'react';
import DataGate from '../../components/DataGate';
import LineChart, { type Band } from '../../components/charts/LineChart';
import { DemoBadge, MetricCard, PageHeader, Panel, Pill, Segmented } from '../../components/ui';
import { getAirSeries } from '../../data/api';
import { AQI_BANDS } from '../../data/sample';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';

type Range = 'hourly' | 'daily';
const BAND_FILL = ['rgba(35,112,74,0.12)', 'rgba(35,112,74,0.05)', 'rgba(138,93,0,0.10)', 'rgba(184,64,42,0.10)'];
const bands: Band[] = AQI_BANDS.map((b, i) => ({ from: b.from, to: b.to, label: b.label, fill: BAND_FILL[i] }));
const bandFor = (v: number) => AQI_BANDS.find((b) => v <= b.to) ?? AQI_BANDS[AQI_BANDS.length - 1];

export default function AirQuality() {
  const state = useAsync(getAirSeries);
  const [range, setRange] = useState<Range>('hourly');
  const [sortStations, setSortStations] = useState<'worst' | 'name'>('worst');
  const { result } = usePlan();

  return (
    <>
      <PageHeader
        eyebrow="Air quality"
        title="Air Quality"
        lede="City air index over the last 24 hours or the last week, with category bands shaded, plus station readings."
        badge={<DemoBadge />}
      />
      <DataGate state={state}>
        {(d) => {
          const series = range === 'hourly' ? d.hourly : d.daily;
          const labels = range === 'hourly' ? d.hourly.map((_, i) => `${String(i).padStart(2, '0')}:00`) : ['6d ago', '5d', '4d', '3d', '2d', 'Yday', 'Today'];
          const peak = Math.max(...series);
          const peakAt = labels[series.indexOf(peak)];
          const avg = series.reduce((a, b) => a + b, 0) / series.length;
          const stations = [...d.stations].sort((a, b) => (sortStations === 'worst' ? b.index - a.index : a.name.localeCompare(b.name)));
          return (
            <>
              <div className="metrics">
                <MetricCard label={range === 'hourly' ? 'Latest hour' : 'Today'} value={String(series[series.length - 1])} unit="AQI" pill={{ tone: bandFor(series[series.length - 1]).tone, text: bandFor(series[series.length - 1]).label }} />
                <MetricCard label="Average" value={avg.toFixed(0)} unit="AQI" pill={{ tone: bandFor(avg).tone, text: bandFor(avg).label }} note={range === 'hourly' ? 'Over 24 hours' : 'Over 7 days'} />
                <MetricCard label="Peak" value={String(peak)} unit="AQI" pill={{ tone: bandFor(peak).tone, text: bandFor(peak).label }} note={`At ${peakAt}`} />
              </div>

              <Panel
                title="City air index"
                actions={<Segmented<Range> label="Time range" value={range} onChange={setRange} options={[{ value: 'hourly', label: 'Last 24 hours' }, { value: 'daily', label: 'Last 7 days' }]} />}
                note="Sample data in a CPCB-style category scale. Not a live reading."
              >
                <LineChart
                  values={series}
                  xLabels={labels}
                  labelEvery={range === 'hourly' ? 4 : 1}
                  yMax={300}
                  yTicks={[0, 50, 100, 150, 200, 250, 300]}
                  yLabel="Air quality index"
                  xLabel={range === 'hourly' ? 'Hour of day' : 'Day'}
                  bands={bands}
                  ariaLabel={`Air index over ${range === 'hourly' ? '24 hours' : '7 days'}. Peak ${peak} at ${peakAt}.`}
                />
              </Panel>

              <div className="two-col">
                <Panel
                  title="Monitoring stations"
                  actions={<Segmented<'worst' | 'name'> label="Sort stations" value={sortStations} onChange={setSortStations} options={[{ value: 'worst', label: 'Worst first' }, { value: 'name', label: 'A to Z' }]} />}
                  note="Sample data."
                >
                  <ul className="stations">
                    {stations.map((s) => (
                      <li key={s.name}>
                        <span>{s.name}</span>
                        <b>{s.index}</b>
                        <Pill tone={bandFor(s.index).tone}>{bandFor(s.index).label}</Pill>
                      </li>
                    ))}
                  </ul>
                </Panel>

                <Panel title="Effect of your plan (demo)">
                  {result ? (
                    <div>
                      <p>
                        For <b>{result.inputs.planName}</b>, the demo model moves the plan area's air index from{' '}
                        <b>{result.before.airIndex.toFixed(0)}</b> to <b>{result.after.airIndex.toFixed(0)}</b>.
                      </p>
                      <p className="note">Simulated for the plan area only and unrelated to the station readings shown here.</p>
                    </div>
                  ) : (
                    <p className="note">Evaluate a plan to see its modelled effect on the air index here.</p>
                  )}
                </Panel>
              </div>
            </>
          );
        }}
      </DataGate>
    </>
  );
}
