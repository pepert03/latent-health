/**
 * Sistema visual del vídeo (y de la web): mezcla del trazo a mano y de la ilustración con grano.
 *
 * - Fondo de papel crudo con grano.
 * - Figuras y objetos con línea negra que tiembla un poco, como dibujada a mano.
 * - Rellenos planos en una paleta corta: ocre (albúmina, orina), terracota (corazón, alerta),
 *   oliva (LatentHealth) y salvia; sombras suaves.
 * - Titulares en serif (Fraunces) y textos pequeños en Inter.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { loadFont as fraunces } from "@remotion/google-fonts/Fraunces";
import { loadFont as inter } from "@remotion/google-fonts/Inter";
import { Grano } from "../estilos/comun";

const serif = fraunces("normal", { weights: ["300", "400", "500", "600"], subsets: ["latin", "latin-ext"] }).fontFamily;
fraunces("italic", { weights: ["300", "400"], subsets: ["latin", "latin-ext"] });
export const F = {
  serif,
  sans: inter("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin", "latin-ext"] }).fontFamily,
};

export const P = {
  papel: "#EFE8DA",
  papelOscuro: "#E3D8C3",
  tarjeta: "#F8F4EA",
  tinta: "#1F1C17",
  tinta2: "#5C564B",
  mudo: "#8F887A",
  linea: "#D9CFBC",
  ocre: "#D49A33",
  ocreOscuro: "#9C6B14",
  ocreClaro: "#F0D79C",
  terracota: "#C0533A",
  terracotaClaro: "#E6A48D",
  rinon: "#B8705A",
  rinonClaro: "#D69881",
  oliva: "#56654A",
  olivaClaro: "#A8B38F",
  salvia: "#C8CEB2",
  piel: "#E7D3B4",
} as const;

/** Grosor de línea en el lienzo de 1920 × 1080. */
export const GROSOR = 4.5;

export const linea = (ancho = GROSOR) => ({
  fill: "none",
  stroke: P.tinta,
  strokeWidth: ancho,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

/** Filtros comunes. Van dentro de cada <svg>. El temblor se aplica a un grupo sin transformar. */
export const Defs: React.FC = () => (
  <defs>
    <filter id="trazo" filterUnits="userSpaceOnUse" x={0} y={0} width={1920} height={1080}>
      <feTurbulence type="fractalNoise" baseFrequency={0.016} numOctaves={1} seed={3} result="ruido" />
      <feDisplacementMap in="SourceGraphic" in2="ruido" scale={4} xChannelSelector="R" yChannelSelector="G" />
    </filter>
    <filter id="sombra" x="-30%" y="-30%" width="170%" height="180%">
      <feDropShadow dx={10} dy={18} stdDeviation={16} floodColor="#3C301E" floodOpacity={0.2} />
    </filter>
    <filter id="halo" x="-150%" y="-150%" width="400%" height="400%">
      <feGaussianBlur stdDeviation={22} />
    </filter>
  </defs>
);

export const Lienzo: React.FC<{ children: React.ReactNode; fondo?: string }> = ({ children, fondo }) => (
  <AbsoluteFill
    style={{
      background: fondo ?? `radial-gradient(ellipse at 28% 18%, #F6F1E6 0%, ${P.papel} 52%, ${P.papelOscuro} 100%)`,
      fontFamily: F.sans,
      color: P.tinta,
    }}
  >
    {children}
    <Grano id="granoFino" opacidad={0.6} frecuencia={1.05} mezcla="overlay" />
    <Grano id="granoGrueso" opacidad={0.2} frecuencia={0.55} mezcla="multiply" />
  </AbsoluteFill>
);

/** Lienzo SVG a pantalla completa. */
export const Svg: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <svg width={1920} height={1080} viewBox="0 0 1920 1080" style={{ position: "absolute", inset: 0, overflow: "visible" }}>
    <Defs />
    {children}
  </svg>
);

export const Cabecera: React.FC<{
  x: number;
  y: number;
  ancho: number;
  etiqueta?: string;
  titulo: React.ReactNode;
  texto?: React.ReactNode;
  tam?: number;
}> = ({ x, y, ancho, etiqueta, titulo, texto, tam = 84 }) => (
  <div style={{ position: "absolute", left: x, top: y, width: ancho }}>
    {etiqueta ? (
      <div style={{ fontFamily: F.sans, fontWeight: 600, fontSize: 22, letterSpacing: 3, textTransform: "uppercase", color: P.mudo, marginBottom: 22 }}>
        {etiqueta}
      </div>
    ) : null}
    <div style={{ fontFamily: F.serif, fontWeight: 400, fontSize: tam, lineHeight: 1.04, letterSpacing: -tam * 0.018, color: P.tinta }}>{titulo}</div>
    {texto ? <div style={{ fontFamily: F.sans, fontSize: 30, lineHeight: 1.45, color: P.tinta2, marginTop: 28 }}>{texto}</div> : null}
  </div>
);

/** Palabra subrayada con rotulador. */
export const Marca: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = P.ocreClaro }) => (
  <span style={{ background: `linear-gradient(transparent 58%, ${color} 58%, ${color} 92%, transparent 92%)`, padding: "0 4px" }}>{children}</span>
);

export const Fuente: React.FC<{ children: React.ReactNode; x?: number; y?: number }> = ({ children, x = 120, y = 1010 }) => (
  <div style={{ position: "absolute", left: x, top: y, fontFamily: F.sans, fontSize: 19, color: P.mudo }}>{children}</div>
);
