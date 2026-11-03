import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { AlertTriangle, Inbox, Loader2, FlaskConical } from 'lucide-react';
import { DEMO_NOTICE } from '../config';
import type { Priority } from '../types';

/* ---------- Button ---------- */
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'md' | 'lg';
  busy?: boolean;
}
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', busy, className = '', children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={`btn btn--${variant} btn--${size} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy && <Loader2 className="spin" size={18} aria-hidden="true" />}
      {children}
    </button>
  );
});

/* ---------- Pill ---------- */
const PILL_TEXT: Record<Priority, string> = { high: 'High', med: 'Medium', low: 'Low' };
export function Pill({ tone, children }: { tone: Priority; children?: ReactNode }) {
  return <span className={`pill pill--${tone}`}>{children ?? PILL_TEXT[tone]}</span>;
}

/* ---------- Demo badge ---------- */
export function DemoBadge({ label = 'Sample data', title = DEMO_NOTICE }: { label?: string; title?: string }) {
  return (
    <span className="demo-badge" title={title}>
      <FlaskConical size={14} aria-hidden="true" />
      {label}
    </span>
  );
}

/* ---------- Panel ---------- */
export function Panel({
  title,
  actions,
  children,
  className = '',
  note,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  note?: ReactNode;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel__head">
          {title && <h3>{title}</h3>}
          {actions && <div className="panel__actions">{actions}</div>}
        </header>
      )}
      {children}
      {note && <p className="note panel__note">{note}</p>}
    </section>
  );
}

/* ---------- Page header ---------- */
export function PageHeader({
  eyebrow,
  title,
  lede,
  badge,
}: {
  eyebrow?: string;
  title: string;
  lede?: string;
  badge?: ReactNode;
}) {
  return (
    <header className="page-head">
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <div className="page-head__row">
        <h1>{title}</h1>
        {badge}
      </div>
      {lede && <p className="lede">{lede}</p>}
    </header>
  );
}

/* ---------- Metric card ---------- */
export function MetricCard({
  label,
  value,
  unit,
  note,
  pill,
  delta,
}: {
  label: string;
  value: string;
  unit?: string;
  note?: string;
  pill?: { tone: Priority; text: string };
  delta?: { text: string; good: boolean };
}) {
  return (
    <div className="metric">
      <span className="metric__label">{label}</span>
      <div className="metric__value">
        {value}
        {unit && <small>{unit}</small>}
      </div>
      {pill && <Pill tone={pill.tone}>{pill.text}</Pill>}
      {delta && <span className={`delta ${delta.good ? 'delta--good' : 'delta--bad'}`}>{delta.text}</span>}
      {note && <p className="metric__note">{note}</p>}
    </div>
  );
}

/* ---------- Segmented control ---------- */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string; disabled?: boolean }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={`seg__btn${o.value === value ? ' is-on' : ''}`}
          aria-pressed={o.value === value}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- States ---------- */
export function LoadingState({ label = 'Loading sample data' }: { label?: string }) {
  return (
    <div className="state" role="status">
      <Loader2 className="spin" size={22} aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state state--error" role="alert">
      <AlertTriangle size={22} aria-hidden="true" />
      <div>
        <strong>Something went wrong</strong>
        <p>{message}</p>
      </div>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function EmptyState({ title, text, action }: { title: string; text: string; action?: ReactNode }) {
  return (
    <div className="state state--empty">
      <Inbox size={24} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
      {action}
    </div>
  );
}

/* ---------- Section transition: a divider band used between result sections ---------- */
export function SectionBand({ children }: { children: ReactNode }) {
  return <div className="band">{children}</div>;
}
