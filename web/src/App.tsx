import { DisclaimerBar, TopBar } from './components/Layout'
import type { NavItem } from './components/Layout'
import { Section } from './components/Section'

/** Orden de la página. Cada id es el ancla de una sección de src/sections/. */
const SECTIONS: NavItem[] = [
  { id: 'problema', label: 'El problema' },
  { id: 'pruebas', label: 'Las pruebas' },
  { id: 'modelo', label: 'El modelo' },
  { id: 'app', label: 'La app' },
  { id: 'referencias', label: 'Referencias' },
]

export default function App() {
  return (
    <>
      <TopBar items={SECTIONS} />
      <main id="inicio" className="pb-12">
        <Section
          id="problema"
          eyebrow="En construcción"
          title="Detección precoz cardio-renal-metabólica, medida en casa"
          lead="Estructura del sitio lista. Las secciones se añaden en los siguientes commits."
        />
      </main>
      <DisclaimerBar />
    </>
  )
}
