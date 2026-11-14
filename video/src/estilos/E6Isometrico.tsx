/** Estilo 6, isométrico de línea: el circuito casa, farmacia, centro de salud y la lista de la médica. */
import React from "react";
import { AbsoluteFill } from "remotion";
import { F } from "./comun";

const S = 34; // tamaño de una casilla de la rejilla
const O = { x: 1300, y: 260 }; // origen
const COS = Math.cos(Math.PI / 6);
const iso = (x: number, y: number, z = 0): [number, number] => [O.x + (x - y) * COS * S, O.y + (x + y) * 0.5 * S - z * S];
const pts = (...p: [number, number, number][]) => p.map(([x, y, z]) => iso(x, y, z).join(",")).join(" ");

const TINTA = "#141414";
const L = { stroke: TINTA, strokeWidth: 2.4, strokeLinejoin: "round" as const };

/** Caja isométrica: cara de arriba, izquierda y derecha. */
const Caja: React.FC<{ x: number; y: number; w: number; d: number; h: number; arriba?: string; izq?: string; der?: string; z?: number }> = ({
  x,
  y,
  w,
  d,
  h,
  arriba = "#ffffff",
  izq = "#ffffff",
  der = "#ececec",
  z = 0,
}) => (
  <g {...L}>
    <polygon points={pts([x, y + d, z], [x + w, y + d, z], [x + w, y + d, z + h], [x, y + d, z + h])} fill={izq} />
    <polygon points={pts([x + w, y, z], [x + w, y + d, z], [x + w, y + d, z + h], [x + w, y, z + h])} fill={der} />
    <polygon points={pts([x, y, z + h], [x + w, y, z + h], [x + w, y + d, z + h], [x, y + d, z + h])} fill={arriba} />
  </g>
);

/** Ventanas en la cara izquierda (la que mira a la cámara por la izquierda). */
const Ventanas: React.FC<{ x: number; y: number; w: number; d: number; filas: number; cols: number; z0?: number }> = ({ x, y, w, d, filas, cols, z0 = 0.6 }) => (
  <g {...L} strokeWidth={1.8}>
    {Array.from({ length: filas * cols }, (_, i) => {
      const c = i % cols;
      const f = Math.floor(i / cols);
      const x0 = x + 0.4 + c * ((w - 0.4) / cols);
      const z = z0 + f * 1.1;
      return <polygon key={i} points={pts([x0, y + d, z], [x0 + 0.7, y + d, z], [x0 + 0.7, y + d, z + 0.7], [x0, y + d, z + 0.7])} fill="#f4f4f4" />;
    })}
  </g>
);

const Tarjeta: React.FC<{ x: number; y: number; titulo: string; linea: string; acento?: boolean }> = ({ x, y, titulo, linea, acento }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      background: "#fff",
      border: `2px solid ${TINTA}`,
      borderRadius: 10,
      padding: "14px 18px",
      fontFamily: F.sans,
      boxShadow: `6px 6px 0 ${TINTA}`,
      minWidth: 250,
    }}
  >
    <div style={{ fontSize: 18, color: "#6b6b6b", fontWeight: 500 }}>{titulo}</div>
    <div style={{ fontSize: 26, fontWeight: 700, color: acento ? "#0f8f7e" : TINTA }}>{linea}</div>
  </div>
);

export const E6Isometrico: React.FC = () => {
  const camino = (a: [number, number, number], b: [number, number, number], c: [number, number, number]) => `M ${iso(...a).join(" ")} L ${iso(...b).join(" ")} L ${iso(...c).join(" ")}`;
  return (
    <AbsoluteFill style={{ background: "#f6f6f4", fontFamily: F.sans }}>
      {/* Marco de página, como la referencia */}
      <div style={{ position: "absolute", inset: 40, background: "#ffffff", borderRadius: 18, boxShadow: "0 1px 0 rgba(0,0,0,0.05)" }} />
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        <defs>
          <pattern id="rayado" width={8} height={8} patternUnits="userSpaceOnUse" patternTransform="rotate(30)">
            <line x1={0} y1={0} x2={0} y2={8} stroke={TINTA} strokeWidth={1.4} />
          </pattern>
          <marker id="flecha" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={7} markerHeight={7} orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill={TINTA} />
          </marker>
        </defs>
        {/* Rejilla isométrica */}
        <g stroke="#e6e6e3" strokeWidth={1.2}>
          {Array.from({ length: 23 }, (_, i) => (
            <line key={`a${i}`} x1={iso(i - 3, -3)[0]} y1={iso(i - 3, -3)[1]} x2={iso(i - 3, 19)[0]} y2={iso(i - 3, 19)[1]} />
          ))}
          {Array.from({ length: 23 }, (_, i) => (
            <line key={`b${i}`} x1={iso(-3, i - 3)[0]} y1={iso(-3, i - 3)[1]} x2={iso(19, i - 3)[0]} y2={iso(19, i - 3)[1]} />
          ))}
        </g>

        {/* Caminos punteados entre los sitios */}
        <g fill="none" stroke={TINTA} strokeWidth={2.2} strokeDasharray="7 7" markerEnd="url(#flecha)">
          <path d={camino([2.2, 7.7, 0], [2.2, 6.5, 0], [2.2, 5.3, 0])} />
          <path d={camino([5.2, 3, 0], [8, 3, 0], [10.7, 3, 0])} />
          <path d={camino([12.2, 9, 0], [13.5, 9, 0], [13.5, 4.8, 0])} />
          <path d={camino([16.2, 2.5, 0], [17, 2.5, 0], [17, 8.7, 0])} />
        </g>

        {/* Casa del paciente */}
        <Caja x={1} y={1.5} w={4} d={3.5} h={2.4} />
        <g {...L}>
          <polygon points={pts([1, 5, 2.4], [5, 5, 2.4], [5, 3.25, 4.1], [1, 3.25, 4.1])} fill="#ffffff" />
          <polygon points={pts([5, 1.5, 2.4], [5, 5, 2.4], [5, 3.25, 4.1])} fill="url(#rayado)" />
          <polygon points={pts([1, 1.5, 2.4], [5, 1.5, 2.4], [5, 3.25, 4.1], [1, 3.25, 4.1])} fill="#ececec" />
          <polygon points={pts([2.2, 5, 0], [3.1, 5, 0], [3.1, 5, 1.5], [2.2, 5, 1.5])} fill={TINTA} />
        </g>
        <Ventanas x={3.2} y={1.5} w={1.6} d={3.5} filas={1} cols={1} z0={0.9} />

        {/* Farmacia */}
        <Caja x={8.5} y={7.5} w={3.5} d={3} h={2.6} />
        <Ventanas x={8.5} y={7.5} w={3.5} d={3} filas={1} cols={3} z0={0.5} />
        <g {...L}>
          <polygon points={pts([12, 8.4, 2.9], [12, 9.6, 2.9], [12, 9.6, 4.1], [12, 8.4, 4.1])} fill="#ffffff" />
        </g>
        <g fill="#0f8f7e">
          <polygon points={pts([12, 8.85, 3.15], [12, 9.15, 3.15], [12, 9.15, 3.85], [12, 8.85, 3.85])} />
          <polygon points={pts([12, 8.65, 3.35], [12, 9.35, 3.35], [12, 9.35, 3.65], [12, 8.65, 3.65])} />
        </g>

        {/* Centro de salud */}
        <Caja x={11} y={0.5} w={5} d={4} h={4.2} />
        <Ventanas x={11} y={0.5} w={5} d={4} filas={3} cols={4} />
        <Caja x={12.5} y={2} w={1.6} d={1.6} h={0.5} z={4.2} der="url(#rayado)" />

        {/* Móvil tumbado con la tira */}
        <g {...L}>
          <polygon points={pts([1.2, 8, 0.25], [3.2, 8, 0.25], [3.2, 11.6, 0.25], [1.2, 11.6, 0.25])} fill={TINTA} />
          <polygon points={pts([1.4, 8.3, 0.26], [3.0, 8.3, 0.26], [3.0, 11.3, 0.26], [1.4, 11.3, 0.26])} fill="#ffffff" />
          <polygon points={pts([2.0, 8.8, 0.27], [2.4, 8.8, 0.27], [2.4, 10.8, 0.27], [2.0, 10.8, 0.27])} fill="#ffffff" />
        </g>
        {[9.2, 9.7, 10.2].map((y, i) => (
          <polygon key={i} points={pts([2.0, y, 0.28], [2.4, y, 0.28], [2.4, y + 0.3, 0.28], [2.0, y + 0.3, 0.28])} fill={i === 1 ? "#0f8f7e" : "#d8d8d8"} stroke={TINTA} strokeWidth={1.5} />
        ))}

        {/* Portátil de la médica */}
        <g {...L}>
          <polygon points={pts([15, 9, 0], [19, 9, 0], [19, 11.5, 0], [15, 11.5, 0])} fill="#ececec" />
          <polygon points={pts([15, 9, 0], [19, 9, 0], [19, 9, 2.6], [15, 9, 2.6])} fill="#ffffff" />
        </g>
        {[0.6, 1.1, 1.6, 2.1].map((z, i) => (
          <line key={i} x1={iso(15.5, 9, z)[0]} y1={iso(15.5, 9, z)[1]} x2={iso(i === 0 ? 17.5 : 18.4, 9, z)[0]} y2={iso(i === 0 ? 17.5 : 18.4, 9, z)[1]} stroke={i === 0 ? "#0f8f7e" : TINTA} strokeWidth={i === 0 ? 5 : 2} />
        ))}
      </svg>

      {/* Navegación y titular (sirve tal cual de cabecera de la web) */}
      <div style={{ position: "absolute", left: 100, top: 82, display: "flex", alignItems: "center", gap: 14 }}>
        <svg width={40} height={40} viewBox="0 0 40 40">
          <rect x={4} y={10} width={32} height={20} rx={10} fill="none" stroke={TINTA} strokeWidth={2.6} />
          <circle cx={14} cy={20} r={4} fill="#0f8f7e" />
        </svg>
        <div style={{ fontSize: 26, fontWeight: 600 }}>LatentHealth</div>
      </div>
      <div style={{ position: "absolute", right: 100, top: 78, background: TINTA, color: "#fff", borderRadius: 999, padding: "12px 26px", fontSize: 22, fontWeight: 600 }}>Ver la demo</div>
      <div style={{ position: "absolute", left: 100, top: 330, width: 740, fontFamily: F.serif, fontSize: 84, lineHeight: 1.02, color: TINTA, letterSpacing: -1 }}>
        El paciente se mide en casa.
        <span style={{ color: "#9a9a96" }}> La médica recibe la lista ya ordenada.</span>
      </div>
      <div style={{ position: "absolute", left: 100, top: 640, width: 600, fontSize: 28, color: "#555", lineHeight: 1.4 }}>
        Tiras de orina, tensión y pulso desde casa. Un modelo que sabe cuánto fiarse de cada medida.
      </div>

      <Tarjeta x={860} y={790} titulo="Julián · tira 2 de 3" linea="Repite mañana" />
      <Tarjeta x={1530} y={810} titulo="Lista del cupo" linea="Actuar: 5 pacientes" acento />
    </AbsoluteFill>
  );
};
