import { useEffect } from "react";
import { useStored } from "./hooks";

export type Theme = "dark" | "light";
export type Accent = "teal" | "violet" | "blue" | "rose" | "amber" | "emerald";

// [main colour, gradient partner] – must match the data-accent palettes in styles.css
export const ACCENTS: { id: Accent; label: string; colors: [string, string] }[] = [
  { id: "teal", label: "Türkis", colors: ["#14b8a6", "#6366f1"] },
  { id: "violet", label: "Violett", colors: ["#8b5cf6", "#ec4899"] },
  { id: "blue", label: "Blau", colors: ["#3b82f6", "#06b6d4"] },
  { id: "rose", label: "Rosé", colors: ["#f43f5e", "#f59e0b"] },
  { id: "amber", label: "Bernstein", colors: ["#f59e0b", "#ef4444"] },
  { id: "emerald", label: "Smaragd", colors: ["#10b981", "#84cc16"] },
];

export interface Appearance {
  theme: Theme;
  setTheme: (t: Theme) => void;
  accent: Accent;
  setAccent: (a: Accent) => void;
  /** glass blur and the aurora backdrop */
  effects: boolean;
  setEffects: (v: boolean) => void;
  motion: boolean;
  setMotion: (v: boolean) => void;
}

/** User-selectable look, persisted per browser and mirrored onto <html data-*>. */
export function useAppearance(): Appearance {
  const [theme, setTheme] = useStored<Theme>("mc-theme", "dark");
  const [accent, setAccent] = useStored<Accent>("mc-accent", "teal");
  const [effects, setEffects] = useStored("mc-effects", true);
  const [motion, setMotion] = useStored("mc-motion", true);

  useEffect(() => {
    const d = document.documentElement.dataset;
    d.theme = theme;
    d.accent = accent;
    d.fx = effects ? "on" : "off";
    d.motion = motion ? "on" : "off";
  }, [theme, accent, effects, motion]);

  return { theme, setTheme, accent, setAccent, effects, setEffects, motion, setMotion };
}

/** True when animations should be skipped (system setting or user choice). */
export function motionReduced(): boolean {
  return document.documentElement.dataset.motion === "off" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}
