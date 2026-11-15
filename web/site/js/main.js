// Arranque de la portada: secciones que se cuentan con el scroll, el kit en 3D, contadores y la
// app interactiva.
import { $, $$, num } from './lib.js'
import { initApp } from './app.js'
import { SECA, tiraSVG } from './tira.js'
import { camSVG, loadPhoto } from './camara.js'

const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
const isStatic = document.documentElement.classList.contains('static')
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v))

// --- Secciones con scroll fijado: cada una sabe su avance (0-1) y su paso ----------------------
const scrollies = $$('.scrolly').map((section) => ({
  section,
  steps: Number(section.dataset.steps),
  items: $$('[data-i]', section),
  screens: $$('.scr', section),
  ticks: $$('.ticks i', section),
  step: -1,
  progress: 0,
  onProgress: null,
}))

function updateScrolly(s) {
  const rect = s.section.getBoundingClientRect()
  const travel = s.section.offsetHeight - innerHeight
  const p = travel > 0 ? clamp(-rect.top / travel) : 0
  s.progress = p
  s.section.style.setProperty('--p', p.toFixed(4))
  s.onProgress?.(p)
  const step = Math.min(s.steps - 1, Math.floor(p * s.steps))
  if (step === s.step) return
  s.step = step
  s.section.dataset.step = String(step)
  s.items.forEach((el) => el.classList.toggle('on', Number(el.dataset.i) === step))
  s.screens.forEach((el) => el.classList.toggle('on', Number(el.dataset.n) === step))
  s.ticks.forEach((el, i) => el.classList.toggle('on', i <= step))
}

let frame = 0
function onScroll() {
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    scrollies.forEach(updateScrolly)
    $('#nav').classList.toggle('solid', scrollY > 40)
  })
}
addEventListener('scroll', onScroll, { passive: true })
addEventListener('resize', onScroll)
onScroll()

// --- Aparece al entrar en pantalla ----------------------------------------------------------
function onView(el, fn, threshold = 0.3) {
  if (!el) return
  if (isStatic || reduced || !('IntersectionObserver' in window)) return fn(el)
  const observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) {
        fn(el)
        observer.disconnect()
      }
    },
    { threshold },
  )
  observer.observe(el)
}

// 100 puntos: 4 encendidos (los hipertensos a los que se les mira la orina).
const dots = $('#dots')
const lit = new Set([12, 38, 61, 87])
dots.innerHTML = Array.from({ length: 100 }, (_, i) => `<i class="${lit.has(i) ? 'on' : ''}" style="--i:${i}"></i>`).join('')
onView(dots, (el) => el.classList.add('in'))

// Contadores: de 0 al número, una vez.
function countUp(el) {
  const target = Number(el.dataset.count)
  if (reduced || isStatic) return (el.textContent = num(target))
  const t0 = performance.now()
  const tick = (now) => {
    const t = clamp((now - t0) / 1400)
    el.textContent = num(Math.round(target * (1 - Math.pow(1 - t, 3))))
    if (t < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}
$$('[data-count]').forEach((el) => onView(el, countUp, 0.6))

// --- La tira de la portada, la misma de toda la web (las almohadillas se colorean en bucle) -----
const heroStrip = $('#hero-tira')
if (heroStrip) heroStrip.innerHTML = tiraSVG({ ...SECA, id: 'hero-tira', title: 'Tira de orina de LatentHealth' })

// --- El visor de la cámara del escaparate: dibujado ya, y con la foto del render 3D si existe ----
const showCam = $('#show-cam')
if (showCam) {
  showCam.insertAdjacentHTML('afterbegin', camSVG({ id: 'show-cam' }))
  loadPhoto().then((ok) => {
    if (!ok) return
    showCam.querySelector('.cam-svg')?.remove()
    showCam.insertAdjacentHTML('afterbegin', camSVG({ id: 'show-cam' }))
  })
}

// --- El kit en 3D: se carga cuando la sección se acerca. Sin GPU (render por software) o si falla,
// se queda la imagen fija de cada paso.
const kitScrolly = scrollies.find((s) => s.section.id === 'kit')
const stage = $('#kit3d')
let kitLoading = false

function softwareGPU() {
  try {
    const gl = document.createElement('canvas').getContext('webgl2') ?? document.createElement('canvas').getContext('webgl')
    if (!gl) return true
    const info = gl.getExtension('WEBGL_debug_renderer_info')
    const name = info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : ''
    gl.getExtension('WEBGL_lose_context')?.loseContext()
    return /swiftshader|llvmpipe|softpipe|basic render|software/i.test(name)
  } catch {
    return true
  }
}

function loadKit() {
  if (kitLoading || !stage) return
  kitLoading = true
  if (new URLSearchParams(location.search).has('sin3d') || softwareGPU()) return
  import('./kit3d.js')
    .then(({ mountKit }) => mountKit(stage, { background: null }))
    .then((kit) => {
      if (!kit) return
      stage.classList.add('ready')
      kitScrolly.onProgress = (p) => kit.setProgress(p)
      kit.setProgress(kitScrolly.progress)
    })
    .catch((error) => console.warn('Kit 3D no disponible:', error))
}
if ('IntersectionObserver' in window) {
  const near = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      loadKit()
      near.disconnect()
    }
  }, { rootMargin: '600px 0px' })
  near.observe(kitScrolly.section)
} else loadKit()

// Tinta que se extiende (js/ink.js). En la portada, la mancha de siempre; en «Pruébala» y en el
// cierre, la tinta de la escala inunda la sección entera al entrar y se queda con su textura.
import('./ink.js')
  .then(({ createInk }) => {
    const hero = $('#ink-hero')
    if (hero) createInk(hero, { color: '#a9d3ca', opacity: 0.55, origin: [0.72, 0.45], seed: 3, mode: 'time', duration: 5200 }).play()
    for (const [id, origin] of [
      ['ink-try', [0.5, 0.3]],
      ['ink-closing', [0.5, 0.55]],
    ]) {
      const host = document.getElementById(id)
      if (!host) continue
      const ink = createInk(host, {
        colors: ['#5fbe8c', '#0b7774'],
        colorMode: 'zones',
        cover: true,
        flat: false,
        opacity: 0.5,
        origin,
        seed: id.length,
        mode: 'time',
        duration: 4600,
      })
      onView(host.parentElement, () => ink.play(), 0.15)
    }
  })
  .catch(() => {})

initApp()

// Panel del médico (js/medico.js).
import('./medico.js')
  .then((m) => m.initDoctor?.())
  .catch((error) => console.warn('Panel del médico no disponible:', error))

// ?ir=seccion:0.5 coloca la página en ese punto de la sección (para revisar capturas).
const ir = new URLSearchParams(location.search).get('ir')
if (ir) {
  const [id, frac = '0'] = ir.split(':')
  const target = document.getElementById(id)
  if (target) {
    const travel = Math.max(0, target.offsetHeight - innerHeight)
    document.documentElement.style.scrollBehavior = 'auto'
    scrollTo(0, target.offsetTop + Number(frac) * travel)
    onScroll()
  }
}

// ?auto=… ejecuta la prueba de humo de la app (js/autotest.js): recorre un caso entero sola.
if (new URLSearchParams(location.search).has('auto')) import('./autotest.js')
