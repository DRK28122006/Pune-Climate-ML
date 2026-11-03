import type { ReactNode } from 'react';

interface Base {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  unit?: string;
}

function Shell({ id, label, hint, error, unit, children }: Base & { children: ReactNode }) {
  return (
    <div className={`field${error ? ' field--error' : ''}`}>
      <label htmlFor={`f-${id}`}>{label}</label>
      <div className="field__control">
        {children}
        {unit && <span className="field__unit">{unit}</span>}
      </div>
      {hint && !error && (
        <p className="field__hint" id={`h-${id}`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field__error" id={`e-${id}`} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

const describe = (p: Base) => (p.error ? `e-${p.id}` : p.hint ? `h-${p.id}` : undefined);

export function TextField(p: Base & { value: string; onChange: (v: string) => void; maxLength?: number }) {
  return (
    <Shell {...p}>
      <input
        id={`f-${p.id}`}
        type="text"
        value={p.value}
        maxLength={p.maxLength}
        aria-invalid={!!p.error}
        aria-describedby={describe(p)}
        onChange={(e) => p.onChange(e.target.value)}
      />
    </Shell>
  );
}

export function NumberField(
  p: Base & { value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number },
) {
  return (
    <Shell {...p}>
      <input
        id={`f-${p.id}`}
        type="number"
        inputMode="decimal"
        value={Number.isNaN(p.value) ? '' : p.value}
        min={p.min}
        max={p.max}
        step={p.step ?? 1}
        aria-invalid={!!p.error}
        aria-describedby={describe(p)}
        onChange={(e) => p.onChange(e.target.value === '' ? NaN : Number(e.target.value))}
      />
    </Shell>
  );
}

export function SelectField(
  p: Base & { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] },
) {
  return (
    <Shell {...p}>
      <select
        id={`f-${p.id}`}
        value={p.value}
        aria-invalid={!!p.error}
        aria-describedby={describe(p)}
        onChange={(e) => p.onChange(e.target.value)}
      >
        {p.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Shell>
  );
}

export function RangeField({
  id,
  label,
  value,
  min,
  max,
  unit = '%',
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  unit?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="range">
      <label htmlFor={`f-${id}`}>
        {label}
        <output htmlFor={`f-${id}`}>
          {value}
          {unit}
        </output>
      </label>
      <input
        id={`f-${id}`}
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
