import { useEffect, useState } from 'react'

export interface NavItem {
  id: string
  label: string
}

/** Sección que ocupa ahora la franja central de la pantalla, para marcarla en el menú. */
function useActiveSection(ids: string[]): string {
  const [active, setActive] = useState(ids[0] ?? '')
  const key = ids.join('|')

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id)
        }
      },
      { rootMargin: '-45% 0px -50% 0px' },
    )
    for (const id of key.split('|')) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [key])

  return active
}

/** Avance del scroll de 0 a 1, para la línea de progreso de la cabecera. */
function useScrollProgress(): number {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    let frame = 0
    const update = () => {
      frame = 0
      const max = document.documentElement.scrollHeight - window.innerHeight
      setProgress(max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0)
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [])

  return progress
}

export function TopBar({ items }: { items: NavItem[] }) {
  const active = useActiveSection(items.map((i) => i.id))
  const progress = useScrollProgress()

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-page/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6 sm:px-10">
        <a href="#inicio" className="flex items-center gap-2.5 font-display text-xl font-medium tracking-tight">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="8" className="fill-accent" />
            <path
              d="M5 17h5l2.5-7 4 13 3-9 1.5 3H27"
              fill="none"
              stroke="#fff"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          LatentHealth
        </a>
        <nav aria-label="Secciones" className="ml-auto hidden lg:block">
          <ul className="flex items-center gap-1 text-sm">
            {items.map((item) => (
              <li key={item.id}>
                <a
                  href={`#${item.id}`}
                  aria-current={active === item.id ? 'true' : undefined}
                  className={`rounded-full px-3 py-1.5 transition-colors ${
                    active === item.id
                      ? 'bg-ink font-semibold text-page'
                      : 'text-ink-2 hover:bg-sunken hover:text-ink'
                  }`}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-accent"
        style={{ transform: `scaleX(${progress})` }}
      />
    </header>
  )
}

/** Aviso permanente, siempre a la vista en el borde inferior. */
export function DisclaimerBar() {
  return (
    <div
      role="note"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 px-4 py-1.5 text-center text-sm text-ink-2 backdrop-blur-sm"
    >
      <strong className="font-semibold text-ink">Datos sintéticos</strong> · Prototipo de apoyo a la decisión, no
      diagnostica · Modelos entrenados con NHANES (EE. UU.)
    </div>
  )
}
