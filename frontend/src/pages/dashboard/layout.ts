// Dashboard layout model: which widgets are shown, in which order and how wide.
// Pure functions only, so they are easy to test (layout.test.ts).

export type WidgetSize = "s" | "m" | "l" | "xl" | "full";

export const SIZE_LABELS: Record<WidgetSize, string> = { s: "S", m: "M", l: "L", xl: "XL", full: "Voll" };
export const SIZE_ORDER: WidgetSize[] = ["s", "m", "l", "xl", "full"];

export interface WidgetPlacement {
  type: string;
  size: WidgetSize;
}

export interface WidgetMeta {
  type: string;
  sizes: WidgetSize[];
  defaultSize: WidgetSize;
}

/** Drop unknown/duplicate widgets and sizes a widget does not support. */
export function sanitizeLayout(raw: unknown, metas: WidgetMeta[]): WidgetPlacement[] | null {
  if (!Array.isArray(raw)) return null;
  const byType = new Map(metas.map((m) => [m.type, m]));
  const seen = new Set<string>();
  const out: WidgetPlacement[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const { type, size } = item as Partial<WidgetPlacement>;
    const meta = typeof type === "string" ? byType.get(type) : undefined;
    if (!meta || seen.has(meta.type)) continue;
    seen.add(meta.type);
    out.push({ type: meta.type, size: size && meta.sizes.includes(size) ? size : meta.defaultSize });
  }
  return out;
}

/** Move the widget `type` to the position currently held by `target`. */
export function moveWidget(layout: WidgetPlacement[], type: string, target: string): WidgetPlacement[] {
  const from = layout.findIndex((w) => w.type === type);
  const to = layout.findIndex((w) => w.type === target);
  if (from < 0 || to < 0 || from === to) return layout;
  const next = layout.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** Move a widget one step forward (-1) or backward (+1). */
export function shiftWidget(layout: WidgetPlacement[], type: string, delta: -1 | 1): WidgetPlacement[] {
  const i = layout.findIndex((w) => w.type === type);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= layout.length) return layout;
  return moveWidget(layout, type, layout[j].type);
}

export function resizeWidget(layout: WidgetPlacement[], type: string, size: WidgetSize): WidgetPlacement[] {
  return layout.map((w) => (w.type === type ? { ...w, size } : w));
}

export function removeWidget(layout: WidgetPlacement[], type: string): WidgetPlacement[] {
  return layout.filter((w) => w.type !== type);
}

export function addWidget(layout: WidgetPlacement[], meta: WidgetMeta): WidgetPlacement[] {
  if (layout.some((w) => w.type === meta.type)) return layout;
  return [...layout, { type: meta.type, size: meta.defaultSize }];
}

/** Time-of-day greeting for the welcome widget. */
export function greeting(d: Date): string {
  const h = d.getHours();
  if (h < 5) return "Gute Nacht";
  if (h < 11) return "Guten Morgen";
  if (h < 18) return "Guten Tag";
  return "Guten Abend";
}
