/** Estilo 9, ilustración con grano: la tira en el móvil y la probabilidad que da la app. */
import React from "react";
import { AbsoluteFill } from "remotion";
import { F, Grano } from "./comun";

const OLIVA = "#4f5640";
const OLIVA_CLARO = "#7d8460";
const CREMA = "#f1e6cf";
const ROJO = "#d9472b";

export const E9Grano: React.FC = () => (
  <AbsoluteFill style={{ background: "linear-gradient(170deg, #e7b25b 0%, #c79a57 30%, #8a8a6c 62%, #5d6452 100%)" }}>
    <svg width={1920} height={1080} style={{ position: "absolute" }}>
      <defs>
        <linearGradient id="pantalla" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fbf3df" />
          <stop offset="100%" stopColor="#e9d9b7" />
        </linearGradient>
        <linearGradient id="tira" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fbf6ea" />
          <stop offset="100%" stopColor="#ded2b4" />
        </linearGradient>
        <radialGradient id="disco" cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="#f6eedb" />
          <stop offset="60%" stopColor="#d9cdb0" />
          <stop offset="100%" stopColor="#a99d80" />
        </radialGradient>
        <filter id="sombra" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx={18} dy={24} stdDeviation={22} floodColor="#2c2a1f" floodOpacity={0.45} />
        </filter>
      </defs>

      {/* Tubo de la medida que sale del móvil y llega al resultado (como la goma del fonendo) */}
      <path d="M 700 860 C 760 1060 1060 1040 1110 860 C 1160 740 1260 700 1340 680" fill="none" stroke="#2f3426" strokeWidth={30} strokeLinecap="round" filter="url(#sombra)" />
      <path d="M 700 860 C 760 1060 1060 1040 1110 860 C 1160 740 1260 700 1340 680" fill="none" stroke="#454c37" strokeWidth={12} strokeLinecap="round" opacity={0.7} />

      {/* Móvil */}
      <g transform="rotate(-6 560 520)" filter="url(#sombra)">
        <rect x={360} y={120} width={400} height={790} rx={58} fill="#2b2a24" />
        <rect x={380} y={140} width={360} height={750} rx={44} fill="url(#pantalla)" />
        {/* Tira de orina dentro de la pantalla */}
        <rect x={525} y={230} width={70} height={520} rx={14} fill="url(#tira)" stroke="#bfae88" strokeWidth={3} />
        {[
          ["#e9e3c6", 300],
          ["#9fb07d", 380],
          ["#c9c1e0", 460],
          ["#e3b46c", 540],
        ].map(([c, y]) => (
          <rect key={y as number} x={535} y={y as number} width={50} height={48} rx={6} fill={c as string} />
        ))}
        <rect x={505} y={280} width={110} height={330} rx={16} fill="none" stroke={ROJO} strokeWidth={4} strokeDasharray="14 10" />
        <g stroke={ROJO} strokeWidth={10} strokeLinecap="round">
          <line x1={470} y1={190} x2={470} y2={218} />
          <line x1={456} y1={204} x2={484} y2={204} />
        </g>
        <text x={560} y={820} textAnchor="middle" fontFamily={F.fraunces} fontSize={36} fontWeight={600} fill={OLIVA}>
          Repite mañana
        </text>
      </g>

      {/* Disco con la probabilidad */}
      <g filter="url(#sombra)" transform="translate(0 80)">
        <circle cx={1500} cy={470} r={250} fill={OLIVA} />
        <circle cx={1500} cy={470} r={205} fill="url(#disco)" />
        <circle cx={1500} cy={470} r={160} fill="none" stroke={OLIVA_CLARO} strokeWidth={4} />
        {/* Arco: 14 % de la vuelta */}
        <circle cx={1500} cy={470} r={182} fill="none" stroke={ROJO} strokeWidth={22} strokeDasharray={`${2 * Math.PI * 182 * 0.14} ${2 * Math.PI * 182}`} transform="rotate(-90 1500 470)" strokeLinecap="round" />
        <text x={1500} y={500} textAnchor="middle" fontFamily={F.fraunces} fontSize={120} fontWeight={600} fill={OLIVA}>
          14 %
        </text>
        <text x={1500} y={560} textAnchor="middle" fontFamily={F.sans} fontSize={28} fontWeight={600} fill={OLIVA_CLARO} letterSpacing={2}>
          ALBUMINURIA
        </text>
      </g>
    </svg>

    <div style={{ position: "absolute", left: 1150, top: 50, width: 700, fontFamily: F.fraunces, color: CREMA, fontSize: 62, lineHeight: 1.05 }}>
      Cada tira mueve la probabilidad.
    </div>
    <div style={{ position: "absolute", left: 1150, top: 200, width: 680, fontFamily: F.sans, color: "#efe6cf", fontSize: 28, opacity: 0.9 }}>
      Solo repite quien sale dudoso.
    </div>
    <Grano id="granoFino" opacidad={0.55} frecuencia={1.1} mezcla="overlay" />
    <Grano id="granoGrueso" opacidad={0.18} frecuencia={0.6} />
  </AbsoluteFill>
);
