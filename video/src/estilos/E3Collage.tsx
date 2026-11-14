/** Estilo 3, collage de papel: "96 de cada 100 hipertensos nunca se miran la orina". */
import React from "react";
import { AbsoluteFill } from "remotion";
import { F, Grano, azar } from "./comun";

/** Polígono de papel rasgado: rectángulo con los bordes irregulares. */
const rasgado = (x: number, y: number, w: number, h: number, semilla: number, dientes = 40, amp = 9) => {
  const r = azar(semilla);
  const pts: string[] = [];
  for (let i = 0; i <= dientes; i++) pts.push(`${x + (w * i) / dientes},${y + (r() - 0.5) * amp}`);
  for (let i = 0; i <= dientes / 3; i++) pts.push(`${x + w + (r() - 0.5) * amp},${y + (h * i) / (dientes / 3)}`);
  for (let i = dientes; i >= 0; i--) pts.push(`${x + (w * i) / dientes},${y + h + (r() - 0.5) * amp}`);
  for (let i = Math.floor(dientes / 3); i >= 0; i--) pts.push(`${x + (r() - 0.5) * amp},${y + (h * i) / (dientes / 3)}`);
  return pts.join(" ");
};

const Recorte: React.FC<{ texto: string; x: number; y: number; giro: number; fondo: string; color: string; tamano: number; fuente?: string }> = ({
  texto,
  x,
  y,
  giro,
  fondo,
  color,
  tamano,
  fuente = F.cartel,
}) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      rotate: `${giro}deg`,
      background: fondo,
      color,
      fontFamily: fuente,
      fontSize: tamano,
      lineHeight: 1,
      padding: `${tamano * 0.06}px ${tamano * 0.12}px ${tamano * 0.02}px`,
      boxShadow: "6px 8px 0 rgba(0,0,0,0.18)",
    }}
  >
    {texto}
  </div>
);

const Cinta: React.FC<{ x: number; y: number; giro: number; ancho?: number }> = ({ x, y, giro, ancho = 150 }) => (
  <div style={{ position: "absolute", left: x, top: y, width: ancho, height: 42, rotate: `${giro}deg`, background: "rgba(235, 220, 160, 0.75)", boxShadow: "0 2px 4px rgba(0,0,0,0.12)" }} />
);

export const E3Collage: React.FC = () => {
  const columnas = 20;
  return (
    <AbsoluteFill style={{ background: "#e8dfcc" }}>
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        <defs>
          <pattern id="trama" width={14} height={14} patternUnits="userSpaceOnUse" patternTransform="rotate(20)">
            <circle cx={7} cy={7} r={3.4} fill="#c8402f" />
          </pattern>
          <pattern id="tramaNegra" width={10} height={10} patternUnits="userSpaceOnUse">
            <circle cx={5} cy={5} r={2.2} fill="#1d1b19" />
          </pattern>
        </defs>
        {/* Papeles de fondo */}
        <polygon points={rasgado(-40, 610, 2000, 520, 3, 60, 22)} fill="#1d1b19" />
        <polygon points={rasgado(1180, -40, 820, 560, 5, 30, 18)} fill="url(#trama)" opacity={0.9} />
        <polygon points={rasgado(80, 120, 560, 420, 11, 30, 14)} fill="#f6f1e6" />
        <circle cx={1500} cy={300} r={170} fill="#c8402f" />
        <circle cx={1500} cy={300} r={170} fill="url(#tramaNegra)" opacity={0.18} />

        {/* Hoja fotocopiada con las 100 personas */}
        {/* Tubo de orina recortado sobre el círculo rojo */}
        <g transform="rotate(14 1500 300)">
          <rect x={1455} y={150} width={90} height={280} rx={45} fill="#f6f1e6" />
          <rect x={1455} y={290} width={90} height={140} rx={0} fill="#f2d24b" />
          <rect x={1455} y={380} width={90} height={50} rx={45} fill="#f2d24b" />
          <rect x={1440} y={130} width={120} height={46} rx={8} fill="#1d1b19" />
        </g>
        <g transform="rotate(-2 1260 830)">
          <polygon points={rasgado(880, 650, 800, 360, 21, 50, 10)} fill="#f3efe4" />
          {Array.from({ length: 100 }, (_, i) => {
            const c = i % columnas;
            const f = Math.floor(i / columnas);
            const x = 920 + c * 37;
            const y = 700 + f * 58;
            const destacada = i >= 96;
            return (
              <g key={i} transform={`translate(${x} ${y})`} opacity={destacada ? 1 : 0.75}>
                <circle cx={0} cy={-8} r={7} fill={destacada ? "#1d1b19" : "#8d867a"} />
                <path d="M -11 20 C -11 4 -6 0 0 0 C 6 0 11 4 11 20 Z" fill={destacada ? "#1d1b19" : "#8d867a"} />
                {destacada ? <ellipse cx={0} cy={4} rx={19} ry={27} fill="none" stroke="#c8402f" strokeWidth={4} transform="rotate(-8)" /> : null}
              </g>
            );
          })}
        </g>
      </svg>

      {/* Titular recortado */}
      <Recorte texto="96" x={130} y={130} giro={-4} fondo="#1d1b19" color="#f6f1e6" tamano={330} />
      <Recorte texto="de cada" x={560} y={190} giro={3} fondo="#f6f1e6" color="#1d1b19" tamano={110} />
      <Recorte texto="100" x={600} y={320} giro={-2} fondo="#c8402f" color="#f6f1e6" tamano={170} />
      <Cinta x={150} y={110} giro={-12} />
      <Cinta x={880} y={300} giro={18} ancho={120} />

      {/* Tiras escritas a máquina */}
      <div style={{ position: "absolute", left: 120, top: 640, rotate: "-1.5deg", background: "#f6f1e6", padding: "16px 26px", fontFamily: F.maquina, fontSize: 40, color: "#1d1b19", boxShadow: "5px 6px 0 rgba(0,0,0,0.25)" }}>
        hipertensos nunca se hacen
      </div>
      <div style={{ position: "absolute", left: 160, top: 730, rotate: "1deg", background: "#f6f1e6", padding: "16px 26px", fontFamily: F.maquina, fontSize: 40, color: "#1d1b19", boxShadow: "5px 6px 0 rgba(0,0,0,0.25)" }}>
        la prueba de <b style={{ background: "#f2d24b", padding: "0 6px" }}>orina</b>.
      </div>
      <div style={{ position: "absolute", left: 130, top: 960, fontFamily: F.maquina, fontSize: 24, color: "#e8dfcc" }}>Fuente: Shin et al., Hypertension 2021</div>
      <div style={{ position: "absolute", left: 1620, top: 1000, rotate: "-6deg", fontFamily: F.rotulador, fontSize: 40, color: "#f2d24b" }}>solo 4 ↑</div>
      <Grano id="granoCollage" opacidad={0.45} />
    </AbsoluteFill>
  );
};
