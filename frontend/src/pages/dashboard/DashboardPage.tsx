import { Component, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent, type ErrorInfo, type PointerEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, GripVertical, LayoutGrid, Plus, RotateCcw, SlidersHorizontal, X } from "lucide-react";
import { Empty, PageHeader } from "../../components/ui";
import { Modal, useConfirm } from "../../components/Modal";
import { useStored } from "../../hooks";
import { motionReduced } from "../../appearance";
import { addWidget, moveWidget, removeWidget, resizeWidget, sanitizeLayout, shiftWidget, SIZE_LABELS, type WidgetPlacement } from "./layout";
import { DEFAULT_LAYOUT, WIDGETS, type WidgetDef } from "./widgets";

const BY_TYPE = new Map(WIDGETS.map((w) => [w.type, w]));

export function Dashboard() {
  const [stored, setStored] = useStored<unknown>("mc-dashboard", DEFAULT_LAYOUT);
  const layout = useMemo(() => sanitizeLayout(stored, WIDGETS) ?? DEFAULT_LAYOUT, [stored]);
  const [editing, setEditing] = useState(false);
  const [catalog, setCatalog] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [justAdded, setJustAdded] = useState<string | null>(null);
  const confirm = useConfirm();
  const grid = useRef<HTMLDivElement>(null);
  const before = useRef<Map<string, DOMRect> | null>(null);
  const lastTarget = useRef<string | null>(null);
  const lastSwap = useRef(0);

  const widgetEls = () => Array.from(grid.current?.querySelectorAll<HTMLElement>("[data-widget]") ?? []);

  /** Apply a layout change; positions are captured first so the move can be animated (FLIP). */
  const update = (next: WidgetPlacement[]) => {
    if (next === layout) return;
    before.current = new Map(widgetEls().map((el) => [el.dataset.widget!, el.getBoundingClientRect()]));
    setStored(next);
  };

  useLayoutEffect(() => {
    const prev = before.current;
    before.current = null;
    if (!prev || motionReduced()) return;
    for (const el of widgetEls()) {
      const p = prev.get(el.dataset.widget!);
      if (!p) continue;
      const r = el.getBoundingClientRect();
      const dx = p.left - r.left;
      const dy = p.top - r.top;
      const sx = r.width ? p.width / r.width : 1;
      const sy = r.height ? p.height / r.height : 1;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < 0.01 && Math.abs(sy - 1) < 0.01) continue;
      el.animate(
        [
          { transformOrigin: "top left", transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` },
          { transformOrigin: "top left", transform: "none" },
        ],
        { duration: 450, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
      );
    }
  }, [layout]);

  useEffect(() => {
    if (!editing) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !catalog && setEditing(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, catalog]);

  useEffect(() => {
    if (!justAdded) return;
    document.querySelector(`[data-widget="${justAdded}"]`)?.scrollIntoView({ behavior: motionReduced() ? "auto" : "smooth", block: "center" });
    const t = window.setTimeout(() => setJustAdded(null), 900);
    return () => window.clearTimeout(t);
  }, [justAdded]);

  const add = (def: WidgetDef) => {
    update(addWidget(layout, def));
    setJustAdded(def.type);
    setCatalog(false);
  };

  const reset = async () => {
    if (await confirm({ title: "Dashboard zurücksetzen?", message: "Alle Widgets, ihre Reihenfolge und Größen werden auf den Standard gesetzt.", confirmLabel: "Zurücksetzen" })) update(DEFAULT_LAYOUT);
  };

  // drag & drop: the dragged widget takes the slot of whatever it is dragged over
  const dragProps = (type: string) =>
    editing
      ? {
          draggable: true,
          onDragStart: (e: DragEvent) => {
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", type);
            lastTarget.current = null;
            setDragging(type);
          },
          onDragOver: (e: DragEvent) => {
            if (!dragging) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            if (type === dragging) {
              lastTarget.current = null;
              return;
            }
            // the swapped widget slides away under the cursor: don't bounce back onto it
            if (type === lastTarget.current || performance.now() - lastSwap.current < 250) return;
            lastTarget.current = type;
            lastSwap.current = performance.now();
            update(moveWidget(layout, dragging, type));
          },
          onDrop: (e: DragEvent) => e.preventDefault(),
          onDragEnd: () => setDragging(null),
        }
      : {};

  // cursor spotlight on card widgets
  const onPointerMove = (e: PointerEvent) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>(".widget-card");
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - r.left}px`);
    el.style.setProperty("--my", `${e.clientY - r.top}px`);
  };

  const unused = WIDGETS.filter((w) => !layout.some((p) => p.type === w.type));

  return (
    <div className="page dash">
      <PageHeader title="Dashboard">
        <button className={`btn ${editing ? "btn-primary" : ""}`} onClick={() => setEditing(!editing)} title={editing ? "Bearbeiten beenden" : "Widgets anordnen, Größe ändern, hinzufügen oder entfernen"}>
          {editing ? <Check size={16} /> : <SlidersHorizontal size={16} />} {editing ? "Fertig" : "Anpassen"}
        </button>
      </PageHeader>

      {layout.length === 0 ? (
        <Empty icon={<LayoutGrid size={36} />} title="Dein Dashboard ist leer">
          <button className="btn btn-primary" onClick={() => setCatalog(true)}>
            <Plus size={16} /> Widgets hinzufügen
          </button>
        </Empty>
      ) : (
        <div ref={grid} className={`widget-grid ${editing ? "editing" : ""}`} onPointerMove={onPointerMove}>
          {layout.map((p, i) => {
            const def = BY_TYPE.get(p.type)!;
            return (
              <section
                key={p.type}
                data-widget={p.type}
                className={`widget w-${p.size} ${def.bare ? "" : "widget-card"} ${dragging === p.type ? "dragging" : ""} ${justAdded === p.type ? "just-added" : ""}`}
                style={{ "--i": i } as CSSProperties}
                aria-label={def.title}
                {...dragProps(p.type)}
              >
                {editing && (
                  <div className="widget-edit" onMouseDown={(e) => e.stopPropagation()}>
                    <span className="widget-edit-grip" title="Ziehen zum Verschieben">
                      <GripVertical size={15} />
                    </span>
                    {def.sizes.length > 1 && (
                      <span className="size-seg" role="group" aria-label="Größe">
                        {def.sizes.map((s) => (
                          <button key={s} className={p.size === s ? "active" : ""} onClick={() => update(resizeWidget(layout, p.type, s))} title={`Größe ${SIZE_LABELS[s]}`} aria-pressed={p.size === s}>
                            {SIZE_LABELS[s]}
                          </button>
                        ))}
                      </span>
                    )}
                    <button className="icon-btn" onClick={() => update(shiftWidget(layout, p.type, -1))} disabled={i === 0} title="Nach vorne" aria-label="Nach vorne">
                      <ChevronLeft size={16} />
                    </button>
                    <button className="icon-btn" onClick={() => update(shiftWidget(layout, p.type, 1))} disabled={i === layout.length - 1} title="Nach hinten" aria-label="Nach hinten">
                      <ChevronRight size={16} />
                    </button>
                    <button className="icon-btn danger" onClick={() => update(removeWidget(layout, p.type))} title="Entfernen" aria-label="Widget entfernen">
                      <X size={16} />
                    </button>
                  </div>
                )}
                {!def.bare && (
                  <header className="widget-head">
                    <span className="widget-icon">
                      <def.icon size={16} />
                    </span>
                    <h3>{def.title}</h3>
                    {def.link && !editing && (
                      <Link to={def.link.to} className="widget-link">
                        {def.link.label} <ChevronRight size={14} />
                      </Link>
                    )}
                  </header>
                )}
                <div className={`widget-content ${def.bare ? "" : "widget-body"}`}>
                  <WidgetBoundary title={def.title}>
                    <def.Component />
                  </WidgetBoundary>
                </div>
              </section>
            );
          })}
        </div>
      )}

      {editing && (
        <div className="dash-editbar">
          <span className="dash-editbar-hint">Widgets ziehen, Größe wählen oder entfernen</span>
          <button className="btn btn-primary" onClick={() => setCatalog(true)} disabled={unused.length === 0}>
            <Plus size={16} /> Widget hinzufügen
          </button>
          <button className="btn" onClick={reset}>
            <RotateCcw size={15} /> Zurücksetzen
          </button>
          <button className="btn" onClick={() => setEditing(false)}>
            <Check size={16} /> Fertig
          </button>
        </div>
      )}

      {catalog && (
        <Modal title="Widget hinzufügen" size="lg" onClose={() => setCatalog(false)}>
          {unused.length === 0 ? (
            <Empty title="Alle Widgets sind schon auf dem Dashboard" />
          ) : (
            <div className="widget-catalog">
              {unused.map((w, i) => (
                <button key={w.type} className="catalog-item" style={{ "--i": i } as CSSProperties} onClick={() => add(w)}>
                  <span className="widget-icon">
                    <w.icon size={18} />
                  </span>
                  <span>
                    <strong>{w.title}</strong>
                    <p>{w.description}</p>
                  </span>
                </button>
              ))}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}

/** Keeps one broken widget from taking the whole dashboard down. */
class WidgetBoundary extends Component<{ title: string; children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Widget „${this.props.title}“ fehlgeschlagen`, error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="alert alert-error">
        <AlertTriangle size={18} />
        <div>
          <strong>{this.props.title} konnte nicht angezeigt werden</strong>
          <div className="small">{this.state.error.message}</div>
        </div>
      </div>
    );
  }
}
