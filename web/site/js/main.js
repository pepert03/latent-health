// Arranque de la página: apariciones con el scroll, menú, animaciones de la tira y del kit,
// y los dos bloques que hablan con el modelo.
import { $, $$ } from './lib.js'
import { initLab } from './model.js'
import { initApp } from './app.js'

const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
const isStatic = document.documentElement.classList.contains('static')

// --- Aparición de los bloques al llegar con el scroll ---------------------------------------
function reveal() {
  const items = $$('.rv')
  if (isStatic || reduced || !('IntersectionObserver' in window)) {
    items.forEach((el) => el.classList.add('in'))
    return
  }
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in')
          observer.unobserve(entry.target)
        }
      }
    },
    { rootMargin: '0px 0px -10% 0px', threshold: 0.08 },
  )
  items.forEach((el) => observer.observe(el))
}

// --- Animaciones que se disparan al entrar en pantalla (y se pueden repetir) ----------------
function playOnView(el, replayButton) {
  if (!el) return
  const play = () => {
    el.classList.remove('play')
    void el.getBoundingClientRect()
    el.classList.add('play')
  }
  if (isStatic || reduced) return
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          play()
          observer.disconnect()
        }
      },
      { threshold: 0.35 },
    )
    observer.observe(el)
  } else play()
  replayButton?.addEventListener('click', play)
}

// --- Menú: sección activa y barra de progreso ------------------------------------------------
function navigation() {
  const links = $$('.nav a')
  const byId = new Map(links.map((a) => [a.getAttribute('href').slice(1), a]))
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          links.forEach((a) => a.removeAttribute('aria-current'))
          byId.get(entry.target.id)?.setAttribute('aria-current', 'true')
        }
      },
      { rootMargin: '-45% 0px -50% 0px' },
    )
    byId.forEach((_, id) => {
      const section = document.getElementById(id)
      if (section) observer.observe(section)
    })
  }
  const bar = $('#progress')
  let frame = 0
  const update = () => {
    frame = 0
    const max = document.documentElement.scrollHeight - innerHeight
    bar.style.transform = `scaleX(${max > 0 ? Math.min(1, scrollY / max) : 0})`
  }
  const onScroll = () => {
    if (!frame) frame = requestAnimationFrame(update)
  }
  addEventListener('scroll', onScroll, { passive: true })
  addEventListener('resize', onScroll)
  update()
}

// 25 casillas con una marcada: el 4 % de los hipertensos.
$('#pads-25').innerHTML = Array.from({ length: 25 }, (_, i) => `<i${i === 0 ? ' class="on"' : ''}></i>`).join('')

reveal()
navigation()
playOnView($('#reader'))
playOnView($('#kit'), $('#kit-replay'))
initLab()
initApp()

// ?auto=… ejecuta la prueba de humo de la app (js/autotest.js): recorre un caso entero sola.
if (new URLSearchParams(location.search).has('auto')) import('./autotest.js')
