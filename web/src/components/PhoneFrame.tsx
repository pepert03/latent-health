import type { ReactNode } from 'react'

interface PhoneFrameProps {
  /** Nombre accesible del conjunto, p. ej. «Aplicación del paciente (maqueta)». */
  label: string
  /** Hora que enseña la barra de estado. */
  clock?: string
  children: ReactNode
}

/**
 * Marco de teléfono dibujado con CSS (ver .phone en index.css). El contenido va en un área
 * con scroll propio, así que lo de dentro se maqueta como una pantalla de móvil de ~368 px.
 */
export function PhoneFrame({ label, clock = '9:41', children }: PhoneFrameProps) {
  return (
    <div className="phone" role="group" aria-label={label}>
      <div className="phone__screen">
        <div className="phone__island" aria-hidden="true" />
        <div className="phone__status" aria-hidden="true">
          <span>{clock}</span>
          <svg width="46" height="12" viewBox="0 0 46 12" fill="currentColor">
            <rect x="0" y="7" width="3" height="5" rx="0.8" />
            <rect x="5" y="5" width="3" height="7" rx="0.8" />
            <rect x="10" y="2.5" width="3" height="9.5" rx="0.8" />
            <rect x="15" y="0" width="3" height="12" rx="0.8" />
            <rect x="24.5" y="0.5" width="19" height="11" rx="3" fill="none" stroke="currentColor" opacity="0.5" />
            <rect x="26" y="2" width="14" height="8" rx="1.6" />
          </svg>
        </div>
        <div className="phone__body">{children}</div>
        <div className="phone__home" aria-hidden="true" />
      </div>
    </div>
  )
}
