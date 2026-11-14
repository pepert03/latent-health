/**
 * Gráficos de LatentHealth. Son componentes puros de React + SVG: reciben `t` (avance de 0 a 1)
 * y los datos, y no dependen de Remotion. En el vídeo `t` sale del fotograma; en la web, del
 * scroll o de un temporizador. Así el vídeo y la web enseñan exactamente lo mismo.
 */
import React from "react";
import { C, fontFamily, numero } from "../marca/tema";
import { tramo } from "../marca/tiempo";

// --- Persona (icono) ---

export const Persona: React.FC<{ x: number; y: number; s: number; color: string; opacidad?: number }> = ({ x, y, s, color, opacidad = 1 }) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacidad}>
    <circle cx={0} cy={-11} r={6} fill={color} />
    <path d="M -9 12 C -9 0 -5 -3 0 -3 C 5 -3 9 0 9 12 Z" fill={color} />
  </g>
);

/** Rejilla de personas: `resaltadas` de `total` se encienden en orden con el avance. */
export const RejillaPersonas: React.FC<{
  total?: number;
  columnas?: number;
  resaltadas: number;
  t: number;
  color?: string;
  apagado?: string;
  ancho?: number;
  desdeElFinal?: boolean;
}> = ({ total = 100, columnas = 20, resaltadas, t, color = C.marca, apagado = C.linea, ancho = 900, desdeElFinal = false }) => {
  const filas = Math.ceil(total / columnas);
  const paso = ancho / columnas;
  const encendidas = Math.round(resaltadas * tramo(t, 0.15, 1));
  return (
    <svg width={ancho} height={filas * paso * 1.25} viewBox={`0 0 ${ancho} ${filas * paso * 1.25}`}>
      {Array.from({ length: total }, (_, i) => {
        const c = i % columnas;
        const f = Math.floor(i / columnas);
        const aparece = tramo(t, (i / total) * 0.15, (i / total) * 0.15 + 0.1);
        const indice = desdeElFinal ? total - 1 - i : i;
        const on = indice < encendidas;
        return <Persona key={i} x={c * paso + paso / 2} y={f * paso * 1.25 + paso * 0.7} s={paso / 30} color={on ? color : apagado} opacidad={aparece} />;
      })}
    </svg>
  );
};

// --- Número grande que cuenta ---

export const NumeroGrande: React.FC<{
  valor: number;
  t: number;
  decimales?: number;
  prefijo?: string;
  sufijo?: string;
  tamano?: number;
  color?: string;
}> = ({ valor, t, decimales = 0, prefijo = "", sufijo = "", tamano = 220, color = C.tinta }) => (
  <div style={{ fontFamily, fontWeight: 800, fontSize: tamano, color, letterSpacing: -tamano * 0.04, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
    {prefijo}
    {numero(valor * tramo(t, 0, 0.85), decimales)}
    {sufijo}
  </div>
);

// --- Barras horizontales comparadas (hoy en gris, nosotros en marca) ---

export type Barra = { etiqueta: string; valor: number; nuestro?: boolean; nota?: string };

export const BarrasComparadas: React.FC<{
  barras: Barra[];
  t: number;
  maximo: number;
  minimo?: number;
  ancho?: number;
  formato?: (v: number) => string;
  alto?: number;
}> = ({ barras, t, maximo, minimo = 0, ancho = 1100, formato = (v) => `${numero(v)} %`, alto = 64 }) => (
  <div style={{ fontFamily, width: ancho, display: "flex", flexDirection: "column", gap: alto * 0.55 }}>
    {barras.map((b, i) => {
      const p = tramo(t, 0.1 + i * 0.18, 0.55 + i * 0.18);
      const largo = ((b.valor - minimo) / (maximo - minimo)) * (ancho - 220) * p;
      return (
        <div key={b.etiqueta}>
          <div style={{ fontSize: 34, fontWeight: b.nuestro ? 700 : 500, color: b.nuestro ? C.tinta : C.tinta2, marginBottom: 10 }}>
            {b.etiqueta}
            {b.nota ? <span style={{ fontWeight: 400, color: C.mudo, fontSize: 26 }}>{"  ·  " + b.nota}</span> : null}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <div style={{ height: alto, width: Math.max(largo, 4), background: b.nuestro ? C.marca : C.hoy, borderRadius: "0 8px 8px 0" }} />
            <div style={{ fontSize: alto * 0.75, fontWeight: 800, color: b.nuestro ? C.marca : C.hoyOscuro, opacity: p, fontVariantNumeric: "tabular-nums" }}>
              {formato(b.valor * p + minimo * (1 - p))}
            </div>
          </div>
        </div>
      );
    })}
  </div>
);

// --- La cadena que se rompe (los cuatro fallos) ---

export const Cadena: React.FC<{ eslabones: string[]; rotos: number; t: number; ancho?: number }> = ({ eslabones, rotos, t, ancho = 1600 }) => {
  const n = eslabones.length;
  const paso = ancho / n;
  return (
    <svg width={ancho} height={300} viewBox={`0 0 ${ancho} 300`} style={{ fontFamily, overflow: "visible" }}>
      {eslabones.map((texto, i) => {
        const aparece = tramo(t, i * 0.08, i * 0.08 + 0.2);
        const roto = i < rotos ? tramo(t, 0.35 + i * 0.15, 0.5 + i * 0.15) : 0;
        const cx = paso * i + paso / 2;
        const color = roto > 0.5 ? C.ambar : C.marca;
        return (
          <g key={i} opacity={aparece}>
            <g transform={`translate(${cx - roto * 18} ${110 + roto * 14}) rotate(${-roto * 9})`}>
              <path d={`M ${-paso * 0.18} -55 A 55 55 0 0 0 ${-paso * 0.18} 55 L 0 55`} fill="none" stroke={color} strokeWidth={22} strokeLinecap="round" />
            </g>
            <g transform={`translate(${cx + roto * 18} ${110 - roto * 14}) rotate(${roto * 9})`}>
              <path d={`M 0 -55 L ${paso * 0.18} -55 A 55 55 0 0 1 ${paso * 0.18} 55`} fill="none" stroke={color} strokeWidth={22} strokeLinecap="round" />
            </g>
            {roto < 0.5 ? <line x1={cx - paso * 0.1} x2={cx + paso * 0.1} y1={55} y2={55} stroke={color} strokeWidth={22} strokeLinecap="round" /> : null}
            <text x={cx} y={235} textAnchor="middle" fontSize={34} fontWeight={700} fill={C.tinta}>
              {i + 1}
            </text>
            <text x={cx} y={280} textAnchor="middle" fontSize={30} fill={C.tinta2}>
              {texto}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

// --- Probabilidad que se mueve con cada medida ---

export type Paso = { etiqueta: string; p: number };

export const PasosProbabilidad: React.FC<{ pasos: Paso[]; t: number; ancho?: number; umbralAlto?: number; umbralBajo?: number }> = ({
  pasos,
  t,
  ancho = 1200,
  umbralAlto = 0.95,
  umbralBajo = 0.05,
}) => {
  const alto = 420;
  const x = (i: number) => 80 + (i * (ancho - 160)) / Math.max(pasos.length - 1, 1);
  const y = (p: number) => 40 + (1 - p) * (alto - 100);
  const visibles = tramo(t, 0, 1) * (pasos.length - 1);
  const puntos = pasos.map((s, i) => `${x(i)},${y(s.p)}`);
  const largoTotal = pasos.length - 1;
  return (
    <svg width={ancho} height={alto} viewBox={`0 0 ${ancho} ${alto}`} style={{ fontFamily, overflow: "visible" }}>
      <rect x={60} y={y(1)} width={ancho - 120} height={y(umbralAlto) - y(1)} fill={C.ambarClaro} />
      <rect x={60} y={y(umbralBajo)} width={ancho - 120} height={y(0) - y(umbralBajo)} fill={C.marcaClaro} />
      <text x={ancho - 70} y={y(1) + 30} textAnchor="end" fontSize={24} fill={C.ambar} fontWeight={600}>
        confirmada
      </text>
      <text x={ancho - 70} y={y(0) - 10} textAnchor="end" fontSize={24} fill={C.marcaOscuro} fontWeight={600}>
        descartada
      </text>
      <line x1={60} x2={ancho - 60} y1={y(0)} y2={y(0)} stroke={C.linea} strokeWidth={2} />
      <polyline
        points={puntos.join(" ")}
        fill="none"
        stroke={C.tinta}
        strokeWidth={4}
        strokeLinejoin="round"
        strokeDasharray={`${ancho * 2}`}
        strokeDashoffset={ancho * 2 * (1 - visibles / largoTotal)}
      />
      {pasos.map((s, i) => {
        const o = Math.min(1, Math.max(0, visibles - i + 1));
        return (
          <g key={i} opacity={o}>
            <circle cx={x(i)} cy={y(s.p)} r={13} fill={C.fondo} stroke={C.tinta} strokeWidth={4} />
            <text x={x(i)} y={y(s.p) - 28} textAnchor="middle" fontSize={34} fontWeight={800} fill={C.tinta}>
              {numero(s.p * 100)} %
            </text>
            <text x={x(i)} y={alto - 14} textAnchor="middle" fontSize={26} fill={C.tinta2}>
              {s.etiqueta}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

// --- Silueta con puntos de medida ---

export const Silueta: React.FC<{ t: number; puntos?: { x: number; y: number; color: string }[]; alto?: number; color?: string }> = ({
  t,
  puntos = [],
  alto = 760,
  color = C.tinta,
}) => {
  const dibujo = tramo(t, 0, 0.5);
  const contorno =
    "M200 70 C235 70 258 98 258 132 C258 166 235 194 200 194 C165 194 142 166 142 132 C142 98 165 70 200 70 Z " +
    "M120 230 C150 214 176 210 200 210 C224 210 250 214 280 230 C318 250 330 290 334 340 L346 520 C347 540 330 548 318 532 L296 360 L292 560 L300 900 C300 925 268 930 262 905 L214 620 L200 620 L186 620 L138 905 C132 930 100 925 100 900 L108 560 L104 360 L82 532 C70 548 53 540 54 520 L66 340 C70 290 82 250 120 230 Z";
  return (
    <svg height={alto} viewBox="0 0 400 940" style={{ overflow: "visible" }}>
      <path d={contorno} fill="none" stroke={color} strokeWidth={5} strokeDasharray={4000} strokeDashoffset={4000 * (1 - dibujo)} strokeLinejoin="round" />
      {puntos.map((p, i) => {
        const a = tramo(t, 0.45 + i * 0.08, 0.6 + i * 0.08);
        return (
          <g key={i} opacity={a}>
            <circle cx={p.x} cy={p.y} r={34 * a} fill={p.color} opacity={0.18} />
            <circle cx={p.x} cy={p.y} r={14} fill={p.color} />
          </g>
        );
      })}
    </svg>
  );
};
