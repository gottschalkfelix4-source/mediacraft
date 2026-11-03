import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Check, Moon, Palette, Sun } from "lucide-react";
import { ACCENTS, type Appearance } from "../appearance";
import { Toggle } from "./ui";

/** Topbar button with a popover for theme, accent colour, effects and animations. */
export function AppearanceMenu({ appearance: a }: { appearance: Appearance }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="popover-anchor" ref={ref}>
      <button className="icon-btn" onClick={() => setOpen(!open)} title="Erscheinungsbild" aria-label="Erscheinungsbild" aria-expanded={open}>
        <Palette size={18} />
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Erscheinungsbild">
          <div>
            <h4>Design</h4>
            <div className="theme-seg">
              <button className={a.theme === "dark" ? "active" : ""} onClick={() => a.setTheme("dark")}>
                <Moon size={15} /> Dunkel
              </button>
              <button className={a.theme === "light" ? "active" : ""} onClick={() => a.setTheme("light")}>
                <Sun size={15} /> Hell
              </button>
            </div>
          </div>
          <div>
            <h4>Akzentfarbe</h4>
            <div className="swatches">
              {ACCENTS.map((x) => (
                <button
                  key={x.id}
                  className={`swatch ${a.accent === x.id ? "active" : ""}`}
                  style={{ "--sw-a": x.colors[0], "--sw-b": x.colors[1] } as CSSProperties}
                  onClick={() => a.setAccent(x.id)}
                  title={x.label}
                  aria-label={`Akzentfarbe ${x.label}`}
                  aria-pressed={a.accent === x.id}
                >
                  {a.accent === x.id && <Check size={14} strokeWidth={3} />}
                </button>
              ))}
            </div>
          </div>
          <div className="col gap-sm">
            <h4>Effekte</h4>
            <Toggle checked={a.effects} onChange={a.setEffects} label="Glas & Hintergrund-Leuchten" />
            <Toggle checked={a.motion} onChange={a.setMotion} label="Animationen" />
          </div>
        </div>
      )}
    </div>
  );
}
