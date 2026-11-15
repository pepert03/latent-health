/** Fotogramas 6 a 8 del guion: el médico, los resultados y el cierre. */
import React from "react";
import { Persona } from "./Personajes";
import { Cabecera, F, Fuente, Lienzo, P, Svg, linea } from "./sistema";

// --- 6 · El médico ---

const Grupo: React.FC<{ color: string; titulo: string; children: React.ReactNode }> = ({ color, titulo, children }) => (
  <div style={{ marginTop: 22 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 20, fontWeight: 700, letterSpacing: 2.5, textTransform: "uppercase", color: P.tinta2 }}>
      <span style={{ width: 14, height: 14, borderRadius: 999, background: color }} />
      {titulo}
    </div>
    {children}
  </div>
);

const FilaActuar: React.FC<{ nombre: string; texto: string; resaltada?: boolean }> = ({ nombre, texto, resaltada }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "11px 20px",
      marginTop: 6,
      borderRadius: 16,
      background: resaltada ? "#F6E3D9" : "transparent",
      border: resaltada ? `2px solid ${P.terracotaClaro}` : "2px solid transparent",
    }}
  >
    <div>
      <div style={{ fontSize: 28, fontWeight: 600 }}>{nombre}</div>
      <div style={{ fontSize: 22, color: P.tinta2, marginTop: 4 }}>{texto}</div>
    </div>
    <div style={{ fontSize: 20, fontWeight: 600, padding: "8px 18px", borderRadius: 999, border: `2px solid ${P.tinta}` }}>Ver ficha</div>
  </div>
);

const FilaMedir: React.FC<{ nombre: string; prueba: string; p: number }> = ({ nombre, prueba, p }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 24, padding: "12px 20px", marginTop: 6 }}>
    <div style={{ width: 230, fontSize: 26, fontWeight: 600 }}>{nombre}</div>
    <div style={{ flex: 1, height: 14, borderRadius: 7, background: "#E6DCC7", position: "relative" }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${p}%`, borderRadius: 7, background: P.ocre }} />
    </div>
    <div style={{ width: 80, fontFamily: F.serif, fontSize: 32, textAlign: "right" }}>{p} %</div>
    <div style={{ width: 220, fontSize: 20, color: P.tinta2 }}>pedir: {prueba}</div>
  </div>
);

export const M6Medica: React.FC = () => (
  <Lienzo>
    <Cabecera x={120} y={80} ancho={1700} etiqueta="6 · El médico" titulo="No recibe cien alertas. Recibe una lista." tam={80} />
    <Svg>
      <ellipse cx={360} cy={934} rx={160} ry={13} fill={P.tinta} opacity={0.07} />
      <g filter="url(#trazo)">
        <path d="M 130 930 L 330 930 M 362 930 L 640 930" {...linea()} />
        <Persona x={360} y={930} s={1.28} bata gafas ropa={P.tarjeta} brazo="M 68 -262 L 68 -112" />
      </g>
    </Svg>
    <div
      style={{
        position: "absolute",
        left: 720,
        top: 250,
        width: 1080,
        height: 770,
        background: P.tarjeta,
        borderRadius: 30,
        border: `3px solid ${P.tinta}`,
        boxShadow: "18px 26px 50px rgba(60, 48, 30, 0.2)",
        padding: "34px 40px",
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <span style={{ fontFamily: F.serif, fontSize: 46 }}>Mi cupo</span>
          <span style={{ fontSize: 22, color: P.mudo, marginLeft: 18 }}>1.500 pacientes · hoy</span>
        </div>
        <span style={{ fontSize: 20, color: P.tinta2 }}>ordenada por lo que cambiaría</span>
      </div>
      <Grupo color={P.terracota} titulo="Actuar · ya está claro y no consta">
        <FilaActuar nombre="Julián, 62" texto="Albuminuria repetida en casa, sin enfermedad renal registrada" resaltada />
        <FilaActuar nombre="Manuel, 77" texto="Pulso irregular dos días · P(fibrilación auricular) 73 %" />
        <FilaActuar nombre="Carmen, 59" texto="Tensión alta en casa, 149/91, sin hipertensión registrada" />
      </Grupo>
      <Grupo color={P.ocre} titulo="Medir · probabilidad de un hallazgo nuevo">
        <FilaMedir nombre="Elena, 74" prueba="creatinina" p={59} />
        <FilaMedir nombre="Marta, 47" prueba="orina en casa" p={39} />
        <FilaMedir nombre="Antonio, 81" prueba="creatinina" p={24} />
      </Grupo>
    </div>
  </Lienzo>
);

// --- 7 · Resultados: diabetes oculta ---

const Puntos: React.FC<{ x0: number; y0: number; llenos: number; color: string }> = ({ x0, y0, llenos, color }) => (
  <g>
    {Array.from({ length: 100 }, (_, i) => {
      const c = i % 10;
      const f = Math.floor(i / 10);
      const lleno = i < llenos;
      return (
        <circle key={i} cx={x0 + c * 46} cy={y0 + f * 46} r={15} fill={lleno ? color : "none"} stroke={lleno ? P.tinta : P.mudo} strokeWidth={lleno ? 3 : 2.4} strokeDasharray={lleno ? undefined : "4 5"} />
      );
    })}
  </g>
);

export const M7Diabetes: React.FC = () => {
  const izq = 330;
  const der = 1130;
  const y0 = 360;
  return (
    <Lienzo>
      <Cabecera x={120} y={70} ancho={1700} etiqueta="7 · Resultados" titulo="Con los mismos análisis, 75 en lugar de 52." tam={80} />
      <div style={{ position: "absolute", left: izq - 16, top: 270, fontSize: 26, color: P.tinta2, fontWeight: 600 }}>Hoy: cuestionario FINDRISC</div>
      <div style={{ position: "absolute", left: der - 16, top: 270, fontSize: 26, color: P.tinta, fontWeight: 600 }}>LatentHealth: historia y una glucosa</div>
      <Svg>
        <g filter="url(#trazo)">
          <Puntos x0={izq} y0={y0} llenos={52} color={P.mudo} />
          <Puntos x0={der} y0={y0} llenos={75} color={P.oliva} />
        </g>
      </Svg>
      {[
        { x: izq - 16, n: "52", color: P.mudo },
        { x: der - 16, n: "75", color: P.oliva },
      ].map((b) => (
        <div key={b.n} style={{ position: "absolute", left: b.x, top: 805, display: "flex", alignItems: "baseline", gap: 20 }}>
          <span style={{ fontFamily: F.serif, fontWeight: 300, fontSize: 120, lineHeight: 1, color: b.color, letterSpacing: -3 }}>{b.n}</span>
          <span style={{ fontSize: 26, color: P.tinta2, width: 400, lineHeight: 1.35 }}>de cada 100 diabetes ocultas encontradas</span>
        </div>
      ))}
      <Fuente>NHANES 2005-2018 · 27.300 adultos sin diabetes diagnosticada · se analiza al 20-22 % · reports/diabetes_en_casa.md</Fuente>
    </Lienzo>
  );
};

// --- 8 · Cierre ---

export const M8Cierre: React.FC = () => (
  <Lienzo>
    <div style={{ position: "absolute", left: 0, right: 0, top: 120, textAlign: "center", fontFamily: F.serif, fontStyle: "italic", fontWeight: 300, fontSize: 46, color: P.tinta2 }}>
      No habrá un día en que le salvemos la vida.
    </div>
    <Svg>
      <circle cx={1290} cy={380} r={58} fill={P.ocre} opacity={0.35} filter="url(#halo)" />
      <ellipse cx={900} cy={784} rx={300} ry={14} fill={P.tinta} opacity={0.07} />
      <g filter="url(#trazo)">
        <circle cx={1290} cy={380} r={50} {...linea()} fill={P.ocreClaro} />
        <path d="M 560 780 L 880 780 M 912 780 L 1240 780 M 1272 780 L 1380 780" {...linea()} />
        <Persona x={820} y={780} s={1.25} gafas ropa={P.olivaClaro} brazo="M 100 -240 L 152 -96" />
        <Persona x={1100} y={780} s={0.7} mira={-1} coleta ropa={P.ocre} brazo="M 100 -228 L 129 -171" />
        <path d="M 1010 596 C 1002 584 988 590 994 602 L 1010 618 L 1026 602 C 1032 590 1018 584 1010 596 Z" {...linea(3)} fill={P.terracotaClaro} />
      </g>
    </Svg>
    <div style={{ position: "absolute", left: 0, right: 0, top: 830, textAlign: "center", fontFamily: F.serif, fontWeight: 400, fontSize: 80, color: P.tinta, letterSpacing: -1.5 }}>
      Dentro de diez años, Julián seguirá aquí.
    </div>
    <div style={{ position: "absolute", left: 0, right: 0, top: 950, textAlign: "center", fontSize: 26, color: P.tinta2 }}>
      ≈ 1.200 muertes evitadas al año en España · estimación con supuestos
    </div>
  </Lienzo>
);
