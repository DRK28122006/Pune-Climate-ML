import { useState } from 'react';
import DataGate from '../../components/DataGate';
import { BarRow, Ring } from '../../components/charts/Visuals';
import { DemoBadge, MetricCard, PageHeader, Panel, Segmented } from '../../components/ui';
import { getWards } from '../../data/api';
import { getCityOverview } from '../../data/api';
import { CANOPY_TARGET_PCT } from '../../config';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';

export default function GreenCover() {
  const state = useAsync(getWards);
  const cityState = useAsync(getCityOverview);
  const { result } = usePlan();
  const [view, setView] = useState<'now' | 'plan'>('now');
  const [target, setTarget] = useState(CANOPY_TARGET_PCT);
  const effective = result ? view : 'now';

  return (
    <>
      <PageHeader
        eyebrow="Green cover"
        title="Green Cover"
        lede="Tree canopy as a share of ward area, and how many points each ward is from the target."
        badge={<DemoBadge />}
      />
      <DataGate state={state}>
        {(wards) => {
          const rows = wards
            .map((w) => {
              const planned = result && effective === 'plan' && result.inputs.focusArea === w.name ? result.after.canopyPct : w.canopyPct;
              return { ...w, shown: planned, changed: planned !== w.canopyPct };
            })
            .sort((a, b) => a.shown - b.shown);
          const cityNow = cityState.data?.canopyPct ?? 0;
          const belowTarget = rows.filter((r) => r.shown < target).length;
          return (
            <>
              <div className="toolbar">
                <Segmented<'now' | 'plan'>
                  label="Canopy view"
                  value={effective}
                  onChange={setView}
                  options={[{ value: 'now', label: 'Current' }, { value: 'plan', label: 'With my plan', disabled: !result }]}
                />
                <div className="range range--inline">
                  <label htmlFor="f-target">
                    Canopy target <output htmlFor="f-target">{target}%</output>
                  </label>
                  <input id="f-target" type="range" min={20} max={45} value={target} onChange={(e) => setTarget(Number(e.target.value))} />
                </div>
              </div>
              {!result && <p className="note">“With my plan” unlocks after you evaluate and optimize a plan.</p>}

              <div className="metrics">
                <MetricCard label="City canopy" value={cityNow.toFixed(1)} unit="%" note="City average, sample" pill={{ tone: cityNow < target ? 'med' : 'low', text: cityNow < target ? `${(target - cityNow).toFixed(1)} points below target` : 'At or above target' }} />
                <MetricCard label="Wards below target" value={String(belowTarget)} unit={`of ${rows.length}`} note="Sample wards listed here" />
                {result && effective === 'plan' && (
                  <MetricCard label={`${result.inputs.focusArea} with plan`} value={result.after.canopyPct.toFixed(1)} unit="%" delta={{ text: `+${(result.after.canopyPct - result.before.canopyPct).toFixed(1)} pts (demo)`, good: true }} note={`By year ${result.inputs.horizonYears}`} />
                )}
              </div>

              <Panel title="Canopy against target" note="Sample data. The vertical mark on each bar is the target.">
                <div className="greenwrap">
                  <Ring value={cityNow} target={target} caption={`of ${target}% target`} />
                  <div className="bars">
                    {rows.map((w) => (
                      <BarRow
                        key={w.id}
                        label={w.name}
                        value={w.shown}
                        max={target}
                        marker={target}
                        display={`${w.shown.toFixed(w.changed ? 1 : 0)}%`}
                        right={w.shown >= target ? 'On target' : `+${(target - w.shown).toFixed(w.changed ? 1 : 0)} pts`}
                        color={w.changed ? 'var(--leaf-deep)' : 'var(--leaf)'}
                      />
                    ))}
                  </div>
                </div>
                {effective === 'plan' && <p className="note">Dark bar: ward changed by your demonstration plan.</p>}
              </Panel>

              <Panel title="Satellite before and after">
                <p className="note">Not available in this prototype. A comparison of imagery tiles can be added here once a tile source is connected.</p>
              </Panel>
            </>
          );
        }}
      </DataGate>
    </>
  );
}
