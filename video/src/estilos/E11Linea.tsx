/** Estilo 11, una sola línea: el cierre. Julián, diez años después, con su nieta. */
import React from "react";
import { AbsoluteFill } from "remotion";
import { F } from "./comun";

const TINTA = "#1a1a1a";

export const E11Linea: React.FC = () => (
  <AbsoluteFill style={{ background: "#efede6" }}>
    <svg width={1920} height={1080} style={{ position: "absolute" }}>
      <defs>
        {/* Temblor de trazo a mano */}
        <filter id="pulso">
          <feTurbulence type="fractalNoise" baseFrequency={0.035} numOctaves={2} seed={4} />
          <feDisplacementMap in="SourceGraphic" scale={4} />
        </filter>
      </defs>
      <g fill="none" stroke={TINTA} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round" filter="url(#pulso)">
        {/* Suelo, con huecos */}
        <path d="M 560 760 L 900 760 M 930 760 L 1240 760 M 1270 760 L 1360 760" />
        {/* Sol */}
        <circle cx={1270} cy={360} r={44} />

        {/* Julián: cabeza en arco con nariz, cuerpo en bloque, brazo que baja a la mano de la niña */}
        <path d="M 770 480 L 770 432 A 34 34 0 0 1 838 432 L 838 446 L 852 460 L 838 466 L 838 480" />
        <path d="M 796 448 Q 806 454 816 448" />
        <path d="M 720 760 L 720 560 A 84 66 0 0 1 888 560 L 888 640" />
        <path d="M 804 600 L 804 760" />
        <path d="M 888 640 L 888 690 L 950 690" />
        <path d="M 760 760 L 760 700" />
        <path d="M 724 600 L 700 690" />

        {/* Nieta: más pequeña, mano levantada que coge la de Julián */}
        <path d="M 990 600 L 990 572 A 26 26 0 0 1 1042 572 L 1042 584 L 1052 594 L 1042 598 L 1042 610" />
        <path d="M 1006 586 Q 1014 591 1022 586" />
        <path d="M 966 760 L 966 670 A 50 44 0 0 1 1066 670 L 1066 760" />
        <path d="M 966 690 L 950 690" />
        <path d="M 1016 704 L 1016 760" />
        <path d="M 1066 690 L 1096 640" />
        {/* Corazón diminuto entre los dos */}
        <path d="M 920 640 C 912 628 898 634 904 646 L 920 662 L 936 646 C 942 634 928 628 920 640 Z" />
      </g>
    </svg>
    <div style={{ position: "absolute", left: 0, right: 0, top: 820, textAlign: "center", fontFamily: F.serif, fontSize: 76, color: TINTA }}>
      Dentro de diez años, Julián seguirá aquí.
    </div>
    <div style={{ position: "absolute", left: 0, right: 0, top: 930, textAlign: "center", fontFamily: F.sans, fontSize: 26, color: "#6a675f" }}>
      ≈ 1.200 muertes evitadas al año en España · estimación con supuestos
    </div>
    <div style={{ position: "absolute", left: 0, right: 0, top: 150, textAlign: "center", fontFamily: F.serifItalica, fontSize: 40, color: "#6a675f" }}>
      No habrá un día en que le salvemos la vida.
    </div>
  </AbsoluteFill>
);
