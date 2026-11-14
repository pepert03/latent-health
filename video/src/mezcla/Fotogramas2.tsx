/** Fotogramas 3 y 5 del guion: dónde falla hoy, la app y el kit. */
import React from "react";
import { Cabecera, F, Fuente, Lienzo, P, Svg, linea } from "./sistema";

// --- 3 · Dónde falla hoy ---

const Tubo: React.FC<{ x: number; y: number; liquido?: number; color?: string }> = ({ x, y, liquido = 0, color = P.ocreClaro }) => (
  <g transform={`translate(${x} ${y})`}>
    {liquido > 0 ? <path d={`M -16 ${44 - liquido} L 16 ${44 - liquido} L 16 44 C 16 60 -16 60 -16 44 Z`} fill={color} /> : null}
    <path d="M -16 -34 L -16 44 C -16 60 16 60 16 44 L 16 -34" {...linea(3.6)} />
    <rect x={-22} y={-46} width={44} height={14} rx={4} fill={P.tinta} />
  </g>
);

const iconos = [
  // No se pide: tubo vacío y una cruz
  <g key="a">
    <Tubo x={52} y={62} />
    <path d="M 82 22 L 102 42 M 102 22 L 82 42" stroke={P.terracota} strokeWidth={5} strokeLinecap="round" />
  </g>,
  // Una muestra engaña: un tubo con albúmina y el siguiente sin ella
  <g key="b">
    <Tubo x={34} y={62} liquido={46} />
    <Tubo x={86} y={62} liquido={46} color={P.salvia} />
    <path d="M 26 4 L 42 4 M 34 -4 L 34 12" stroke={P.terracota} strokeWidth={4.5} strokeLinecap="round" />
    <path d="M 78 4 L 94 4" stroke={P.oliva} strokeWidth={4.5} strokeLinecap="round" />
  </g>,
  // No se apunta: carpeta con las líneas vacías
  <g key="c" {...linea(3.6)}>
    <path d="M 12 28 L 46 28 L 56 40 L 108 40 L 108 102 L 12 102 Z" fill={P.tarjeta} />
    <path d="M 30 62 L 90 62 M 30 80 L 72 80" strokeDasharray="6 8" />
  </g>,
  // No se trata: cápsula
  <g key="d" transform="rotate(-35 60 60)">
    <path d="M 40 44 L 60 44 L 60 76 L 40 76 C 18 76 18 44 40 44 Z" fill={P.olivaClaro} />
    <rect x={18} y={44} width={84} height={32} rx={16} {...linea(3.6)} />
    <line x1={60} y1={44} x2={60} y2={76} {...linea(3.6)} />
  </g>,
];

const fallos = [
  { cifra: "4 %", titulo: "No se pide", texto: "de los hipertensos se mira la orina. De los diabéticos, la mitad.", fuente: "Shin et al., Hypertension 2021" },
  { cifra: "1 de 2", titulo: "Una muestra engaña", texto: "positivos no se repite en la muestra siguiente.", fuente: "NHANES 2009-2010" },
  { cifra: "> 80 %", titulo: "No se apunta", texto: "de quienes tienen el riñón dañado según su analítica no lo tienen en su historia.", fuente: "REVEAL-CKD" },
  { cifra: "10-33 %", titulo: "No se trata", texto: "de los candidatos toma el fármaco que protege el riñón y el corazón.", fuente: "iSGLT2 · docs/solucion.md" },
];

export const M3Fallos: React.FC = () => {
  const x = (i: number) => 120 + i * 435;
  const cx = (i: number) => x(i) + 78;
  const cy = 450;
  return (
    <Lienzo>
      <Cabecera x={120} y={90} ancho={1700} etiqueta="3 · Dónde falla hoy" titulo="El circuito se rompe en cuatro sitios." tam={84} />
      <Svg>
        <g filter="url(#trazo)">
          <path d={`M ${cx(0)} ${cy} L ${cx(3)} ${cy}`} {...linea(3)} strokeDasharray="2 14" />
          {[0, 1, 2].map((i) => {
            const m = (cx(i) + cx(i + 1)) / 2;
            return <path key={i} d={`M ${m - 12} ${cy - 18} L ${m - 2} ${cy + 18} M ${m + 4} ${cy - 18} L ${m + 14} ${cy + 18}`} stroke={P.terracota} strokeWidth={5} strokeLinecap="round" />;
          })}
          {fallos.map((_, i) => (
            <g key={i}>
              <circle cx={cx(i)} cy={cy} r={80} fill={P.tarjeta} filter="url(#sombra)" />
              <circle cx={cx(i)} cy={cy} r={80} {...linea(3.6)} />
              <g transform={`translate(${cx(i) - 60} ${cy - 60})`}>{iconos[i]}</g>
            </g>
          ))}
        </g>
      </Svg>
      {fallos.map((f, i) => (
        <div key={i} style={{ position: "absolute", left: x(i), top: 580, width: 380 }}>
          <div style={{ fontFamily: F.serif, fontWeight: 300, fontSize: 104, lineHeight: 1, letterSpacing: -3, color: P.terracota }}>{f.cifra}</div>
          <div style={{ fontWeight: 600, fontSize: 32, marginTop: 22 }}>{f.titulo}</div>
          <div style={{ fontSize: 25, lineHeight: 1.45, color: P.tinta2, marginTop: 10 }}>{f.texto}</div>
          <div style={{ fontSize: 18, color: P.mudo, marginTop: 18 }}>{f.fuente}</div>
        </div>
      ))}
    </Lienzo>
  );
};

// --- 5 · La app ---

const Pastilla: React.FC<{ children: React.ReactNode; activa?: boolean }> = ({ children, activa }) => (
  <div
    style={{
      display: "inline-block",
      padding: "14px 30px",
      borderRadius: 999,
      border: `3px solid ${P.tinta}`,
      background: activa ? P.terracota : "transparent",
      color: activa ? P.tarjeta : P.tinta,
      fontWeight: 600,
      fontSize: 32,
      marginBottom: 18,
    }}
  >
    {children}
  </div>
);

/** Pantalla del móvil: resultado de una tira (HTML, nítido). */
const PantallaTira: React.FC = () => (
  <div style={{ width: "100%", height: "100%", borderRadius: 58, background: P.tarjeta, overflow: "hidden", position: "relative", fontFamily: F.sans, color: P.tinta }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "22px 40px 0", fontSize: 20, fontWeight: 600 }}>
      <span>8:02</span>
      <span style={{ width: 110, height: 30, borderRadius: 999, background: "#26221C" }} />
      <span style={{ width: 34, height: 16, borderRadius: 4, border: `2px solid ${P.tinta}` }} />
    </div>
    <div style={{ padding: "26px 32px 0" }}>
      <div style={{ fontSize: 19, color: P.mudo, fontWeight: 500 }}>Hoy · tira 2 de 3 · primera orina</div>
      <div style={{ fontFamily: F.serif, fontSize: 40, marginTop: 4 }}>Tu tira de hoy</div>
      <div style={{ marginTop: 18, height: 150, borderRadius: 22, background: "#E6DCC7", position: "relative" }}>
        <div style={{ position: "absolute", left: 30, right: 30, top: 50, height: 50, borderRadius: 10, background: "#FBF8F0", boxShadow: "0 3px 0 rgba(0,0,0,0.08)" }}>
          <div style={{ position: "absolute", left: 18, top: 0, bottom: 0, width: 90, background: "#E8E0CF", borderRadius: "10px 0 0 10px" }} />
          <div style={{ position: "absolute", right: 92, top: 9, width: 34, height: 32, borderRadius: 5, background: P.ocreClaro }} />
          <div style={{ position: "absolute", right: 42, top: 9, width: 34, height: 32, borderRadius: 5, background: P.olivaClaro }} />
        </div>
        {[
          { left: 14, top: 14, borderLeft: true, borderTop: true },
          { right: 14, top: 14, borderRight: true, borderTop: true },
          { left: 14, bottom: 14, borderLeft: true, borderBottom: true },
          { right: 14, bottom: 14, borderRight: true, borderBottom: true },
        ].map((c, i) => (
          <div
            key={i}
            style={{
              position: "absolute",
              width: 26,
              height: 26,
              left: c.left,
              right: c.right,
              top: c.top,
              bottom: c.bottom,
              borderLeft: c.borderLeft ? `4px solid ${P.oliva}` : undefined,
              borderRight: c.borderRight ? `4px solid ${P.oliva}` : undefined,
              borderTop: c.borderTop ? `4px solid ${P.oliva}` : undefined,
              borderBottom: c.borderBottom ? `4px solid ${P.oliva}` : undefined,
            }}
          />
        ))}
      </div>
      <div style={{ marginTop: 22, background: "#FFFDF8", borderRadius: 24, padding: "22px 24px", border: `2px solid ${P.linea}` }}>
        <div style={{ fontFamily: F.serif, fontSize: 40, color: P.terracota, lineHeight: 1, whiteSpace: "nowrap" }}>Repite mañana</div>
        <div style={{ fontSize: 21, lineHeight: 1.45, color: P.tinta2, marginTop: 12 }}>Con esta tira no se puede descartar. Mañana, con la primera orina del día.</div>
      </div>
      <div style={{ marginTop: 26, fontSize: 18, color: P.mudo, fontWeight: 500 }}>Probabilidad de albuminuria</div>
      <div style={{ position: "relative", marginTop: 44, height: 14, borderRadius: 7, background: "#E6DCC7" }}>
        <div style={{ position: "absolute", left: 0, width: "5%", top: 0, bottom: 0, background: P.olivaClaro, borderRadius: "7px 0 0 7px" }} />
        <div style={{ position: "absolute", right: 0, width: "5%", top: 0, bottom: 0, background: P.terracotaClaro, borderRadius: "0 7px 7px 0" }} />
        <div style={{ position: "absolute", left: "14%", top: -7, width: 28, height: 28, marginLeft: -14, borderRadius: 999, background: P.tinta, border: `4px solid ${P.tarjeta}` }} />
        <div style={{ position: "absolute", left: "14%", top: -48, marginLeft: -30, fontFamily: F.serif, fontSize: 30 }}>14 %</div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 16, color: P.mudo, marginTop: 12 }}>
        <span>descartada</span>
        <span>confirmada</span>
      </div>
      <div style={{ marginTop: 30, background: P.oliva, color: P.tarjeta, borderRadius: 999, padding: "18px 0", textAlign: "center", fontSize: 22, fontWeight: 600 }}>Recuérdamelo mañana</div>
    </div>
  </div>
);

export const M5App: React.FC = () => (
  <Lienzo>
    <Cabecera x={120} y={150} ancho={720} etiqueta="5 · La app" titulo="No le da un número. Le dice qué hacer." tam={88} />
    <div style={{ position: "absolute", left: 120, top: 560 }}>
      <Pastilla>Ya está</Pastilla>
      <br />
      <Pastilla activa>Repite mañana</Pastilla>
      <br />
      <Pastilla>Manda el tubo al laboratorio</Pastilla>
    </div>
    <div style={{ position: "absolute", left: 120, top: 870, width: 700, fontSize: 28, lineHeight: 1.45, color: P.tinta2 }}>
      Cada tira mueve la probabilidad. Solo repite quien sale dudoso.
    </div>
    <Svg>
      {/* Bote de orina y tira sobre la mesa, al lado del móvil */}
      <g filter="url(#trazo)">
        <g transform="translate(1650 640)">
          <ellipse cx={0} cy={66} rx={70} ry={12} fill={P.tinta} opacity={0.08} />
          <path d="M -58 -40 L 58 -40 L 48 44 C 46 62 -46 62 -48 44 Z" fill={P.ocreClaro} />
          <path d="M -66 -96 L 66 -96 L 48 44 C 46 62 -46 62 -48 44 Z" {...linea()} />
          <path d="M -70 -110 L 70 -110 L 70 -92 L -70 -92 Z" {...linea()} fill={P.olivaClaro} />
          <path d="M 30 -70 L 44 -70 M 30 -46 L 44 -46 M 30 -22 L 44 -22" {...linea(3)} />
        </g>
        <g transform="translate(1560 860) rotate(-16)">
          <rect x={0} y={0} width={300} height={44} rx={9} fill="#FBF8F0" filter="url(#sombra)" />
          <rect x={0} y={0} width={80} height={44} rx={9} fill="#E8E0CF" />
          <rect x={196} y={7} width={32} height={30} rx={5} fill={P.ocreClaro} />
          <rect x={242} y={7} width={32} height={30} rx={5} fill={P.olivaClaro} />
          <rect x={0} y={0} width={300} height={44} rx={9} {...linea(3.6)} />
        </g>
      </g>
    </Svg>
    <div
      style={{
        position: "absolute",
        left: 1040,
        top: 90,
        width: 440,
        height: 900,
        borderRadius: 74,
        background: "#26221C",
        padding: 16,
        rotate: "-3deg",
        boxShadow: "24px 34px 60px rgba(60, 48, 30, 0.28)",
      }}
    >
      <PantallaTira />
    </div>
  </Lienzo>
);

// --- 5 · El kit, visto desde arriba ---

const Rotulo: React.FC<{ x: number; y: number; titulo: string; texto: string }> = ({ x, y, titulo, texto }) => (
  <div style={{ position: "absolute", left: x, top: y, width: 300 }}>
    <div style={{ fontWeight: 600, fontSize: 26 }}>{titulo}</div>
    <div style={{ fontSize: 21, color: P.tinta2, marginTop: 4, lineHeight: 1.35 }}>{texto}</div>
  </div>
);

export const M5Kit: React.FC = () => (
  <Lienzo>
    <Cabecera
      x={120}
      y={150}
      ancho={560}
      etiqueta="5 · El kit"
      titulo="Solo lo que le falta."
      tam={96}
      texto="Nadie compra nada. Las tiras se mandan, los aparatos se prestan y la glucosa se mide en la farmacia."
    />
    <Svg>
      <g filter="url(#trazo)">
        {/* Caja del kit */}
        <g transform="translate(770 150) rotate(-2)">
          <rect x={0} y={0} width={540} height={330} rx={20} fill={P.oliva} filter="url(#sombra)" />
          <rect x={36} y={40} width={468} height={250} rx={14} fill={P.tarjeta} />
          <rect x={0} y={0} width={540} height={330} rx={20} {...linea()} />
          <rect x={36} y={40} width={468} height={250} rx={14} {...linea(3)} />
        </g>
        {/* Tres tiras */}
        {[0, 1, 2].map((i) => (
          <g key={i} transform={`translate(${1385 + i * 92} ${140}) rotate(${[-4, 1, 5][i]} 32 180)`}>
            <rect x={0} y={0} width={64} height={360} rx={10} fill="#FBF8F0" filter="url(#sombra)" />
            <rect x={0} y={0} width={64} height={110} rx={10} fill="#E8E0CF" />
            <rect x={9} y={254} width={46} height={40} rx={6} fill={P.ocreClaro} />
            <rect x={9} y={304} width={46} height={40} rx={6} fill={P.olivaClaro} />
            <rect x={0} y={0} width={64} height={360} rx={10} {...linea(3.6)} />
          </g>
        ))}
        {/* Reloj */}
        <g transform="translate(1720 310) scale(0.9)">
          <rect x={-42} y={-150} width={84} height={300} rx={26} fill={P.salvia} filter="url(#sombra)" />
          <rect x={-42} y={-150} width={84} height={300} rx={26} {...linea(3.6)} />
          <rect x={-62} y={-68} width={124} height={136} rx={38} {...linea(3.6)} fill="#2B2721" />
          <path d="M -44 4 L -24 4 L -16 -22 L -4 32 L 6 -8 L 14 4 L 44 4" fill="none" stroke={P.ocre} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round" />
        </g>
        {/* Manguito y su aparato */}
        <g transform="translate(770 670) rotate(2)">
          <rect x={0} y={0} width={470} height={200} rx={28} fill={P.olivaClaro} filter="url(#sombra)" />
          <rect x={300} y={22} width={150} height={156} rx={16} fill={P.salvia} />
          <path d="M 320 50 L 430 50 M 320 80 L 430 80 M 320 110 L 430 110 M 320 140 L 430 140" {...linea(2)} opacity={0.5} />
          <rect x={0} y={0} width={470} height={200} rx={28} {...linea()} />
          <rect x={300} y={22} width={150} height={156} rx={16} {...linea(3)} />
        </g>
        <path d="M 1240 780 C 1290 790 1290 700 1340 710" {...linea(9)} />
        <path d="M 1240 780 C 1290 790 1290 700 1340 710" stroke={P.salvia} strokeWidth={4} fill="none" strokeLinecap="round" />
        <g transform="translate(1330 640)">
          <rect x={0} y={0} width={220} height={290} rx={30} fill={P.tarjeta} filter="url(#sombra)" />
          <rect x={24} y={28} width={172} height={150} rx={14} fill="#DCE1CC" />
          <circle cx={110} cy={236} r={26} fill={P.olivaClaro} />
          <rect x={0} y={0} width={220} height={290} rx={30} {...linea()} />
          <rect x={24} y={28} width={172} height={150} rx={14} {...linea(3)} />
          <circle cx={110} cy={236} r={26} {...linea(3)} />
        </g>
        {/* Farmacia: la glucosa ya no va en el kit */}
        <g transform="translate(1640 690)">
          <rect x={0} y={0} width={150} height={150} rx={26} fill={P.tarjeta} filter="url(#sombra)" />
          <path d="M 56 30 L 94 30 L 94 56 L 120 56 L 120 94 L 94 94 L 94 120 L 56 120 L 56 94 L 30 94 L 30 56 L 56 56 Z" fill={P.oliva} />
          <rect x={0} y={0} width={150} height={150} rx={26} {...linea()} />
        </g>
      </g>
      <text x={1040} y={295} textAnchor="middle" fontFamily={F.serif} fontSize={46} fill={P.tinta} transform="rotate(-2 1040 300)">
        LatentHealth
      </text>
      <text x={1040} y={335} textAnchor="middle" fontFamily={F.sans} fontSize={22} fill={P.tinta2} transform="rotate(-2 1040 300)">
        Kit de orina · 3 tiras
      </text>
      <text x={1440} y={748} textAnchor="middle" fontFamily={F.serif} fontSize={56} fill={P.tinta}>
        128
      </text>
      <text x={1440} y={796} textAnchor="middle" fontFamily={F.serif} fontSize={38} fill={P.tinta2}>
        82 · 74 ♥
      </text>
    </Svg>
    <Rotulo x={780} y={505} titulo="Kit de orina" texto="se manda a casa" />
    <Rotulo x={1385} y={525} titulo="3 tiras" texto="albúmina y creatinina" />
    <Rotulo x={1660} y={480} titulo="Reloj" texto="si ya lo tiene" />
    <Rotulo x={780} y={905} titulo="Manguito" texto="se presta una semana, si hace falta" />
    <Rotulo x={1600} y={865} titulo="Glucosa" texto="una medida en la farmacia" />
    <Fuente>Ilustración del kit. Lo que recibe cada paciente lo decide su ficha.</Fuente>
  </Lienzo>
);
