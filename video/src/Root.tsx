import { Folder, Still } from "remotion";
import { E1PlanoVectorial } from "./estilos/E1PlanoVectorial";
import { E3Collage } from "./estilos/E3Collage";
import { E6Isometrico } from "./estilos/E6Isometrico";
import { E9Grano } from "./estilos/E9Grano";
import { E11Linea } from "./estilos/E11Linea";
import { M0Cien, M0Julian, M1Cuerpo } from "./mezcla/Fotogramas1";
import { M3Fallos, M5App, M5Kit } from "./mezcla/Fotogramas2";
import { M6Medica, M7Diabetes, M8Cierre } from "./mezcla/Fotogramas3";

const still = { width: 1920, height: 1080 };

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Folder name="Mezcla">
        <Still id="M0-Julian" component={M0Julian} {...still} />
        <Still id="M0-Cien" component={M0Cien} {...still} />
        <Still id="M1-Cuerpo" component={M1Cuerpo} {...still} />
        <Still id="M3-Fallos" component={M3Fallos} {...still} />
        <Still id="M5-App" component={M5App} {...still} />
        <Still id="M5-Kit" component={M5Kit} {...still} />
        <Still id="M6-Medica" component={M6Medica} {...still} />
        <Still id="M7-Diabetes" component={M7Diabetes} {...still} />
        <Still id="M8-Cierre" component={M8Cierre} {...still} />
      </Folder>
      <Folder name="Estilos">
        <Still id="E1-PlanoVectorial" component={E1PlanoVectorial} {...still} />
        <Still id="E3-Collage" component={E3Collage} {...still} />
        <Still id="E6-Isometrico" component={E6Isometrico} {...still} />
        <Still id="E9-Grano" component={E9Grano} {...still} />
        <Still id="E11-Linea" component={E11Linea} {...still} />
      </Folder>
    </>
  );
};
