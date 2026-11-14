/** Estilo 1, plano vectorial: "un mismo daño" (corazón y riñón unidos por los vasos; la albúmina se escapa). */
import React from "react";
import { AbsoluteFill } from "remotion";
import { F, azar } from "./comun";

const CORAZON = "M0,90 C-150,-10 -160,-150 -60,-160 C-20,-163 0,-130 0,-110 C0,-130 20,-163 60,-160 C160,-150 150,-10 0,90 Z";
const RINON = "M -60,-140 C 40,-170 120,-90 110,0 C 100,90 40,160 -40,140 C -90,128 -100,90 -70,55 C -45,25 -45,-25 -70,-55 C -100,-90 -110,-125 -60,-140 Z";
const ARTERIA = "M 660 600 C 820 760 1040 820 1200 640";
const VENA = "M 1180 520 C 1030 380 830 380 700 470";

export const E1PlanoVectorial: React.FC = () => {
  const r = azar(7);
  const estrellas = Array.from({ length: 120 }, () => ({ x: r() * 1920, y: r() * 1080, s: 1 + r() * 2.5, o: 0.2 + r() * 0.6 }));
  const albumina = Array.from({ length: 16 }, (_, i) => ({ x: 1230 + (r() - 0.5) * 120, y: 800 + i * 14 + r() * 40, s: 7 + r() * 9 }));
  return (
    <AbsoluteFill style={{ background: "radial-gradient(circle at 50% 55%, #24386a 0%, #14204a 45%, #0b1230 100%)" }}>
      <svg width={1920} height={1080}>
        <defs>
          <radialGradient id="halo" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ff6b8a" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#ff6b8a" stopOpacity={0} />
          </radialGradient>
          <radialGradient id="haloAzul" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#63d5ff" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#63d5ff" stopOpacity={0} />
          </radialGradient>
          <radialGradient id="haloAmarillo" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffd34d" stopOpacity={0.6} />
            <stop offset="100%" stopColor="#ffd34d" stopOpacity={0} />
          </radialGradient>
          <clipPath id="clipCorazon">
            <path d={CORAZON} />
          </clipPath>
          <clipPath id="clipRinon">
            <path d={RINON} />
          </clipPath>
        </defs>
        {estrellas.map((e, i) => (
          <circle key={i} cx={e.x} cy={e.y} r={e.s} fill="#cfe3ff" opacity={e.o} />
        ))}
        <g transform="translate(0 50)">
        {/* Vasos: arteria y vena, con brillo y glóbulos */}
        <path d={VENA} fill="none" stroke="#3b4fc4" strokeWidth={54} strokeLinecap="round" />
        <path d={VENA} fill="none" stroke="#5d74ec" strokeWidth={26} strokeLinecap="round" />
        <path d={ARTERIA} fill="none" stroke="#b8263f" strokeWidth={60} strokeLinecap="round" />
        <path d={ARTERIA} fill="none" stroke="#e5405a" strokeWidth={34} strokeLinecap="round" />
        <path d={ARTERIA} fill="none" stroke="#ff8a9c" strokeWidth={6} strokeLinecap="round" strokeDasharray="40 70" opacity={0.8} />
        {[0.2, 0.38, 0.55, 0.72, 0.86].map((p, i) => {
          const x = 660 + (1200 - 660) * p;
          const y = 600 + Math.sin(p * Math.PI) * 190 - p * 10;
          return <ellipse key={i} cx={x} cy={y} rx={13} ry={9} fill="#ffd0d6" transform={`rotate(${i * 30} ${x} ${y})`} />;
        })}

        {/* Corazón */}
        <circle cx={600} cy={520} r={330} fill="url(#halo)" />
        <g transform="translate(600 540) scale(1.55)">
          <path d={CORAZON} fill="#e33a54" />
          <g clipPath="url(#clipCorazon)">
            <path d="M -160 -170 L 20 -170 C -60 -100 -80 0 -10 100 L -160 100 Z" fill="#ff6b80" />
            <circle cx={-80} cy={-110} r={18} fill="#ffb3bf" />
          </g>
          <path d={CORAZON} fill="none" stroke="#9d1c33" strokeWidth={6} />
          <path d="M -30 -150 C -24 -170 -10 -180 8 -188" fill="none" stroke="#e33a54" strokeWidth={26} strokeLinecap="round" />
          <path d="M 40 -150 C 46 -166 60 -174 78 -178" fill="none" stroke="#5d74ec" strokeWidth={22} strokeLinecap="round" />
        </g>

        {/* Riñón con los glomérulos y la albúmina que se escapa */}
        <circle cx={1250} cy={560} r={300} fill="url(#haloAzul)" />
        <g transform="translate(1260 560) scale(1.75)">
          <path d={RINON} fill="#d8608a" />
          <g clipPath="url(#clipRinon)">
            <path d="M 0 -170 C 140 -120 140 120 0 170 L 140 170 L 140 -170 Z" fill="#f28fb0" />
            {[[-10, -90], [40, -40], [55, 30], [20, 95], [-20, -20], [10, 40]].map(([x, y], i) => (
              <g key={i}>
                <circle cx={x} cy={y} r={14} fill="#a23866" />
                <circle cx={x - 3} cy={y - 3} r={6} fill="#ffd34d" />
              </g>
            ))}
          </g>
          <path d={RINON} fill="none" stroke="#8e2a56" strokeWidth={5} />
          <path d="M -70 30 C -90 60 -60 110 -50 150" fill="none" stroke="#f2c14e" strokeWidth={14} strokeLinecap="round" />
        </g>
        <circle cx={1230} cy={900} r={130} fill="url(#haloAmarillo)" />
        {albumina.map((a, i) => (
          <g key={i}>
            <circle cx={a.x} cy={a.y} r={a.s} fill="#ffd34d" />
            <circle cx={a.x - a.s * 0.3} cy={a.y - a.s * 0.3} r={a.s * 0.35} fill="#fff4c2" />
          </g>
        ))}

        {/* Etiquetas */}
        <g fontFamily={F.redonda} fontWeight={800} fill="#ffffff">
          <line x1={430} y1={300} x2={500} y2={360} stroke="#ffffff" strokeWidth={3} opacity={0.7} />
          <text x={300} y={285} fontSize={40}>Corazón</text>
          <line x1={1420} y1={330} x2={1360} y2={400} stroke="#ffffff" strokeWidth={3} opacity={0.7} />
          <text x={1420} y={315} fontSize={40}>Riñón</text>
          <line x1={1330} y1={880} x2={1400} y2={900} stroke="#ffd34d" strokeWidth={3} />
          <text x={1410} y={915} fontSize={40} fill="#ffd34d">Albúmina en la orina</text>
          <text x={1410} y={960} fontSize={28} fontWeight={700} fill="#cfe3ff">la primera señal</text>
        </g>
        </g>
      </svg>
      <div style={{ position: "absolute", top: 40, left: 0, right: 0, textAlign: "center", fontFamily: F.redonda, color: "#fff" }}>
        <div style={{ fontSize: 96, fontWeight: 900, letterSpacing: -1 }}>Un mismo daño</div>
        <div style={{ fontSize: 40, fontWeight: 700, color: "#a9c4f5" }}>diabetes · hipertensión · riñón · corazón</div>
      </div>
    </AbsoluteFill>
  );
};
