/**
 * Personajes y anatomía en el estilo de trazo: cabeza en arco, cuerpo en cúpula, línea negra a mano
 * y rellenos planos. Coordenadas locales con el origen en los pies (Persona) o arriba a la
 * izquierda (Anatomia). El grosor de línea se compensa con la escala para que todos los personajes
 * tengan el mismo trazo.
 */
import React from "react";
import { GROSOR, P, linea } from "./sistema";

const CUERPO = "M -105 0 L -105 -240 C -105 -292 -60 -320 0 -320 C 60 -320 105 -292 105 -240 L 105 0";
const CABEZA = "M -42 -334 L -42 -410 C -42 -436 -22 -452 0 -452 C 22 -452 42 -436 42 -410 L 42 -392 L 55 -378 L 42 -372 L 42 -334";

export type PersonaProps = {
  x: number;
  y: number;
  s?: number;
  mira?: 1 | -1;
  ropa?: string;
  piel?: string;
  gafas?: boolean;
  mono?: boolean;
  bata?: boolean;
  coleta?: boolean;
  brazo?: string;
  dentro?: React.ReactNode;
};

/** Una persona de pie, de perfil (mira a la derecha con mira = 1). */
export const Persona: React.FC<PersonaProps> = ({
  x,
  y,
  s = 1,
  mira = 1,
  ropa = P.olivaClaro,
  piel = P.piel,
  gafas,
  mono,
  bata,
  coleta,
  brazo = "M 68 -262 L 68 -112",
  dentro,
}) => (
  <g transform={`translate(${x} ${y}) scale(${s * mira} ${s})`}>
    <path d={`${CUERPO} Z`} fill={ropa} />
    {dentro}
    <path d={`${CABEZA} Z`} fill={piel} />
    {mono ? <circle cx={-38} cy={-444} r={19} fill={P.tinta} /> : null}
    <g {...linea(GROSOR / s)}>
      <path d={CUERPO} />
      <path d={CABEZA} />
      <path d="M 9 -402 Q 17 -396 25 -402" />
      <path d={brazo} />
      <path d={bata ? "M 0 -318 L 0 0" : "M 0 -130 L 0 0"} />
      {gafas ? (
        <>
          <circle cx={17} cy={-401} r={14} />
          <path d="M 3 -404 L -30 -411" />
        </>
      ) : null}
      {coleta ? <path d="M -40 -424 C -74 -428 -78 -388 -46 -386" /> : null}
      {bata ? (
        <>
          <path d="M -46 -318 C -48 -262 58 -258 58 -318" />
          <path d="M 26 -272 L 26 -246" />
          <circle cx={26} cy={-236} r={10} fill={P.tarjeta} />
        </>
      ) : null}
    </g>
  </g>
);

/** Persona pequeña para rejillas de "x de cada 100". */
export const MiniPersona: React.FC<{ x: number; y: number; s?: number; relleno?: string; discontinua?: boolean; color?: string }> = ({
  x,
  y,
  s = 1,
  relleno,
  discontinua,
  color = P.tinta,
}) => {
  const cuerpo = "M -20 0 L -20 -20 C -20 -31 -11 -36 0 -36 C 11 -36 20 -31 20 -20 L 20 0";
  const cabeza = "M -10 -41 L -10 -52 C -10 -58 -5 -62 0 -62 C 5 -62 10 -58 10 -52 L 10 -41";
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      {relleno ? (
        <>
          <path d={`${cuerpo} Z`} fill={relleno} />
          <path d={`${cabeza} Z`} fill={relleno} />
        </>
      ) : null}
      <g {...linea(3 / s)} stroke={color} strokeDasharray={discontinua ? "5 6" : undefined}>
        <path d={cuerpo} />
        <path d={cabeza} />
      </g>
    </g>
  );
};

// --- Órganos ---

export const RINON = "M 10 -55 C 40 -55 46 -20 44 0 C 42 30 30 55 5 55 C -18 55 -14 30 -8 18 C -3 8 -3 -8 -8 -18 C -14 -30 -18 -55 10 -55 Z";
const RINON_BRILLO = "M 14 -46 C 34 -42 37 -18 36 0 C 35 18 30 32 22 40 C 26 20 26 -20 14 -46 Z";

export const Rinon: React.FC<{ x: number; y: number; s?: number; espejo?: boolean; color?: string; brillo?: string }> = ({
  x,
  y,
  s = 1,
  espejo,
  color = P.rinon,
  brillo = P.rinonClaro,
}) => (
  <g transform={`translate(${x} ${y}) scale(${(espejo ? -1 : 1) * s} ${s})`}>
    <path d={RINON} fill={color} />
    <path d={RINON_BRILLO} fill={brillo} />
    {[
      [18, -30],
      [28, -6],
      [24, 22],
      [10, 38],
    ].map(([cx, cy], i) => (
      <circle key={i} cx={cx} cy={cy} r={3.2} fill={P.tinta} opacity={0.35} />
    ))}
    <path d={RINON} {...linea(GROSOR / s)} />
  </g>
);

const CORAZON = "M -46 -18 C -62 14 -46 58 4 76 C 30 84 54 60 54 24 C 54 -6 36 -30 8 -34 C -14 -37 -34 -32 -46 -18 Z";
const CORAZON_BRILLO = "M -40 -14 C -50 10 -40 38 -14 52 C -26 30 -26 4 -12 -24 C -24 -27 -34 -24 -40 -14 Z";

export const Corazon: React.FC<{ x: number; y: number; s?: number; giro?: number }> = ({ x, y, s = 1, giro = 0 }) => (
  <g transform={`translate(${x} ${y}) rotate(${giro}) scale(${s})`}>
    {/* Vena cava y cayado de la aorta, como tubos con borde */}
    <path d="M -26 -26 L -30 -66" stroke={P.tinta} strokeWidth={20 / 1} strokeLinecap="round" fill="none" />
    <path d="M -26 -26 L -30 -66" stroke={P.oliva} strokeWidth={11} strokeLinecap="round" fill="none" />
    <path d="M -2 -30 C -6 -64 24 -80 42 -66 C 52 -58 52 -46 48 -36" stroke={P.tinta} strokeWidth={22} strokeLinecap="round" fill="none" />
    <path d="M -2 -30 C -6 -64 24 -80 42 -66 C 52 -58 52 -46 48 -36" stroke={P.terracota} strokeWidth={13} strokeLinecap="round" fill="none" />
    <path d={CORAZON} fill={P.terracota} />
    <path d={CORAZON_BRILLO} fill={P.terracotaClaro} opacity={0.8} />
    <g {...linea(GROSOR / s)}>
      <path d={CORAZON} />
      <path d="M 6 -30 C 18 0 22 38 12 70" strokeWidth={2.6 / s} />
    </g>
  </g>
);

// --- Silueta con los órganos (de frente, cortada a la altura de los muslos) ---

const CABEZA_FRENTE = "M 228 214 L 228 118 C 228 70 260 40 300 40 C 340 40 372 70 372 118 L 372 214";
const CUERPO_FRENTE = "M 80 1010 L 80 370 C 80 280 175 236 300 236 C 425 236 520 280 520 370 L 520 1010";
const PULMON = "M 272 330 C 222 318 172 360 170 450 C 168 520 192 566 240 566 C 262 566 274 546 274 512 Z";

/** Puntos donde salen las líneas de las etiquetas (en coordenadas locales). */
export const ANCLAS = { corazon: [372, 452], rinon: [404, 628], vejiga: [334, 878] } as const;

export const Anatomia: React.FC<{ x: number; y: number; s?: number; albumina?: boolean }> = ({ x, y, s = 1, albumina = true }) => {
  const gotasIzq = [
    [247, 702],
    [253, 742],
    [262, 790],
    [273, 830],
  ];
  const gotasDer = [
    [353, 692],
    [347, 742],
    [338, 790],
    [327, 830],
  ];
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      {/* Cuerpo */}
      <path d={`${CUERPO_FRENTE} Z`} fill={P.piel} />
      <path d={`${CABEZA_FRENTE} Z`} fill={P.piel} />

      {/* Pulmones, apenas insinuados */}
      <path d={PULMON} fill={P.salvia} opacity={0.75} />
      <path d={PULMON} fill={P.salvia} opacity={0.75} transform="translate(600 0) scale(-1 1)" />

      {/* Vasos grandes: aorta (roja) y cava (oliva), con sus ramas al riñón */}
      <g fill="none" strokeLinecap="round">
        <path d="M 290 470 L 290 836 M 290 612 L 246 622 M 290 610 L 356 616" stroke={P.oliva} strokeWidth={8} />
        <path d="M 314 470 L 314 826 M 314 640 L 244 644 M 314 630 L 360 630 M 314 826 Q 300 860 262 912 M 314 826 Q 330 860 352 912" stroke={P.terracota} strokeWidth={8} />
      </g>

      {/* Uréteres y vejiga */}
      <g fill="none" stroke={P.ocre} strokeWidth={6} strokeLinecap="round">
        <path d="M 244 668 C 250 740 262 800 282 860" />
        <path d="M 356 656 C 350 740 338 800 318 860" />
      </g>
      <path d="M 266 860 C 264 836 336 836 334 860 C 346 906 254 906 266 860 Z" fill={P.ocreClaro} />
      <path d="M 266 860 C 264 836 336 836 334 860 C 346 906 254 906 266 860 Z" {...linea(GROSOR * 0.8 / s)} />
      {albumina
        ? [...gotasIzq, ...gotasDer, [292, 874], [306, 866], [300, 884]].map(([cx, cy], i) => <circle key={i} cx={cx} cy={cy} r={5.5} fill={P.ocre} stroke={P.tinta} strokeWidth={1.6} />)
        : null}

      <Rinon x={232} y={640} espejo />
      <Rinon x={368} y={628} />
      <Corazon x={338} y={440} giro={-12} />

      {/* Contorno */}
      <g {...linea(GROSOR / s)}>
        <path d={CUERPO_FRENTE} />
        <path d={CABEZA_FRENTE} />
        <path d="M 262 140 Q 272 147 282 140 M 318 140 Q 328 147 338 140" />
        <path d="M 140 340 Q 132 560 142 812 M 460 340 Q 468 560 458 812" />
      </g>
    </g>
  );
};
