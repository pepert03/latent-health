import React from "react";
import { loadFont as nunito } from "@remotion/google-fonts/Nunito";
import { loadFont as anton } from "@remotion/google-fonts/Anton";
import { loadFont as courier } from "@remotion/google-fonts/CourierPrime";
import { loadFont as instrument } from "@remotion/google-fonts/InstrumentSerif";
import { loadFont as fraunces } from "@remotion/google-fonts/Fraunces";
import { loadFont as marker } from "@remotion/google-fonts/PermanentMarker";
import { loadFont as inter } from "@remotion/google-fonts/Inter";

export const F = {
  redonda: nunito("normal", { weights: ["700", "800", "900"], subsets: ["latin", "latin-ext"] }).fontFamily,
  cartel: anton("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily,
  maquina: courier("normal", { weights: ["400", "700"], subsets: ["latin", "latin-ext"] }).fontFamily,
  serif: instrument("normal", { weights: ["400"], subsets: ["latin", "latin-ext"] }).fontFamily,
  serifItalica: instrument("italic", { weights: ["400"], subsets: ["latin", "latin-ext"] }).fontFamily,
  fraunces: fraunces("normal", { weights: ["400", "600"], subsets: ["latin", "latin-ext"] }).fontFamily,
  rotulador: marker("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily,
  sans: inter("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin", "latin-ext"] }).fontFamily,
};

/** Números pseudoaleatorios repetibles (mismo dibujo en cada render). */
export const azar = (semilla: number) => {
  let s = semilla;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
};

/** Capa de grano de papel o de impresión. */
export const Grano: React.FC<{ id: string; opacidad?: number; frecuencia?: number; mezcla?: React.CSSProperties["mixBlendMode"] }> = ({
  id,
  opacidad = 0.25,
  frecuencia = 0.85,
  mezcla = "multiply",
}) => (
  <svg width={1920} height={1080} style={{ position: "absolute", inset: 0, mixBlendMode: mezcla, pointerEvents: "none" }}>
    <filter id={id}>
      <feTurbulence type="fractalNoise" baseFrequency={frecuencia} numOctaves={3} stitchTiles="stitch" />
      <feColorMatrix type="saturate" values="0" />
    </filter>
    <rect width={1920} height={1080} filter={`url(#${id})`} opacity={opacidad} />
  </svg>
);
