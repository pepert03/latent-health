import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'

interface InViewOptions {
  /** Deja de observar tras la primera aparición (por defecto, sí). */
  once?: boolean
  rootMargin?: string
  threshold?: number
}

/**
 * Indica si el elemento ha entrado en pantalla. Sin IntersectionObserver (o con ?estatico=1)
 * devuelve siempre true: el contenido nunca depende de la animación para verse.
 */
export function useInView<T extends Element>(options: InViewOptions = {}) {
  const { once = true, rootMargin = '0px 0px -12% 0px', threshold = 0.12 } = options
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(
    () => typeof IntersectionObserver === 'undefined' || document.documentElement.hasAttribute('data-static'),
  )

  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    if (document.documentElement.hasAttribute('data-static')) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          if (once) observer.disconnect()
        } else if (!once) {
          setInView(false)
        }
      },
      { rootMargin, threshold },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [once, rootMargin, threshold])

  return [ref, inView] as const
}

interface RevealProps {
  children: ReactNode
  /** Retraso en ms, para escalonar elementos de un mismo bloque. */
  delay?: number
  className?: string
}

/** Envuelve un bloque para que aparezca (opacidad + desplazamiento corto) al llegar con el scroll. */
export function Reveal({ children, delay = 0, className = '' }: RevealProps) {
  const [ref, inView] = useInView<HTMLDivElement>()
  return (
    <div
      ref={ref}
      data-shown={inView}
      className={`reveal ${className}`}
      style={{ '--reveal-delay': `${delay}ms` } as CSSProperties}
    >
      {children}
    </div>
  )
}
