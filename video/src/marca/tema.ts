import { loadFont } from "@remotion/google-fonts/Inter";

// Una sola familia en todo (vídeo y web). Los números grandes, en peso alto.
export const { fontFamily } = loadFont("normal", {
  weights: ["400", "500", "600", "700", "800"],
  subsets: ["latin", "latin-ext"],
});

// Colores por papel, no por gusto: marca = LatentHealth; gris = lo que se hace hoy; ámbar = lo
// que está oculto o en riesgo. Los gráficos comparan "hoy" (gris) con "nosotros" (marca), con
// etiquetas directas: la identidad nunca va solo en el color.
export const C = {
  fondo: "#FBFAF7",
  fondoOscuro: "#0E1A2B",
  tarjeta: "#FFFFFF",
  tinta: "#0E1A2B",
  tinta2: "#4A5363",
  mudo: "#8A8F98",
  linea: "#E6E3DC",
  marca: "#0F8F7E",
  marcaOscuro: "#0B6B5F",
  marcaClaro: "#DDF2EE",
  ambar: "#E39B00",
  ambarClaro: "#FCEFD2",
  rojo: "#D64545",
  hoy: "#BDB9AF",
  hoyOscuro: "#7D796F",
} as const;

export const ANCHO = 1920;
export const ALTO = 1080;
export const FPS = 30;

const fmt = new Intl.NumberFormat("es-ES", { useGrouping: "always" } as unknown as Intl.NumberFormatOptions);
export const numero = (v: number, decimales = 0) =>
  decimales ? v.toFixed(decimales).replace(".", ",") : fmt.format(Math.round(v));
