import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../api";
import { useTags } from "../hooks";
import { useToast } from "./Toast";

/** Multi-select for tags; typing a new label + Enter creates the tag. */
export function TagSelect({ value, onChange }: { value: number[]; onChange: (v: number[]) => void }) {
  const { data: tags = [] } = useTags();
  const [text, setText] = useState("");
  const qc = useQueryClient();
  const toast = useToast();

  const create = async () => {
    const label = text.trim().toLowerCase();
    if (!label) return;
    const existing = tags.find((t) => t.label === label);
    if (existing) {
      if (!value.includes(existing.id)) onChange([...value, existing.id]);
      setText("");
      return;
    }
    try {
      const t = await api.createTag(label);
      qc.invalidateQueries({ queryKey: ["tags"] });
      onChange([...value, t.id]);
      setText("");
    } catch (e) {
      toast.error("Tag konnte nicht angelegt werden", errorMessage(e));
    }
  };

  const available = tags.filter((t) => !value.includes(t.id));
  return (
    <div className="chip-input">
      <div className="chips">
        {value.map((id) => (
          <span key={id} className="chip chip-active">
            {tags.find((t) => t.id === id)?.label ?? `#${id}`}
            <button type="button" className="chip-x" aria-label="Tag entfernen" title="Entfernen" onClick={() => onChange(value.filter((v) => v !== id))}>
              ×
            </button>
          </span>
        ))}
        <input
          className="chip-text"
          placeholder="Tag eingeben + Enter"
          value={text}
          list="tag-options"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              create();
            }
          }}
        />
        <datalist id="tag-options">
          {available.map((t) => (
            <option key={t.id} value={t.label} />
          ))}
        </datalist>
      </div>
      {available.length > 0 && available.length <= 12 && (
        <div className="chips chip-suggestions">
          {available.map((t) => (
            <button type="button" key={t.id} className="chip" onClick={() => onChange([...value, t.id])}>
              + {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
