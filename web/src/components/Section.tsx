import type { ReactNode } from 'react'
import { Reveal } from './Reveal'

interface SectionProps {
  /** Ancla de la sección; debe coincidir con una entrada de SECTIONS en App.tsx. */
  id: string
  /** Rótulo corto sobre el título, p. ej. «01 · El problema». */
  eyebrow?: string
  title: ReactNode
  /** Una o dos frases bajo el título. */
  lead?: ReactNode
  /** `surface`: fondo blanco con filetes; `ink`: fondo oscuro para un cambio de acto. */
  tone?: 'page' | 'surface' | 'ink'
  children?: ReactNode
}

const TONES: Record<NonNullable<SectionProps['tone']>, string> = {
  page: '',
  surface: 'border-y border-line bg-surface',
  ink: 'bg-ink text-page',
}

/** Bloque de página con ancho, márgenes y cabecera comunes a todas las secciones. */
export function Section({ id, eyebrow, title, lead, tone = 'page', children }: SectionProps) {
  const ink = tone === 'ink'
  return (
    <section id={id} aria-labelledby={`${id}-titulo`} className={`px-6 py-24 sm:px-10 lg:py-32 ${TONES[tone]}`}>
      <div className="mx-auto max-w-6xl">
        <Reveal className="max-w-3xl">
          {eyebrow && (
            <p className={`mb-4 text-sm font-semibold tracking-[0.14em] uppercase ${ink ? 'text-accent-soft' : 'text-accent'}`}>
              {eyebrow}
            </p>
          )}
          <h2 id={`${id}-titulo`} className="text-4xl sm:text-5xl">
            {title}
          </h2>
          {lead && <p className={`mt-5 text-xl leading-relaxed ${ink ? 'text-page/80' : 'text-ink-2'}`}>{lead}</p>}
        </Reveal>
        {children && <div className="mt-14">{children}</div>}
      </div>
    </section>
  )
}
