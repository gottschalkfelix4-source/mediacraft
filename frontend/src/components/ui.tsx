import { useEffect, useRef, useState, type ReactNode, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { Loader2, AlertTriangle, Inbox } from "lucide-react";
import { errorMessage } from "../api";
import { motionReduced } from "../appearance";

export function Spinner({ size = 18, label }: { size?: number; label?: string }) {
  return (
    <span className="spinner-wrap" role="status">
      <Loader2 size={size} className="spin" />
      {label && <span>{label}</span>}
    </span>
  );
}

export function Loading({ label = "Lade…" }: { label?: string }) {
  return (
    <div className="loading-block">
      <Spinner size={22} label={label} />
    </div>
  );
}

export function ErrorBox({ error, title = "Fehler beim Laden" }: { error: unknown; title?: string }) {
  return (
    <div className="alert alert-error">
      <AlertTriangle size={18} />
      <div>
        <strong>{title}</strong>
        <div>{errorMessage(error)}</div>
      </div>
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon ?? <Inbox size={36} />}</div>
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, children, sub }: { title: ReactNode; children?: ReactNode; sub?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {sub && <div className="page-sub">{sub}</div>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="toolbar">{children}</div>;
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className ?? ""}`}>
      {(title || actions) && (
        <div className="card-header">
          {title && <h3>{title}</h3>}
          {actions && <div className="card-actions">{actions}</div>}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Badge({ children, tone = "default", title }: { children: ReactNode; tone?: "default" | "accent" | "success" | "warning" | "danger" | "info" | "muted"; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function Progress({ value, tone, title, small, marker }: { value: number; tone?: string; title?: string; small?: boolean; marker?: number | null }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const t = tone ?? (v >= 100 ? "success" : "accent");
  return (
    <div className={`progress ${small ? "progress-sm" : ""}`} title={title} role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`progress-bar tone-${t}`} style={{ width: `${v}%` }} />
      {marker !== null && marker !== undefined && marker > 0 && marker < 100 && <div className="progress-marker" style={{ left: `${marker}%` }} />}
    </div>
  );
}

export function Toggle({ checked, onChange, label, title, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; title?: string; disabled?: boolean }) {
  return (
    <label className={`toggle ${disabled ? "disabled" : ""}`} title={title}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track">
        <span className="toggle-thumb" />
      </span>
      {label && <span className="toggle-label">{label}</span>}
    </label>
  );
}

export function Field({ label, help, children, inline }: { label: ReactNode; help?: ReactNode; children: ReactNode; inline?: boolean }) {
  return (
    <div className={`field ${inline ? "field-inline" : ""}`}>
      <label className="field-label">{label}</label>
      <div className="field-control">
        {children}
        {help && <div className="field-help">{help}</div>}
      </div>
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement> & { onValue?: (v: string) => void }) {
  const { onValue, onChange, className, ...rest } = props;
  return (
    <input
      type="text"
      {...rest}
      className={`input ${className ?? ""}`}
      onChange={(e) => {
        onChange?.(e);
        onValue?.(e.target.value);
      }}
    />
  );
}

export function NumberInput({ value, onValue, min, max, step, className, placeholder, disabled }: {
  value: number | null | undefined;
  onValue: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <input
      type="number"
      className={`input input-num ${className ?? ""}`}
      value={value ?? ""}
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => onValue(e.target.value === "" ? 0 : Number(e.target.value))}
    />
  );
}

export function Select<V extends string | number>(
  props: Omit<SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange"> & {
    value: V;
    onValue: (v: V) => void;
    options: { value: V; label: string; disabled?: boolean }[];
  },
) {
  const { value, onValue, options, className, ...rest } = props;
  const isNum = typeof value === "number";
  return (
    <select
      {...rest}
      className={`input select ${className ?? ""}`}
      value={String(value)}
      onChange={(e) => onValue((isNum ? Number(e.target.value) : e.target.value) as V)}
    >
      {options.map((o) => (
        <option key={String(o.value)} value={String(o.value)} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Tabs<K extends string>({ tabs, active, onChange }: { tabs: { key: K; label: ReactNode; count?: number }[]; active: K; onChange: (k: K) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={active === t.key}
          className={`tab ${active === t.key ? "active" : ""}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
          {t.count !== undefined && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Editable list of free-text chips (e.g. required terms). */
export function ChipInput({ values, onChange, placeholder, suggestions, numeric }: {
  values: (string | number)[];
  onChange: (v: (string | number)[]) => void;
  placeholder?: string;
  suggestions?: (string | number)[];
  numeric?: boolean;
}) {
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const parts = raw.split(/[,;]/).map((s) => s.trim()).filter(Boolean);
    if (!parts.length) return;
    const vals = parts.map((p) => (numeric ? Number(p) : p)).filter((p) => !(numeric && isNaN(p as number)));
    const next = [...values];
    for (const v of vals) if (!next.includes(v)) next.push(v);
    onChange(next);
    setText("");
  };
  const rest = (suggestions ?? []).filter((s) => !values.includes(s));
  return (
    <div className="chip-input">
      <div className="chips">
        {values.map((v) => (
          <span className="chip chip-active" key={String(v)}>
            {v}
            <button type="button" className="chip-x" title="Entfernen" aria-label={`${v} entfernen`} onClick={() => onChange(values.filter((x) => x !== v))}>
              ×
            </button>
          </span>
        ))}
        <input
          className="chip-text"
          value={text}
          placeholder={placeholder ?? "Hinzufügen + Enter"}
          inputMode={numeric ? "numeric" : undefined}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add(text);
            } else if (e.key === "Backspace" && !text && values.length) {
              onChange(values.slice(0, -1));
            }
          }}
          onBlur={() => text && add(text)}
        />
      </div>
      {rest.length > 0 && (
        <div className="chips chip-suggestions">
          {rest.map((s) => (
            <button type="button" key={String(s)} className="chip" onClick={() => onChange([...values, s])} title="Hinzufügen">
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function KV({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v], i) => (
        <div className="kv-row" key={i}>
          <dt>{k}</dt>
          <dd>{v ?? "–"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Pager({ page, pages, onPage }: { page: number; pages: number; onPage: (p: number) => void }) {
  if (pages <= 1) return null;
  return (
    <div className="pager">
      <button className="btn btn-sm" disabled={page <= 1} onClick={() => onPage(1)} title="Erste Seite">
        «
      </button>
      <button className="btn btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)} title="Vorherige Seite">
        ‹
      </button>
      <span className="pager-info">
        Seite {page} von {pages}
      </span>
      <button className="btn btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)} title="Nächste Seite">
        ›
      </button>
      <button className="btn btn-sm" disabled={page >= pages} onClick={() => onPage(pages)} title="Letzte Seite">
        »
      </button>
    </div>
  );
}

/** Shimmering placeholder lines while a widget loads. */
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Lade…">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton-line" />
      ))}
    </div>
  );
}

/** Number that counts up (from 0, later from its previous value) to `value`. */
export function CountUp({ value, format = (n) => String(Math.round(n)), duration = 900 }: { value: number; format?: (n: number) => string; duration?: number }) {
  const [shown, setShown] = useState(() => (motionReduced() ? value : 0));
  const from = useRef(shown);

  useEffect(() => {
    if (motionReduced()) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      const v = a + (value - a) * (1 - Math.pow(1 - p, 3));
      from.current = v;
      setShown(v);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return <span className="count-up">{format(shown)}</span>;
}
