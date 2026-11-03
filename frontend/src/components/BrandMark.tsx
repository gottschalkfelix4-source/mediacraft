/** The MediaCraft cube (craft) with film strip and play symbol (media); coloured by the accent palette. */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="86 86 340 340" aria-hidden="true">
      <polygon points="110,175 256,259 256,425 110,341" fill="#fff" fillOpacity=".62" />
      <polygon points="256,259 402,175 402,341 256,425" fill="#fff" fillOpacity=".84" />
      <polygon points="256,91 402,175 256,259 110,175" fill="#fff" />
      <g style={{ fill: "var(--accent-2)" }} fillOpacity=".75">
        <polygon points="130.4,198.4 153.8,211.8 153.8,228.4 130.4,215" />
        <polygon points="130.4,324.5 153.8,338 153.8,354.6 130.4,341.1" />
        <polygon points="168.4,220.2 191.8,233.7 191.8,250.3 168.4,236.8" />
        <polygon points="168.4,346.4 191.8,359.8 191.8,376.4 168.4,363" />
        <polygon points="206.4,242.1 229.7,255.5 229.7,272.1 206.4,258.7" />
        <polygon points="206.4,368.2 229.7,381.7 229.7,398.3 206.4,384.8" />
      </g>
      <polygon points="127.5,228.2 238.5,292.1 238.5,371.8 127.5,307.9" style={{ fill: "var(--accent-2)" }} fillOpacity=".25" />
      <polygon points="295.4,269.5 295.4,369.1 372.8,274.8" strokeWidth="20" strokeLinejoin="round" style={{ fill: "var(--accent)", stroke: "var(--accent)" }} />
      <path
        d="M256,135 Q263,168 302,175 Q263,182 256,201 Q249,182 210,175 Q249,168 256,135Z"
        style={{ fill: "var(--accent)" }}
      />
    </svg>
  );
}
