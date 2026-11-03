import { describe, expect, it } from "vitest";
import { addWidget, greeting, moveWidget, removeWidget, resizeWidget, sanitizeLayout, shiftWidget, type WidgetMeta, type WidgetPlacement } from "./layout";

const metas: WidgetMeta[] = [
  { type: "a", sizes: ["m", "l"], defaultSize: "l" },
  { type: "b", sizes: ["s", "m"], defaultSize: "s" },
  { type: "c", sizes: ["full"], defaultSize: "full" },
];
const layout: WidgetPlacement[] = [
  { type: "a", size: "l" },
  { type: "b", size: "s" },
  { type: "c", size: "full" },
];

describe("sanitizeLayout", () => {
  it("rejects non-arrays", () => {
    expect(sanitizeLayout(null, metas)).toBeNull();
    expect(sanitizeLayout({ a: 1 }, metas)).toBeNull();
  });

  it("drops unknown and duplicate widgets and fixes unsupported sizes", () => {
    const raw = [{ type: "a", size: "s" }, { type: "zzz", size: "m" }, { type: "a", size: "m" }, "junk", { type: "b" }];
    expect(sanitizeLayout(raw, metas)).toEqual([
      { type: "a", size: "l" },
      { type: "b", size: "s" },
    ]);
  });
});

describe("layout edits", () => {
  it("moves a widget onto another one's position", () => {
    expect(moveWidget(layout, "c", "a").map((w) => w.type)).toEqual(["c", "a", "b"]);
    expect(moveWidget(layout, "a", "c").map((w) => w.type)).toEqual(["b", "c", "a"]);
    expect(moveWidget(layout, "a", "nope")).toBe(layout);
  });

  it("shifts within bounds only", () => {
    expect(shiftWidget(layout, "b", -1).map((w) => w.type)).toEqual(["b", "a", "c"]);
    expect(shiftWidget(layout, "a", -1)).toBe(layout);
    expect(shiftWidget(layout, "c", 1)).toBe(layout);
  });

  it("resizes, removes and adds", () => {
    expect(resizeWidget(layout, "a", "m")[0]).toEqual({ type: "a", size: "m" });
    expect(removeWidget(layout, "b").map((w) => w.type)).toEqual(["a", "c"]);
    expect(addWidget(removeWidget(layout, "b"), metas[1])[2]).toEqual({ type: "b", size: "s" });
    expect(addWidget(layout, metas[0])).toBe(layout);
  });
});

describe("greeting", () => {
  it("depends on the hour", () => {
    expect(greeting(new Date(2026, 0, 1, 3))).toBe("Gute Nacht");
    expect(greeting(new Date(2026, 0, 1, 8))).toBe("Guten Morgen");
    expect(greeting(new Date(2026, 0, 1, 14))).toBe("Guten Tag");
    expect(greeting(new Date(2026, 0, 1, 20))).toBe("Guten Abend");
  });
});
