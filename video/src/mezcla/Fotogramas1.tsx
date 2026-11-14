/** Fotogramas 0 a 2 del guion: Julián, "96 de cada 100" y el cuerpo por dentro. */
import React from "react";
import { Anatomia, ANCLAS, MiniPersona, Persona, Rinon } from "./Personajes";
import { Cabecera, F, Fuente, Lienzo, Marca, P, Svg, linea } from "./sistema";

// --- Iconos pequeños de línea (48 × 48) ---

const Icono: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <svg width={52} height={52} viewBox="0 0 48 48" style={{ flex: "none" }}>
    <g {...linea(3)}>{children}</g>
  </svg>
);

const IconoPulso = () => (
  <Icono>
    <path d="M 2 26 L 12 26 L 17 12 L 25 40 L 31 18 L 35 26 L 46 26" />
  </Icono>
);
const IconoPastilla = () => (
  <Icono>
    <g transform="rotate(-35 24 24)">
      <path d="M 14 16 L 24 16 L 24 32 L 14 32 C 3 32 3 16 14 16 Z" fill={P.olivaClaro} />
      <rect x={6} y={16} width={36} height={16} rx={8} />
      <line x1={24} y1={16} x2={24} y2={32} />
    </g>
  </Icono>
);
const IconoCalendario = () => (
  <Icono>
    <rect x={6} y={10} width={36} height={32} rx={5} />
    <line x1={6} y1={19} x2={42} y2={19} />
    <line x1={15} y1={5} x2={15} y2={13} />
    <line x1={33} y1={5} x2={33} y2={13} />
    <circle cx={24} cy={30} r={2.5} fill={P.tinta} />
  </Icono>
);

const Fila: React.FC<{ icono: React.ReactNode; children: React.ReactNode }> = ({ icono, children }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 22, fontFamily: F.sans, fontSize: 32, color: P.tinta2, marginBottom: 22 }}>
    {icono}
    {children}
  </div>
);

/** 0 · Gancho: Julián se encuentra bien, y algo le pasa dentro que nadie ha mirado. */
export const M0Julian: React.FC = () => (
  <Lienzo>
    <Svg>
      <ellipse cx={560} cy={884} rx={170} ry={14} fill={P.tinta} opacity={0.07} />
      <g filter="url(#trazo)">
        <path d="M 210 880 L 520 880 M 552 880 L 930 880" {...linea()} />
        <Persona
          x={560}
          y={880}
          s={1.35}
          gafas
          dentro={
            <g>
              <circle cx={40} cy={-168} r={52} fill={P.ocre} opacity={0.6} filter="url(#halo)" />
              <Rinon x={40} y={-168} s={0.44} color={P.ocre} brillo={P.ocreClaro} />
            </g>
          }
        />
      </g>
    </Svg>
    <Cabecera x={1040} y={180} ancho={760} etiqueta="Personaje inventado" titulo="Julián tiene 62 años y se encuentra bien." tam={88} />
    <div style={{ position: "absolute", left: 1040, top: 560, width: 760 }}>
      <Fila icono={<IconoPulso />}>Tensión alta desde hace años.</Fila>
      <Fila icono={<IconoPastilla />}>Se toma su pastilla.</Fila>
      <Fila icono={<IconoCalendario />}>Va a su médica una vez al año.</Fila>
    </div>
    <div style={{ position: "absolute", left: 1040, top: 820, width: 800, fontFamily: F.serif, fontStyle: "italic", fontWeight: 300, fontSize: 58, color: P.tinta }}>
      Nadie le ha mirado nunca la <Marca>orina</Marca>.
    </div>
  </Lienzo>
);

/** 0 · Gancho: 96 de cada 100 hipertensos nunca se hacen la prueba de orina. */
export const M0Cien: React.FC = () => {
  const vistos = new Set([7, 33, 58, 81]);
  const x0 = 960;
  const y0 = 150;
  return (
    <Lienzo>
      <div style={{ position: "absolute", left: 104, top: 96, fontFamily: F.serif, fontWeight: 300, fontSize: 420, lineHeight: 0.9, letterSpacing: -14, color: P.tinta }}>96</div>
      <div style={{ position: "absolute", left: 120, top: 520, width: 700, fontFamily: F.serif, fontWeight: 400, fontSize: 62, lineHeight: 1.12, color: P.tinta }}>
        de cada 100 hipertensos <i>nunca</i> se hacen la prueba de <Marca>orina</Marca>.
      </div>
      <Svg>
        <g filter="url(#trazo)">
          {Array.from({ length: 100 }, (_, i) => {
            const c = i % 10;
            const f = Math.floor(i / 10);
            const visto = vistos.has(i);
            return <MiniPersona key={i} x={x0 + c * 84} y={y0 + f * 74 + 62} relleno={visto ? P.oliva : undefined} discontinua={!visto} color={visto ? P.tinta : P.mudo} />;
          })}
          <MiniPersona x={x0 + 20} y={960} s={0.62} relleno={P.oliva} />
          <MiniPersona x={x0 + 330} y={960} s={0.62} discontinua color={P.mudo} />
        </g>
      </Svg>
      <div style={{ position: "absolute", left: x0 + 48, top: 920, fontSize: 26, color: P.tinta2 }}>se la miran (4)</div>
      <div style={{ position: "absolute", left: x0 + 358, top: 920, fontSize: 26, color: P.tinta2 }}>nunca (96)</div>
      <Fuente>Shin et al., Hypertension 2021 · metaanálisis de atención primaria</Fuente>
    </Lienzo>
  );
};

const Etiqueta: React.FC<{ ancla: readonly [number, number]; y: number; titulo: string; texto: string; color?: string }> = ({ ancla, y, titulo, texto, color = P.tinta }) => (
  <>
    <circle cx={ancla[0]} cy={ancla[1]} r={7} fill={P.tinta} />
    <path d={`M ${ancla[0]} ${ancla[1]} L ${ancla[0] + 30} ${y} L 770 ${y}`} {...linea(2.4)} />
    <text x={790} y={y + 8} fontFamily={F.sans} fontWeight={600} fontSize={30} fill={color}>
      {titulo}
    </text>
    <text x={790} y={y + 44} fontFamily={F.sans} fontSize={23} fill={P.tinta2}>
      {texto}
    </text>
  </>
);

/** 1 · Por qué importa: el mismo daño en los vasos llega al riñón y al corazón. */
export const M1Cuerpo: React.FC = () => {
  const ox = 110;
  const oy = 70;
  const a = (p: readonly [number, number]) => [ox + p[0], oy + p[1]] as const;
  return (
    <Lienzo>
      <Svg>
        <g filter="url(#trazo)">
          <Anatomia x={ox} y={oy} />
        </g>
        <Etiqueta ancla={a(ANCLAS.corazon)} y={500} titulo="Corazón" texto="bombea la sangre" />
        <Etiqueta ancla={a(ANCLAS.rinon)} y={690} titulo="Riñones" texto="la filtran" />
        <Etiqueta ancla={a(ANCLAS.vejiga)} y={930} titulo="Albúmina" texto="se escapa a la orina" color={P.ocreOscuro} />
      </Svg>
      <Cabecera
        x={1180}
        y={120}
        ancho={640}
        etiqueta="1 · Por qué importa"
        titulo="Un mismo daño."
        tam={104}
        texto="Diabetes, hipertensión, riñón y corazón no son cuatro problemas: son uno. El azúcar y la tensión alta dañan los vasos pequeños; el riñón deja escapar albúmina, y el mismo daño llega al corazón."
      />
      <div style={{ position: "absolute", left: 1180, top: 760, width: 640 }}>
        <div style={{ fontFamily: F.serif, fontWeight: 300, fontSize: 112, lineHeight: 1, color: P.terracota, letterSpacing: -3 }}>113.620</div>
        <div style={{ fontSize: 26, lineHeight: 1.4, color: P.tinta2, marginTop: 10 }}>muertes al año en España por enfermedades del corazón y los vasos</div>
      </div>
      <Fuente x={1180}>INE, defunciones según la causa de muerte, 2024</Fuente>
    </Lienzo>
  );
};
