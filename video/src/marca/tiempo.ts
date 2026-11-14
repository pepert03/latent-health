import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

const suave = Easing.bezier(0.16, 1, 0.3, 1);

/** Avance de 0 a 1 entre dos instantes (en segundos) de la escena. */
export const useAvance = (desde: number, hasta: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return interpolate(frame, [desde * fps, hasta * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: suave,
  });
};

/** Para gráficos fuera de Remotion: el mismo avance a partir de un valor 0-1 (scroll, hover...). */
export const tramo = (t: number, desde: number, hasta: number) =>
  suave(Math.min(1, Math.max(0, (t - desde) / (hasta - desde))));
