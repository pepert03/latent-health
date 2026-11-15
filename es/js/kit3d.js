/*
  LatentHealth · el kit en 3D (three.js r170, sin paso de compilación).

  import { mountKit } from './js/kit3d.js'
  const kit = await mountKit(document.querySelector('#kit3d'), { progress: 0 })
  kit.setProgress(p)   // p de 0 a 1: el avance de la sección, cuatro pasos de 0,25
  kit.destroy()

    0     – 0,25   la caja cerrada, plano de producto (gira despacio)
    0,25  – 0,44   se abre la solapa y sale el contenido: los sobres en abanico, el vaso que se
                   despliega, la plantilla de color y los tubos; reposo hasta 0,515
    0,515 – 0,708  se rasga un sobre; la tira pasa por el vaso, cambia de color y queda en la
                   plantilla; reposo hasta 0,75
    0,75  – 0,93   el kit se aparta y entran el reloj y el tensiómetro; reposo hasta 1

  KIT_PASOS da el punto de reposo de cada paso (el de las imágenes fijas img/kit-0…3.webp).
  Opciones: progress (0), background (null = transparente), parallax (true), smoothing (s, 0,14),
  maxPixelRatio (2), fade (0,05: fracción de cada borde del lienzo que se funde con la página).
  Además de setProgress/progress/destroy: ready (promesa: ya está todo, también lo que se carga en un
  rato libre), snapshot() (PNG del fotograma) y timings (ms de cada fase del montaje).

  La tira y la plantilla salen de los mismos SVG y medidas que el resto de la web (tira.js y
  plantilla.js); los demás impresos se pintan aquí en canvas. Solo se renderiza cuando cambia algo y se
  pausa fuera de pantalla. Si no hay WebGL, la promesa se rechaza y la página se queda con sus imágenes.
*/
import * as THREE from '../vendor/three/build/three.module.min.js'
import { RoomEnvironment } from '../vendor/three/examples/jsm/environments/RoomEnvironment.js'
import { RoundedBoxGeometry } from '../vendor/three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { HorizontalBlurShader } from '../vendor/three/examples/jsm/shaders/HorizontalBlurShader.js'
import { VerticalBlurShader } from '../vendor/three/examples/jsm/shaders/VerticalBlurShader.js'
import { BARS, INK, CAP, LOGO_W, logoSVG } from './marca.js'
import { TIRA, SECA, DEMO, tiraSVG, tiraMarkup } from './tira.js'
import { PLANTILLA, plantillaSVG } from './plantilla.js'

export const KIT_PASOS = [0.2, 0.475, 0.735, 0.97]

// ─── Paleta ─────────────────────────────────────────────────────────────────────────────────
const C = {
  ink: INK,
  ink2: '#44575a',
  ink3: '#6f7f81',
  teal: '#0b7774',
  green: '#5fbe8c',
  line: '#c9d3cf',
  board: '#fbfbf9',
}

// ─── Utilidades ─────────────────────────────────────────────────────────────────────────────
const DEG = Math.PI / 180
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x))
const seg = (p, a, b) => clamp((p - a) / (b - a))
const smooth = (t) => t * t * (3 - 2 * t)
const sstep = (a, b, x) => smooth(clamp((x - a) / (b - a)))
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const easeOut = (t) => 1 - Math.pow(1 - t, 3)
const easeOutBack = (t) => 1 + 2.2 * Math.pow(t - 1, 3) + 1.2 * Math.pow(t - 1, 2)
const lerp = (a, b, t) => a + (b - a) * t

export function rng(seed) {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Ruido de valor periódico (las texturas encajan al repetirse). */
export function valueNoise(rand, period) {
  const g = new Float32Array(period * period)
  for (let i = 0; i < g.length; i++) g[i] = rand()
  return (x, y) => {
    const xi = Math.floor(x)
    const yi = Math.floor(y)
    const xf = x - xi
    const yf = y - yi
    const x0 = ((xi % period) + period) % period
    const y0 = ((yi % period) + period) % period
    const x1 = (x0 + 1) % period
    const y1 = (y0 + 1) % period
    const u = xf * xf * (3 - 2 * xf)
    const v = yf * yf * (3 - 2 * yf)
    const a = g[y0 * period + x0]
    const b = g[y0 * period + x1]
    const c = g[y1 * period + x0]
    const d = g[y1 * period + x1]
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
  }
}

// ─── Fuentes y canvas ───────────────────────────────────────────────────────────────────────
const SANS = '"LH Archivo", Archivo, "Arial Nova", "Segoe UI", Arial, sans-serif'
const MONO = '"LH Chivo Mono", "Chivo Mono", Consolas, "Courier New", monospace'
const fontURL = (file) => new URL(`../fonts/${file}`, import.meta.url)
let fontsReady = null

export function loadKitFonts() {
  if (!fontsReady) {
    const src = (file) => `url("${fontURL(file)}") format("woff2")`
    const faces = [
      new FontFace('LH Archivo', src('archivo-latin-wdth-normal.woff2'), { weight: '100 900', stretch: '62% 125%' }),
      new FontFace('LH Chivo Mono', src('chivo-mono-latin-wght-normal.woff2'), { weight: '100 900' }),
    ]
    fontsReady = Promise.all(faces.map((f) => f.load().then((ok) => document.fonts.add(ok)).catch(() => null)))
  }
  return fontsReady
}

export function setFont(ctx, size, { weight = 400, mono = false, stretch = 'normal', spacing = 0 } = {}) {
  ctx.font = `${weight} ${size.toFixed(2)}px ${mono ? MONO : SANS}`
  if ('fontStretch' in ctx) ctx.fontStretch = mono ? 'normal' : stretch
  if ('letterSpacing' in ctx) ctx.letterSpacing = `${spacing.toFixed(2)}px`
}

export function makeCanvas(w, h) {
  const c = document.createElement('canvas')
  c.width = Math.max(2, Math.round(w))
  c.height = Math.max(2, Math.round(h))
  return c
}

function text(ctx, str, x, y, size, o = {}) {
  setFont(ctx, size, o)
  ctx.fillStyle = o.color || C.ink
  ctx.textAlign = o.align || 'left'
  ctx.textBaseline = 'alphabetic'
  ctx.fillText(str, x, y)
  const w = ctx.measureText(str).width
  ctx.textAlign = 'left'
  if ('letterSpacing' in ctx) ctx.letterSpacing = '0px'
  return w
}

function rrect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

// El logotipo, sacado de marca.js y pintado como trazado (nítido a cualquier tamaño).
let logoCache = null
function logoParts() {
  if (logoCache) return logoCache
  const svg = logoSVG({ height: CAP, title: '' })
  const bars = [...svg.matchAll(/<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="([\d.]+)"/g)].map((m) =>
    m.slice(1, 6).map(Number),
  )
  const w = /<path transform="translate\(([-\d.]+) ([-\d.]+)\)" d="([^"]+)"/.exec(svg)
  logoCache = { bars, word: w ? { x: +w[1], y: +w[2], path: new Path2D(w[3]) } : null }
  return logoCache
}

/** Logotipo con la línea base en (x, y) y alto de mayúscula `cap` px. Devuelve el ancho. */
function drawLogo(ctx, x, y, cap, { word = true, ink = INK, bars = BARS } = {}) {
  const L = logoParts()
  const s = cap / CAP
  ctx.save()
  ctx.translate(x, y)
  ctx.scale(s, s)
  L.bars.forEach(([bx, by, bw, bh, r], i) => {
    ctx.fillStyle = bars[i % bars.length]
    rrect(ctx, bx, by, bw, bh, r)
    ctx.fill()
  })
  if (word && L.word) {
    ctx.translate(L.word.x, L.word.y)
    ctx.fillStyle = ink
    ctx.fill(L.word.path)
  }
  ctx.restore()
  return (word ? LOGO_W : 170.5) * s
}

// ─── De SVG a canvas (la tira y la plantilla, idénticas a las del resto de la web) ─────────────
function sizedSVG(svg, w, h) {
  const i = svg.indexOf('>')
  const head = svg.slice(0, i).replace(/\s(width|height|preserveAspectRatio)="[^"]*"/g, '')
  return `${head} width="${w}" height="${h}" preserveAspectRatio="none"${svg.slice(i)}`
}

export async function svgCanvas(svg, w, h, fill = null) {
  const img = new Image()
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(sizedSVG(svg, w, h))
  await img.decode()
  const c = makeCanvas(w, h)
  const ctx = c.getContext('2d')
  if (fill) {
    ctx.fillStyle = fill
    ctx.fillRect(0, 0, c.width, c.height)
  }
  ctx.drawImage(img, 0, 0, c.width, c.height)
  return c
}

// Un SVG pintado como imagen no ve las fuentes de la página: se le incrusta Archivo en base64.
let archivoCSS = null
function archivoFace() {
  archivoCSS ??= fetch(fontURL('archivo-latin-wdth-normal.woff2'))
    .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(String(r.status)))))
    .then((buf) => {
      const bytes = new Uint8Array(buf)
      let bin = ''
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
      return `@font-face{font-family:Archivo;font-weight:100 900;font-stretch:62% 125%;src:url(data:font/woff2;base64,${btoa(bin)}) format("woff2")}`
    })
    .catch(() => '')
  return archivoCSS
}

/** La tira de tira.js en canvas, a `px` de largo (alto en proporción). colors: { a, c }. */
export async function stripCanvas(colors = SECA, px = 2048) {
  return svgCanvas(tiraSVG({ a: colors.a, c: colors.c, id: 'k' }), px, Math.round((px * TIRA.h) / TIRA.w), '#eef1ef')
}

/** La plantilla vacía de plantilla.js en canvas; clean: true quita «Pon aquí la tira», como cuando está puesta. */
export async function templateCanvas(px = 768, { clean = false } = {}) {
  const css = await archivoFace()
  let svg = plantillaSVG({ id: 'kpl' })
  if (css) svg = svg.replace('<defs>', `<defs><style>${css}</style>`)
  if (clean) svg = svg.replace(/<text[^>]*>Pon aquí la tira<\/text>/, '')
  return svgCanvas(svg, px, Math.round((px * PLANTILLA.h) / PLANTILLA.w), '#ffffff')
}

// ─── Material con dos texturas que se funden (las almohadillas que cambian de color) ─────────
function crossfadeMaterial(params, mapA, mapB) {
  const m = new THREE.MeshStandardMaterial({ ...params, map: mapA })
  const mix = { value: 0 }
  const map2 = { value: mapB }
  m.userData.mix = mix
  m.userData.map2 = map2
  m.onBeforeCompile = (sh) => {
    sh.uniforms.mixT = mix
    sh.uniforms.map2 = map2
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <map_pars_fragment>', '#include <map_pars_fragment>\nuniform sampler2D map2;\nuniform float mixT;')
      .replace(
        '#include <map_fragment>',
        '#ifdef USE_MAP\n  diffuseColor *= mix(texture2D(map, vMapUv), texture2D(map2, vMapUv), mixT);\n#endif',
      )
  }
  m.customProgramCacheKey = () => 'lh-crossfade'
  return m
}

// ─── La tira en 3D (también la usa tira-foto.js) ──────────────────────────────────────────────
// Unidades del mundo: centímetros. La tira: 8 × 0,5 cm, el mango en x = 0 y la punta en x = 8; la cara
// impresa hacia +y y el borde de arriba del SVG hacia -z (a la izquierda con la tira de pie, punta arriba).
export const STRIP = { l: TIRA.w / 100, w: TIRA.h / 100, t: 0.035, pad: 0.045 }

function stripUV(geo, onlyTop) {
  const pos = geo.attributes.position
  const nor = geo.attributes.normal
  const uv = geo.attributes.uv
  for (let i = 0; i < pos.count; i++) {
    if (onlyTop && nor.getY(i) < 0.5) uv.setXY(i, 0.5, 0.5)
    else uv.setXY(i, clamp(pos.getX(i) / STRIP.l), clamp((STRIP.w / 2 - pos.getZ(i)) / STRIP.w))
  }
  uv.needsUpdate = true
}

/**
 * Rectángulo de cada almohadilla en unidades de tira.js: [x0, y0, x1, y1]. Se lee del propio dibujo
 * (tiraMarkup) para que coincida siempre con el SVG; si no se encuentra, cuadrada y centrada.
 */
export function padRect(key) {
  const [x0, x1] = TIRA.pads[key]
  const m = new RegExp(`<rect[^>]*class="tp-${key}"[^>]*\\sy="([\\d.]+)"[^>]*\\sheight="([\\d.]+)"`).exec(tiraMarkup({ id: 'm' }))
  const s = x1 - x0
  const y0 = m ? +m[1] : (TIRA.h - s) / 2
  const h = m ? +m[2] : s
  return [x0, y0, x1, y0 + h]
}

/** De unidades de tira.js (décimas de mm, mango a la izquierda) a coordenadas locales de la tira. */
export function stripLocal(sx, sy, y = STRIP.t) {
  return new THREE.Vector3(sx / 100, y, sy / 100 - STRIP.w / 2)
}

/**
 * La tira: plástico con la impresión de tira.js y las dos almohadillas en relieve.
 * maps: { seca, demo } texturas de la tira entera; group.userData.develop.value funde de una a otra.
 */
export function buildStrip(maps, { padRoughness = 0.88 } = {}) {
  const g = new THREE.Group()
  const { l, w, t, pad } = STRIP
  const body = new THREE.BoxGeometry(l, t, w).translate(l / 2, t / 2, 0)
  stripUV(body, true)
  const bm = new THREE.Mesh(body, new THREE.MeshStandardMaterial({ map: maps.seca, roughness: 0.4 }))
  bm.castShadow = true
  bm.receiveShadow = true
  g.add(bm)
  const mPad = crossfadeMaterial({ roughness: padRoughness }, maps.seca, maps.demo || maps.seca)
  for (const key of ['a', 'c']) {
    const [x0, y0, x1, y1] = padRect(key).map((v) => v / 100)
    const geo = new RoundedBoxGeometry(x1 - x0, pad, y1 - y0, 1, 0.015).translate((x0 + x1) / 2, t + pad / 2, (y0 + y1) / 2 - w / 2)
    stripUV(geo, false)
    const m = new THREE.Mesh(geo, mPad)
    m.castShadow = true
    m.receiveShadow = true
    g.add(m)
  }
  g.userData.develop = mPad.userData.mix
  g.userData.setDemo = (t) => (mPad.userData.map2.value = t)
  return g
}

// La plantilla: medidas de plantilla.js (6 × 12 cm), 0,4 mm de grueso, apoyada en y = 0 con la cara
// impresa hacia arriba y el logotipo (arriba del SVG) hacia -z.
export const TPL = { w: PLANTILLA.w / 100, h: PLANTILLA.h / 100, t: 0.04 }

/** De unidades de plantilla.js (décimas de mm, origen arriba a la izquierda) a coordenadas locales. */
export function tplLocal(tx, ty, y = TPL.t) {
  return new THREE.Vector3(tx / 100 - TPL.w / 2, y, ty / 100 - TPL.h / 2)
}

/**
 * Pose de la tira puesta en el hueco, en coordenadas de la plantilla. Sigue la misma transformación que
 * plantillaSVG: translate(t.x, t.y + t.h) rotate(-90), es decir, mango abajo y punta arriba.
 */
export function stripOnTemplate() {
  const t = PLANTILLA.tira
  return {
    pos: tplLocal(t.x + TIRA.h / 2, t.y + t.h, TPL.t + 0.0005),
    q: new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 2),
  }
}

function roundRectShape(w, h, r) {
  const s = new THREE.Shape()
  const x0 = -w / 2
  const y0 = -h / 2
  const x1 = w / 2
  const y1 = h / 2
  r = Math.min(r, w / 2, h / 2)
  s.moveTo(x0 + r, y0)
  s.lineTo(x1 - r, y0)
  s.absarc(x1 - r, y0 + r, r, -Math.PI / 2, 0, false)
  s.lineTo(x1, y1 - r)
  s.absarc(x1 - r, y1 - r, r, 0, Math.PI / 2, false)
  s.lineTo(x0 + r, y1)
  s.absarc(x0 + r, y1 - r, r, Math.PI / 2, Math.PI, false)
  s.lineTo(x0, y0 + r)
  s.absarc(x0 + r, y0 + r, r, Math.PI, Math.PI * 1.5, false)
  return s
}

/** Rectángulo negro difuminado (sombras pintadas). */
function softRect(w, h, blur) {
  const pad = Math.ceil(blur * 2.2)
  const c = makeCanvas(w + 2 * pad, h + 2 * pad)
  const ctx = c.getContext('2d')
  ctx.shadowColor = '#000'
  ctx.shadowBlur = blur
  ctx.shadowOffsetX = c.width + 20
  ctx.fillStyle = '#000'
  ctx.fillRect(pad - c.width - 20, pad, w, h)
  return { canvas: c, pad }
}

/**
 * La plantilla: maps { empty, clean } (sin y con «Pon aquí la tira» borrado). group.userData.stripOn(t)
 * funde al impreso limpio y enciende la sombra de la tira puesta.
 */
export function buildTemplate(maps, { roughness = 0.8, bumpMap = null, bumpScale = 0, shadowTexture = null, shadowOpacity = 0.42 } = {}) {
  const g = new THREE.Group()
  const geo = new THREE.ExtrudeGeometry(roundRectShape(TPL.w, TPL.h, 0.26), { depth: TPL.t, bevelEnabled: false, curveSegments: 8 })
  geo.rotateX(-Math.PI / 2)
  const pos = geo.attributes.position
  const nor = geo.attributes.normal
  const uv = geo.attributes.uv
  for (let i = 0; i < pos.count; i++) {
    if (nor.getY(i) > 0.5) uv.setXY(i, (pos.getX(i) + TPL.w / 2) / TPL.w, (TPL.h / 2 - pos.getZ(i)) / TPL.h)
    else uv.setXY(i, 0.5, 0.5)
  }
  const mat = crossfadeMaterial({ roughness, bumpMap, bumpScale }, maps.empty, maps.clean || maps.empty)
  const card = new THREE.Mesh(geo, mat)
  card.castShadow = true
  card.receiveShadow = true
  g.add(card)
  // sombra suave bajo la tira puesta (el mapa de sombras no llega a 0,4 mm de relieve)
  let decal = null
  if (shadowTexture) {
    const k = 100 // px por cm de la textura de sombra
    const sw = shadowTexture.image.width / k
    const sh = shadowTexture.image.height / k
    decal = new THREE.Mesh(
      new THREE.PlaneGeometry(sw, sh).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ map: shadowTexture, color: '#1d2a2a', transparent: true, opacity: 0, depthWrite: false }),
    )
    // centrada bajo la tira puesta, algo desplazada hacia donde cae la luz; un pelo por encima del
    // cartón y por debajo de la cara de la tira (con polygonOffset taparía la tira, que mide 0,35 mm)
    const on = stripOnTemplate()
    const mid = new THREE.Vector3(STRIP.l / 2, 0, 0).applyQuaternion(on.q).add(on.pos)
    decal.position.set(mid.x + 0.025, TPL.t + 0.004, mid.z + 0.05)
    decal.quaternion.copy(on.q)
    decal.renderOrder = 2
    g.add(decal)
  }
  g.userData.setClean = (t) => (mat.userData.map2.value = t)
  g.userData.stripOn = (t) => {
    mat.userData.mix.value = t
    if (decal) {
      decal.material.opacity = shadowOpacity * t
      decal.visible = t > 0
    }
  }
  return g
}

/** Textura de la sombra pintada de la tira (en horizontal, 100 px por cm más el difuminado). */
export function stripShadowCanvas() {
  return softRect(STRIP.l * 100, STRIP.w * 100, 9).canvas
}

// ─── Código de barras y LCD ─────────────────────────────────────────────────────────────────
const EAN_L = ['0001101', '0011001', '0010011', '0111101', '0100011', '0110001', '0101111', '0111011', '0110111', '0001011']
const EAN_G = ['0100111', '0110011', '0011011', '0100001', '0011101', '0111001', '0000101', '0010001', '0001001', '0010111']
const EAN_R = ['1110010', '1100110', '1101100', '1000010', '1011100', '1001110', '1010000', '1000100', '1001000', '1110100']
const EAN_PAR = ['LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG', 'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL']

function drawBarcode(ctx, x, y, m, h, code12, color = C.ink) {
  const d = code12.split('').map(Number)
  const sum = d.reduce((s, v, i) => s + v * (i % 2 ? 3 : 1), 0)
  d.push((10 - (sum % 10)) % 10)
  let bits = '101'
  for (let i = 1; i <= 6; i++) bits += (EAN_PAR[d[0]][i - 1] === 'L' ? EAN_L : EAN_G)[d[i]]
  bits += '01010'
  for (let i = 7; i <= 12; i++) bits += EAN_R[d[i]]
  bits += '101'
  const left = x + m * 9
  ctx.fillStyle = color
  for (let i = 0; i < bits.length; i++) {
    if (bits[i] !== '1') continue
    const guard = i < 3 || (i >= 45 && i < 50) || i >= 92
    ctx.fillRect(left + i * m, y, m, h + (guard ? m * 5 : 0))
  }
  const digits = d.join('')
  setFont(ctx, m * 9, { mono: true, weight: 500 })
  ctx.textBaseline = 'alphabetic'
  ctx.textAlign = 'center'
  ctx.fillText(digits[0], x + m * 4, y + h + m * 8.5)
  ctx.fillText(digits.slice(1, 7), left + m * 24, y + h + m * 8.5)
  ctx.fillText(digits.slice(7), left + m * 70, y + h + m * 8.5)
  ctx.textAlign = 'left'
  return left + 95 * m
}

const SEVEN = { 0: 'abcdef', 1: 'bc', 2: 'abged', 3: 'abgcd', 4: 'fgbc', 5: 'afgcd', 6: 'afgedc', 7: 'abc', 8: 'abcdefg', 9: 'abcdfg' }
function drawSeven(ctx, str, x, y, h, { color = '#1b2729', ghost = 'rgba(27,39,41,0.06)', slant = 0.09, align = 'left' } = {}) {
  const w = h * 0.5
  const t = h * 0.12
  const adv = w + h * 0.2
  const total = str.length * adv - h * 0.2
  let cx = align === 'right' ? x - total : x
  const sk = (px, py) => [px + (y + h - py) * slant, py]
  const poly = (pts) => {
    ctx.beginPath()
    pts.forEach(([px, py], i) => {
      const [qx, qy] = sk(px, py)
      if (i) ctx.lineTo(qx, qy)
      else ctx.moveTo(qx, qy)
    })
    ctx.closePath()
    ctx.fill()
  }
  const hseg = (x0, x1, yy) => poly([[x0, yy], [x0 + t / 2, yy - t / 2], [x1 - t / 2, yy - t / 2], [x1, yy], [x1 - t / 2, yy + t / 2], [x0 + t / 2, yy + t / 2]])
  const vseg = (xx, y0, y1) => poly([[xx, y0], [xx + t / 2, y0 + t / 2], [xx + t / 2, y1 - t / 2], [xx, y1], [xx - t / 2, y1 - t / 2], [xx - t / 2, y0 + t / 2]])
  const g = t * 0.18
  const draw = (segs, x0) => {
    const L = x0 + t / 2
    const R = x0 + w - t / 2
    const top = y + t / 2
    const mid = y + h / 2
    const bot = y + h - t / 2
    if (segs.includes('a')) hseg(L + g, R - g, top)
    if (segs.includes('g')) hseg(L + g, R - g, mid)
    if (segs.includes('d')) hseg(L + g, R - g, bot)
    if (segs.includes('f')) vseg(L, top + g, mid - g)
    if (segs.includes('b')) vseg(R, top + g, mid - g)
    if (segs.includes('e')) vseg(L, mid + g, bot - g)
    if (segs.includes('c')) vseg(R, mid + g, bot - g)
  }
  for (const ch of str) {
    if (ghost) {
      ctx.fillStyle = ghost
      draw('abcdefg', cx)
    }
    if (SEVEN[ch]) {
      ctx.fillStyle = color
      draw(SEVEN[ch], cx)
    }
    cx += adv
  }
}

// ─── Geometría ──────────────────────────────────────────────────────────────────────────────
/** Torno cerrado en vuelta. profile: [[r, y], ...] con el exterior a la derecha del recorrido. */
function lathe(profile, segments = 64, radial = null) {
  const n = profile.length
  const pos = new Float32Array(n * segments * 3)
  const uv = new Float32Array(n * segments * 2)
  const len = [0]
  for (let i = 1; i < n; i++) len.push(len[i - 1] + Math.hypot(profile[i][0] - profile[i - 1][0], profile[i][1] - profile[i - 1][1]))
  for (let i = 0; i < n; i++) {
    const [r0, y] = profile[i]
    for (let j = 0; j < segments; j++) {
      const phi = (j / segments) * Math.PI * 2
      const r = radial ? radial(r0, y, phi) : r0
      const k = i * segments + j
      pos[k * 3] = r * Math.sin(phi)
      pos[k * 3 + 1] = y
      pos[k * 3 + 2] = r * Math.cos(phi)
      uv[k * 2] = j / segments
      uv[k * 2 + 1] = len[i] / (len[n - 1] || 1)
    }
  }
  const idx = []
  for (let i = 0; i < n - 1; i++) {
    for (let j = 0; j < segments; j++) {
      const a = i * segments + j
      const b = i * segments + ((j + 1) % segments)
      const c = (i + 1) * segments + j
      const d = (i + 1) * segments + ((j + 1) % segments)
      idx.push(a, b, c, b, d, c)
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2))
  g.setIndex(idx)
  g.computeVertexNormals()
  return g
}

function arc(cx, cy, r, a0, a1, steps = 5) {
  const out = []
  for (let i = 0; i <= steps; i++) {
    const a = lerp(a0, a1, i / steps) * DEG
    out.push([cx + r * Math.cos(a), cy + r * Math.sin(a)])
  }
  return out
}

function roundPlane(w, h, r, segs = 10) {
  const g = new THREE.ShapeGeometry(roundRectShape(w, h, r), segs)
  const p = g.attributes.position
  const uv = g.attributes.uv
  for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / w + 0.5, p.getY(i) / h + 0.5)
  return g
}

/** Normales suaves con ángulo de pliegue para geometrías no indexadas (ExtrudeGeometry). */
function smoothNormals(g, crease = 45) {
  const pos = g.attributes.position
  const n = pos.count
  const cosC = Math.cos(crease * DEG)
  const a = new THREE.Vector3()
  const b = new THREE.Vector3()
  const c = new THREE.Vector3()
  const fn = []
  for (let f = 0; f < n / 3; f++) {
    a.fromBufferAttribute(pos, f * 3)
    b.fromBufferAttribute(pos, f * 3 + 1)
    c.fromBufferAttribute(pos, f * 3 + 2)
    fn.push(new THREE.Vector3().subVectors(c, b).cross(new THREE.Vector3().subVectors(a, b)))
  }
  const keys = new Array(n)
  const buckets = new Map()
  for (let i = 0; i < n; i++) {
    const k = `${Math.round(pos.getX(i) * 1e3)},${Math.round(pos.getY(i) * 1e3)},${Math.round(pos.getZ(i) * 1e3)}`
    keys[i] = k
    let list = buckets.get(k)
    if (!list) buckets.set(k, (list = []))
    list.push(i)
  }
  const out = new Float32Array(n * 3)
  const sum = new THREE.Vector3()
  const nf = new THREE.Vector3()
  for (let i = 0; i < n; i++) {
    nf.copy(fn[Math.floor(i / 3)])
    if (nf.lengthSq() > 0) nf.normalize()
    sum.set(0, 0, 0)
    for (const j of buckets.get(keys[i])) {
      const o = fn[Math.floor(j / 3)]
      const l = o.length()
      if (l === 0) continue
      if (o.dot(nf) / l >= cosC) sum.add(o)
    }
    if (sum.lengthSq() === 0) sum.copy(nf)
    sum.normalize()
    out[i * 3] = sum.x
    out[i * 3 + 1] = sum.y
    out[i * 3 + 2] = sum.z
  }
  g.setAttribute('normal', new THREE.BufferAttribute(out, 3))
  return g
}

/** Barrido de una sección cerrada [[x, n], ...] a lo largo de una curva plana en YZ (correas). */
function sweep(curve, samples, section) {
  const X = new THREE.Vector3(1, 0, 0)
  const m = section.length
  const rows = samples + 1
  const pos = new Float32Array(rows * m * 3)
  const P = new THREE.Vector3()
  const T = new THREE.Vector3()
  const N = new THREE.Vector3()
  for (let i = 0; i < rows; i++) {
    const t = i / samples
    curve.getPointAt(t, P)
    curve.getTangentAt(t, T)
    N.crossVectors(X, T).normalize()
    for (let j = 0; j < m; j++) {
      const [sx, sn] = section[j]
      const k = (i * m + j) * 3
      pos[k] = P.x + X.x * sx + N.x * sn
      pos[k + 1] = P.y + X.y * sx + N.y * sn
      pos[k + 2] = P.z + X.z * sx + N.z * sn
    }
  }
  const idx = []
  for (let i = 0; i < samples; i++) {
    for (let j = 0; j < m; j++) {
      const j2 = (j + 1) % m
      const a = i * m + j
      const b = i * m + j2
      const c = (i + 1) * m + j
      const d = (i + 1) * m + j2
      idx.push(a, c, b, b, c, d)
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setIndex(idx)
  g.computeVertexNormals()
  return g
}

function superellipse(w, h, steps = 20, p = 5) {
  const pts = []
  for (let i = 0; i < steps; i++) {
    const a = (i / steps) * Math.PI * 2
    const c = Math.cos(a)
    const s = Math.sin(a)
    pts.push([(w / 2) * Math.sign(c) * Math.pow(Math.abs(c), 2 / p), (h / 2) * Math.sign(s) * Math.pow(Math.abs(s), 2 / p)])
  }
  return pts
}

// ─── Poses y recorridos ─────────────────────────────────────────────────────────────────────
const _m4 = new THREE.Matrix4()
function pose(x, y, z, rx = 0, ry = 0, rz = 0) {
  return { pos: new THREE.Vector3(x, y, z), q: new THREE.Quaternion().setFromEuler(new THREE.Euler(rx * DEG, ry * DEG, rz * DEG, 'YXZ')) }
}
/** Cuaternión a partir de los ejes locales x e y expresados en el padre. */
function qBasis(xAxis, yAxis) {
  const X = new THREE.Vector3(...xAxis).normalize()
  const Y = new THREE.Vector3(...yAxis).normalize()
  const Z = new THREE.Vector3().crossVectors(X, Y)
  return new THREE.Quaternion().setFromRotationMatrix(_m4.makeBasis(X, Y, Z))
}
/** a ∘ b: la pose b expresada en el sistema de a. */
function compose(a, b) {
  return { pos: b.pos.clone().applyQuaternion(a.q).add(a.pos), q: a.q.clone().multiply(b.q) }
}
const local = (x, y, z, q = new THREE.Quaternion()) => ({ pos: new THREE.Vector3(x, y, z), q })
const qEuler = (rx = 0, ry = 0, rz = 0) => new THREE.Quaternion().setFromEuler(new THREE.Euler(rx * DEG, ry * DEG, rz * DEG, 'YXZ'))

const _p1 = new THREE.Vector3()
const _p2 = new THREE.Vector3()
function bezier(out, a, b, c, d, t) {
  const it = 1 - t
  return out
    .set(0, 0, 0)
    .addScaledVector(a, it * it * it)
    .addScaledVector(b, 3 * it * it * t)
    .addScaledVector(c, 3 * it * t * t)
    .addScaledVector(d, t * t * t)
}

/** Recorrido por tramos: cada tramo va del final del anterior a `to` mientras p recorre `at`. */
class Track {
  constructor(obj, start, steps) {
    this.obj = obj
    this.start = start
    this.steps = steps
  }

  get end() {
    return this.steps.length ? this.steps[this.steps.length - 1].to : this.start
  }

  update(p) {
    let from = this.start
    const pos = this.obj.position.copy(from.pos)
    const q = this.obj.quaternion.copy(from.q)
    for (const s of this.steps) {
      if (p <= s.at[0]) break
      const t = (s.ease || easeInOut)(seg(p, s.at[0], s.at[1]))
      if (t >= 1) {
        from = s.to
        pos.copy(s.to.pos)
        q.copy(s.to.q)
        continue
      }
      _p1.copy(from.pos)
      _p1.y += s.lift ?? 3
      _p2.copy(s.to.pos)
      _p2.y += s.land ?? 2
      bezier(pos, from.pos, _p1, _p2, s.to.pos, t)
      const r = s.rot || [0.1, 0.9]
      q.slerpQuaternions(from.q, s.to.q, smooth(seg(t, r[0], r[1])))
      break
    }
  }
}

// ─── Sombras de contacto (técnica del ejemplo webgl_shadow_contact de three.js) ─────────────
// Una pasada de profundidad vista desde el suelo y dos desenfoques: un núcleo estrecho y oscuro pegado
// a los objetos y una oclusión ancha y suave, como en una foto de estudio.
export function contactShadows(renderer, { size = 120, res = 1024, height = 8, darkness = 1.4, y = -0.015, layers = [] } = {}) {
  const group = new THREE.Group()
  group.position.y = y
  const mkRT = (r) => {
    const t = new THREE.WebGLRenderTarget(r, r)
    t.texture.generateMipmaps = false
    return t
  }
  const rtDepth = mkRT(res)
  const geo = new THREE.PlaneGeometry(size, size).rotateX(Math.PI / 2)
  const cam = new THREE.OrthographicCamera(-size / 2, size / 2, size / 2, -size / 2, 0, height)
  cam.rotation.x = Math.PI / 2
  group.add(cam)
  const blurPlane = new THREE.Mesh(geo)
  blurPlane.visible = false
  group.add(blurPlane)

  const L = layers.map(({ blur, opacity, res: r = res, passes = 2 }, i) => {
    const rt = mkRT(r)
    const tmp = mkRT(r)
    const mat = new THREE.MeshBasicMaterial({ map: rt.texture, opacity, transparent: true, depthWrite: false })
    const plane = new THREE.Mesh(geo, mat)
    plane.renderOrder = 1 + i
    plane.scale.y = -1
    group.add(plane)
    return { blur, rt, tmp, mat, plane, passes }
  })

  const depthMat = new THREE.MeshDepthMaterial()
  depthMat.userData.darkness = { value: darkness }
  depthMat.onBeforeCompile = (shader) => {
    shader.uniforms.darkness = depthMat.userData.darkness
    shader.fragmentShader =
      'uniform float darkness;\n' +
      shader.fragmentShader.replace(
        'gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );',
        'gl_FragColor = vec4( vec3( 0.0 ), ( 1.0 - fragCoordZ ) * darkness );',
      )
  }
  const hBlur = new THREE.ShaderMaterial(HorizontalBlurShader)
  hBlur.depthTest = false
  const vBlur = new THREE.ShaderMaterial(VerticalBlurShader)
  vBlur.depthTest = false
  const step = (amountCm) => amountCm / size / 4

  function blur(src, dst, tmp, amountCm) {
    blurPlane.visible = true
    blurPlane.material = hBlur
    hBlur.uniforms.tDiffuse.value = src.texture
    hBlur.uniforms.h.value = step(amountCm)
    renderer.setRenderTarget(tmp)
    renderer.render(blurPlane, cam)
    blurPlane.material = vBlur
    vBlur.uniforms.tDiffuse.value = tmp.texture
    vBlur.uniforms.v.value = step(amountCm)
    renderer.setRenderTarget(dst)
    renderer.render(blurPlane, cam)
    blurPlane.visible = false
  }

  function update(scene, hide = []) {
    const bg = scene.background
    scene.background = null
    const hidden = hide.filter((o) => o && o.visible)
    hidden.forEach((o) => (o.visible = false))
    L.forEach((l) => (l.plane.visible = false))
    scene.overrideMaterial = depthMat
    const clearAlpha = renderer.getClearAlpha()
    const clearColor = renderer.getClearColor(new THREE.Color())
    renderer.setClearColor(0x000000, 0)
    renderer.setRenderTarget(rtDepth)
    renderer.clear()
    renderer.render(scene, cam)
    scene.overrideMaterial = null
    for (const l of L) {
      blur(rtDepth, l.rt, l.tmp, l.blur)
      for (let k = 1; k < l.passes; k++) blur(l.rt, l.rt, l.tmp, l.blur * (k === 1 ? 0.45 : 0.25))
    }
    renderer.setRenderTarget(null)
    renderer.setClearColor(clearColor, clearAlpha)
    L.forEach((l) => (l.plane.visible = true))
    hidden.forEach((o) => (o.visible = true))
    scene.background = bg
  }

  function dispose() {
    rtDepth.dispose()
    L.forEach((l) => {
      l.rt.dispose()
      l.tmp.dispose()
      l.mat.dispose()
    })
    geo.dispose()
    depthMat.dispose()
    hBlur.dispose()
    vBlur.dispose()
  }

  return { group, update, dispose }
}

// ─── La caja: cartoncillo blanco de 7 × 13 × 2,8 cm, de pie, con la solapa arriba ─────────────
const BOX = { w: 7, h: 13, d: 2.8, t: 0.045 }
const BAND = [8.85, 9.95] // banda con la escala de la marca, en cm desde arriba
// Atlas de impresión (troquel desplegado), en cm: [x0, y0, x1, y1] con y hacia abajo.
const ATLAS = {
  k: 72,
  w: 19.6,
  h: 17.4,
  front: [2.8, 0, 9.8, 13],
  left: [0, 0, 2.8, 13],
  right: [9.8, 0, 12.6, 13],
  back: [12.6, 0, 19.6, 13],
  top: [2.8, 13, 9.8, 15.8],
  tongue: [2.8, 15.8, 9.8, 17.3],
  inner: [0, 13, 2.8, 17.4],
  white: [9.8, 13, 12.6, 15.8],
  edge: [9.8, 15.8, 12.6, 17.4],
  plain: [12.6, 13, 19.6, 17.4],
}

/** Caja con cada cara mapeada a un rectángulo del atlas. faces: [+x, -x, +y, -y, +z, -z]. */
function atlasBox(w, h, d, faces) {
  const g = new THREE.BoxGeometry(w, h, d)
  const uv = g.attributes.uv
  for (let f = 0; f < 6; f++) {
    const r = faces[f] || ATLAS.white
    for (let i = f * 4; i < f * 4 + 4; i++) {
      const u = uv.getX(i)
      const v = uv.getY(i)
      uv.setXY(i, (r[0] + u * (r[2] - r[0])) / ATLAS.w, 1 - (r[3] - v * (r[3] - r[1])) / ATLAS.h)
    }
  }
  return g
}

function ivdMark(ctx, x, y, h) {
  ctx.strokeStyle = C.ink
  ctx.lineWidth = h * 0.07
  setFont(ctx, h * 0.62, { weight: 700 })
  const tw = ctx.measureText('IVD').width
  const w = tw + h * 0.5
  ctx.strokeRect(x, y, w, h)
  text(ctx, 'IVD', x + w / 2, y + h * 0.74, h * 0.62, { weight: 700, align: 'center' })
  return w
}

function lotBox(ctx, x, y, w, h, label, value) {
  ctx.strokeStyle = C.ink
  ctx.lineWidth = h * 0.05
  rrect(ctx, x, y, w, h, h * 0.18)
  ctx.stroke()
  text(ctx, label, x + h * 0.28, y + h * 0.66, h * 0.36, { mono: true, weight: 700, spacing: h * 0.02 })
  // valor de chorro de tinta: algo más gris y con puntos
  text(ctx, value, x + w - h * 0.28, y + h * 0.68, h * 0.42, { mono: true, weight: 500, color: '#2c3a3c', align: 'right' })
}

function pseudoQR(ctx, x, y, size, seed = 5) {
  const n = 25
  const m = size / n
  const rand = rng(seed)
  const inFinder = (i, j) => (i < 8 && j < 8) || (i >= n - 8 && j < 8) || (i < 8 && j >= n - 8)
  ctx.fillStyle = C.ink
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      if (inFinder(i, j)) continue
      if (rand() < 0.48) ctx.fillRect(x + i * m, y + j * m, m + 0.4, m + 0.4)
    }
  }
  const finder = (i, j) => {
    ctx.fillStyle = C.ink
    ctx.fillRect(x + i * m, y + j * m, 7 * m, 7 * m)
    ctx.fillStyle = C.board
    ctx.fillRect(x + (i + 1) * m, y + (j + 1) * m, 5 * m, 5 * m)
    ctx.fillStyle = C.ink
    ctx.fillRect(x + (i + 2) * m, y + (j + 2) * m, 3 * m, 3 * m)
  }
  finder(0, 0)
  finder(n - 7, 0)
  finder(0, n - 7)
}

/** Todos los impresos de la caja en un solo canvas (el troquel desplegado). */
function paintCarton(stripImg) {
  const A = ATLAS
  const k = A.k
  const c = makeCanvas(A.w * k, A.h * k)
  const ctx = c.getContext('2d')
  const X = (v) => v * k
  ctx.fillStyle = C.board
  ctx.fillRect(0, 0, c.width, c.height)

  // Banda de color que da la vuelta: izquierda, frente (las cuatro casillas), derecha y detrás.
  const band = (x0, x1, col) => {
    ctx.fillStyle = col
    ctx.fillRect(X(x0), X(BAND[0]), X(x1 - x0) + 0.5, X(BAND[1] - BAND[0]))
  }
  band(0, 2.8, BARS[0])
  BARS.forEach((col, i) => band(2.8 + i * 1.75, 2.8 + (i + 1) * 1.75, col))
  band(9.8, 12.6, BARS[3])
  ;[...BARS].reverse().forEach((col, i) => band(12.6 + i * 1.75, 12.6 + (i + 1) * 1.75, col))

  // ── Frente ──
  const F = (v) => X(2.8 + v)
  // la marca manda: logotipo a todo el ancho arriba, la tira en el centro y el nombre del producto debajo
  drawLogo(ctx, F(0.5), X(1.8), X(0.425))
  text(ctx, 'Kit de orina en casa', F(0.5), X(7.3), X(0.4), { weight: 800, stretch: 'expanded' })
  text(ctx, '3 tiras de albúmina y creatinina', F(0.5), X(7.85), X(0.26), { weight: 500, color: C.ink2 })
  // la tira, dibujada a tamaño real (la misma de toda la web)
  if (stripImg) {
    const real = STRIP.l <= 6.5
    const lcm = real ? STRIP.l : 5.8
    const sw = X(lcm)
    const sh = (sw * TIRA.h) / TIRA.w
    const sx = F((BOX.w - lcm) / 2)
    const sy = X(4.6) - sh / 2
    ctx.save()
    ctx.shadowColor = 'rgba(13,34,38,0.22)'
    ctx.shadowBlur = X(0.12)
    ctx.shadowOffsetY = X(0.05)
    ctx.drawImage(stripImg, sx, sy, sw, sh)
    ctx.restore()
    const mm = `${String(TIRA.w / 10).replace('.', ',')} × ${String(TIRA.h / 10).replace('.', ',')} mm`
    text(ctx, real ? 'Tamaño real' : '1 tira por sobre', sx, sy + sh + X(0.42), X(0.19), { mono: true, weight: 500, color: C.ink3 })
    text(ctx, mm, sx + sw, sy + sh + X(0.42), X(0.19), { mono: true, weight: 500, color: C.ink3, align: 'right' })
  }
  text(ctx, 'LECTURA CON EL MÓVIL', F(0.6), X(10.75), X(0.22), { weight: 700, color: C.teal, spacing: X(0.025) })
  text(ctx, '3 tiras · 1 vaso · 1 plantilla · 2 tubos', F(0.6), X(11.25), X(0.19), { mono: true, color: C.ink2 })
  const iw = ivdMark(ctx, F(0.6), X(12.0), X(0.36))
  text(ctx, 'Uso diagnóstico in vitro', F(0.6) + iw + X(0.16), X(12.29), X(0.2), { weight: 500, color: C.ink2 })

  // ── Lateral derecho: nombre en vertical y los recuadros LOT / CAD ──
  const R = (v) => X(9.8 + v)
  drawLogo(ctx, R(0.55), X(1.4), X(0.6), { word: false })
  ctx.save()
  ctx.translate(R(1.22), X(8.3))
  ctx.rotate(-Math.PI / 2)
  text(ctx, 'Kit de orina en casa', 0, 0, X(0.32), { weight: 800, stretch: 'expanded' })
  text(ctx, '3 tiras de albúmina y creatinina', 0, X(0.42), X(0.2), { weight: 500, color: C.ink2 })
  ctx.restore()
  lotBox(ctx, R(0.35), X(10.6), X(2.1), X(0.5), 'LOT', 'L2611A')
  lotBox(ctx, R(0.35), X(11.25), X(2.1), X(0.5), 'CAD', '2027-11')
  text(ctx, '2 °C – 30 °C', R(0.35), X(12.35), X(0.19), { mono: true, color: C.ink2 })

  // ── Lateral izquierdo: la app y el código de barras ──
  const Lx = (v) => X(v)
  ctx.save()
  ctx.translate(Lx(1.3), X(8.3))
  ctx.rotate(-Math.PI / 2)
  text(ctx, 'Todo se hace', 0, -X(0.05), X(0.4), { weight: 800, stretch: 'expanded' })
  text(ctx, 'desde la app', 0, X(0.45), X(0.4), { weight: 800, stretch: 'expanded', color: C.teal })
  ctx.restore()
  drawBarcode(ctx, Lx(0.3), X(10.55), X(0.0215), X(0.85), '843700026115')

  // ── Detrás: la app y el franqueo pagado (la caja vuelve al laboratorio con el tubo) ──
  const B = (v) => X(12.6 + v)
  drawLogo(ctx, B(0.6), X(1.0), X(0.24))
  text(ctx, 'Empieza en la app.', B(0.6), X(2.2), X(0.4), { weight: 800, stretch: 'expanded' })
  ;['Te dice cuándo hacer la prueba,', 'lee la tira con la cámara y', 'avisa a tu médico.'].forEach((s, i) =>
    text(ctx, s, B(0.6), X(2.85 + i * 0.4), X(0.23), { weight: 500, color: C.ink2 }),
  )
  pseudoQR(ctx, B(0.6), X(4.35), X(1.7))
  text(ctx, 'Escanea para', B(2.55), X(5.05), X(0.22), { weight: 600 })
  text(ctx, 'empezar', B(2.55), X(5.4), X(0.22), { weight: 600 })
  ctx.strokeStyle = C.ink
  ctx.lineWidth = X(0.025)
  rrect(ctx, B(0.6), X(10.45), X(5.8), X(1.55), X(0.12))
  ctx.stroke()
  text(ctx, 'FRANQUEO PAGADO', B(0.95), X(11.05), X(0.3), { mono: true, weight: 700, spacing: X(0.04) })
  text(ctx, '· devuélvela con el tubo dentro', B(0.95), X(11.6), X(0.25), { weight: 600, color: C.ink2 })
  drawBarcode(ctx, B(4.3), X(12.25), X(0.017), X(0.4), '843700026122')

  // ── Solapa, lengüeta, interior y cantos ──
  const T = (v) => X(2.8 + v)
  drawLogo(ctx, T(0.55), X(13 + 2.25), X(0.22), { word: false })
  // interior: cartón gris claro que oscurece hacia el fondo
  const [ix0, iy0, ix1, iy1] = A.inner.map(X)
  const gi = ctx.createLinearGradient(0, iy0, 0, iy1)
  gi.addColorStop(0, '#eceee9')
  gi.addColorStop(0.35, '#c9ccc6')
  gi.addColorStop(1, '#6f7571')
  ctx.fillStyle = gi
  ctx.fillRect(ix0, iy0, ix1 - ix0, iy1 - iy0)
  const fillR = (r, col) => {
    ctx.fillStyle = col
    ctx.fillRect(X(r[0]), X(r[1]), X(r[2] - r[0]), X(r[3] - r[1]))
  }
  fillR(A.edge, '#e3e4df')
  fillR(A.plain, '#e9eae5')
  fillR(A.tongue, C.board)
  return c
}

// Braille («kit orina») en relieve sobre la solapa.
const BRAILLE = { k: [1, 3], i: [2, 4], t: [2, 3, 4, 5], o: [1, 3, 5], r: [1, 2, 3, 5], n: [1, 3, 4, 5], a: [1], ' ': [] }

function buildBox(map) {
  const { w: W, h: H, d: D, t } = BOX
  const A = ATLAS
  const mat = new THREE.MeshStandardMaterial({ map, roughness: 0.52 })
  const g = new THREE.Group()
  const Hw = H - t
  const part = (geo, x, y, z, parent = g) => {
    const m = new THREE.Mesh(geo, mat)
    m.position.set(x, y, z)
    m.castShadow = true
    m.receiveShadow = true
    parent.add(m)
    return m
  }
  part(atlasBox(W, Hw, t, [A.edge, A.edge, A.edge, A.white, A.front, A.inner]), 0, Hw / 2, D / 2 - t / 2)
  part(atlasBox(W, Hw, t, [A.edge, A.edge, A.edge, A.white, A.inner, A.back]), 0, Hw / 2, -D / 2 + t / 2)
  part(atlasBox(t, Hw, D - 2 * t, [A.right, A.inner, A.edge, A.white, A.edge, A.edge]), W / 2 - t / 2, Hw / 2, 0)
  part(atlasBox(t, Hw, D - 2 * t, [A.inner, A.left, A.edge, A.white, A.edge, A.edge]), -W / 2 + t / 2, Hw / 2, 0)
  part(atlasBox(W - 2 * t, t, D - 2 * t, [A.edge, A.edge, A.inner, A.white, A.edge, A.edge]), 0, t / 2, 0)

  // Solapa: gira sobre el canto de arriba de la cara de atrás. La lengüeta cuelga por dentro del frente.
  const lid = new THREE.Group()
  lid.position.set(0, Hw, -D / 2)
  g.add(lid)
  part(atlasBox(W, t, D, [A.edge, A.edge, A.top, A.plain, A.edge, A.edge]), 0, t / 2, D / 2, lid)
  const tongue = new THREE.Group()
  tongue.position.set(0, 0, D - t)
  lid.add(tongue)
  const LT = 1.5
  part(atlasBox(W - 2 * t - 0.06, LT, t, [A.edge, A.edge, A.edge, A.edge, A.tongue, A.plain]), 0, -LT / 2, -t / 2, tongue)
  const dust = []
  for (const s of [-1, 1]) {
    const piv = new THREE.Group()
    piv.position.set(s * (W / 2 - t), Hw, 0)
    g.add(piv)
    const len = 1.2
    part(atlasBox(len, t, D - 2 * t - 0.14, [A.edge, A.edge, A.plain, A.plain, A.edge, A.edge]), -s * (len / 2), -t / 2, 0, piv)
    dust.push({ piv, s })
  }
  // braille
  const word = 'kit orina'
  const dots = []
  const pitch = 0.6
  const x0 = -((word.length - 1) * pitch + 0.25) / 2
  ;[...word].forEach((ch, i) => {
    for (const d of BRAILLE[ch] || []) {
      const col = d > 3 ? 1 : 0
      const row = (d - 1) % 3
      dots.push([x0 + i * pitch + col * 0.25, D / 2 - 0.25 + row * 0.25 + 0.1])
    }
  })
  const dotGeo = new THREE.SphereGeometry(0.072, 14, 6, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 0.55, 1)
  const braille = new THREE.InstancedMesh(dotGeo, new THREE.MeshStandardMaterial({ color: '#fbfbf9', roughness: 0.55 }), dots.length)
  dots.forEach(([x, z], i) => braille.setMatrixAt(i, _m4.makeTranslation(x, t, z)))
  lid.add(braille)

  g.userData.open = (k) => {
    lid.rotation.x = -122 * DEG * easeInOut(k)
    tongue.rotation.x = -55 * DEG * smooth(clamp(k * 1.3))
    for (const { piv, s } of dust) piv.rotation.z = -s * 98 * DEG * smooth(seg(k, 0.25, 1))
  }
  return g
}

// ─── Sobre de aluminio mate, uno por tira ─────────────────────────────────────────────────────
// Se ajusta a la tira: largo x (la zona para rasgar en +x), ancho z. La bolsa va de x = -l/2 + seal a
// l/2 - 0.9; la tira dentro, con el mango (x = 0 de la tira) en `handle`, justo antes del rasgado.
export const SACHET = (() => {
  const l = +(STRIP.l + 2.5).toFixed(3)
  const w = +Math.max(2.5, STRIP.w + 1.9).toFixed(3)
  const tear = l / 2 - 1.15
  return { l, w, seal: 0.35, k: 90, tear, tearCenter: (tear + l / 2) / 2, handle: l / 2 - 1.3 }
})()

/** Impresos del sobre: color (con la silueta en alfa), rugosidad/metal y relieve del sellado. */
function sachetCanvases() {
  const { l: L, w: Wd, k, seal, tear } = SACHET
  const cw = Math.round(L * k)
  const ch = Math.round(Wd * k)
  const X = (x) => (x + L / 2) * k // x del sobre (cm, centrado) → px
  const Z = (z) => (z + Wd / 2) * k // z del sobre (cm, centrado) → px
  const col = makeCanvas(cw, ch)
  const mr = makeCanvas(cw, ch)
  const bump = makeCanvas(cw, ch)
  const c1 = col.getContext('2d')
  const c2 = mr.getContext('2d')
  const c3 = bump.getContext('2d')
  // silueta: rectángulo redondeado con la muesca para rasgar
  const outline = (ctx) => {
    rrect(ctx, 0, 0, cw, ch, 0.22 * k)
  }
  c1.fillStyle = '#e3e6e8'
  outline(c1)
  c1.fill()
  c1.save()
  c1.globalCompositeOperation = 'destination-out'
  c1.beginPath()
  c1.moveTo(X(tear) - 0.1 * k, ch + 1)
  c1.lineTo(X(tear), ch - 0.17 * k)
  c1.lineTo(X(tear) + 0.1 * k, ch + 1)
  c1.closePath()
  c1.fill()
  c1.restore()
  // rugosidad (G) y metal (B): aluminio mate; la tinta blanca, sin metal
  c2.fillStyle = 'rgb(0,88,255)'
  c2.fillRect(0, 0, cw, ch)
  // relieve: arrugas suaves del aluminio (ruido de baja frecuencia) y el rayado del sellado
  {
    const rand = rng(17)
    const n1 = valueNoise(rand, 8)
    const n2 = valueNoise(rand, 32)
    const img = c3.createImageData(cw, ch)
    for (let y = 0; y < ch; y++) {
      for (let x = 0; x < cw; x++) {
        const u = x / cw
        const v = y / ch
        const val = 128 + 46 * (n1(u * 8, v * 2.4) - 0.5) + 18 * (n2(u * 32, v * 9) - 0.5)
        const i = (y * cw + x) * 4
        img.data[i] = img.data[i + 1] = img.data[i + 2] = val
        img.data[i + 3] = 255
      }
    }
    c3.putImageData(img, 0, 0)
  }
  // sellado: rayado fino en los márgenes
  c3.save()
  c3.beginPath()
  c3.rect(0, 0, cw, ch)
  rrect(c3, X(-L / 2 + seal), Z(-Wd / 2 + seal), (L - seal - 0.9) * k, (Wd - 2 * seal) * k, 0.1 * k)
  c3.clip('evenodd')
  c3.strokeStyle = 'rgba(255,255,255,0.55)'
  c3.lineWidth = 1.3
  for (let x = -ch; x < cw; x += 5) {
    c3.beginPath()
    c3.moveTo(x, 0)
    c3.lineTo(x + ch, ch)
    c3.stroke()
  }
  c3.restore()
  // zona blanca impresa
  const wx0 = -L / 2 + 0.8
  const wx1 = tear - 0.45
  const wz = Wd / 2 - 0.42
  const white = (ctx, fill) => {
    ctx.fillStyle = fill
    rrect(ctx, X(wx0), Z(-wz), (wx1 - wx0) * k, 2 * wz * k, 0.12 * k)
    ctx.fill()
  }
  white(c1, '#fbfbf9')
  white(c2, 'rgb(0,158,0)')
  white(c3, 'rgba(128,128,128,0.55)')
  drawLogo(c1, X(wx0 + 0.36), Z(-0.1), 0.26 * k)
  text(c1, 'Albúmina y creatinina', X(wx0 + 0.38), Z(0.4), 0.19 * k, { weight: 500, color: C.ink2 })
  text(c1, '1 tira', X(wx1 - 0.3), Z(0.0), 0.44 * k, { weight: 800, stretch: 'expanded', align: 'right' })
  text(c1, 'Ábrelo al usarla', X(wx1 - 0.3), Z(0.4), 0.16 * k, { mono: true, color: C.ink3, align: 'right' })
  // línea de rasgado, sobre el aluminio
  c1.strokeStyle = 'rgba(251,251,249,0.9)'
  c1.lineWidth = 0.025 * k
  c1.setLineDash([0.09 * k, 0.07 * k])
  c1.beginPath()
  c1.moveTo(X(tear), Z(-Wd / 2 + 0.22))
  c1.lineTo(X(tear), Z(Wd / 2 - 0.3))
  c1.stroke()
  c1.setLineDash([])
  c1.fillStyle = '#fbfbf9'
  c1.beginPath()
  c1.moveTo(X(tear) + 0.3 * k, Z(Wd / 2 - 0.42))
  c1.lineTo(X(tear) + 0.12 * k, Z(Wd / 2 - 0.32))
  c1.lineTo(X(tear) + 0.3 * k, Z(Wd / 2 - 0.22))
  c1.closePath()
  c1.fill()
  return { col, mr, bump }
}

/** Altura de la cara de arriba del sobre (almohadillado y la silueta de la tira por dentro). */
function sachetHeight(x, z) {
  const { l: L, w: Wd, seal } = SACHET
  const sx = sstep(-L / 2 + seal, -L / 2 + seal + 0.45, x) * (1 - sstep(L / 2 - 1.35, L / 2 - 0.9, x))
  const sz = sstep(-Wd / 2 + seal, -Wd / 2 + seal + 0.45, z) * (1 - sstep(Wd / 2 - seal - 0.45, Wd / 2 - seal, z))
  const h = SACHET.handle
  const strip = sstep(STRIP.w / 2 + 0.08, STRIP.w / 2 - 0.02, Math.abs(z)) * sstep(h - STRIP.l - 0.2, h - STRIP.l, x) * (1 - sstep(h, h + 0.2, x))
  return 0.004 + 0.052 * Math.sqrt(sx * sz) + 0.014 * strip * sx
}

/** Malla del sobre entre x0 y x1 (centrada en su propio centro en x): dos caras almohadilladas. */
function sachetGeometry(x0, x1) {
  const { l: L, w: Wd } = SACHET
  const nx = Math.max(2, Math.round((x1 - x0) / 0.12))
  const nz = 24
  const cx = (x0 + x1) / 2
  const pos = []
  const uv = []
  const idx = []
  for (const side of [1, -1]) {
    const base = pos.length / 3
    for (let j = 0; j <= nz; j++) {
      const z = -Wd / 2 + (j / nz) * Wd
      for (let i = 0; i <= nx; i++) {
        const x = x0 + (i / nx) * (x1 - x0)
        pos.push(x - cx, side * sachetHeight(x, z), z)
        uv.push((x + L / 2) / L, (Wd / 2 - z) / Wd)
      }
    }
    for (let j = 0; j < nz; j++) {
      for (let i = 0; i < nx; i++) {
        const a = base + j * (nx + 1) + i
        const b = a + 1
        const c = a + nx + 1
        const d = c + 1
        if (side > 0) idx.push(a, c, b, b, c, d)
        else idx.push(a, b, c, b, d, c)
      }
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2))
  g.setIndex(idx)
  g.computeVertexNormals()
  return g
}

/** Material del sobre: aluminio mate con la zona blanca impresa. tex(canvas, { srgb }) → textura. */
export function sachetMaterial(tex) {
  const sc = sachetCanvases()
  const mr = tex(sc.mr, { srgb: false })
  return new THREE.MeshStandardMaterial({
    map: tex(sc.col),
    roughnessMap: mr,
    metalnessMap: mr,
    roughness: 1,
    metalness: 1,
    bumpMap: tex(sc.bump, { srgb: false }),
    bumpScale: 0.6,
    alphaTest: 0.5,
    alphaToCoverage: true,
    side: THREE.DoubleSide,
  })
}

/**
 * Un sobre en dos piezas: body (grupo con el origen en el centro del sobre entero, largo en x y la zona
 * de rasgar en +x) y tear (el trozo que se rasga, con el origen en su propio centro, en x = tearCenter).
 */
export function buildSachet(mat) {
  const m = new THREE.Mesh(sachetGeometry(-SACHET.l / 2, SACHET.tear), mat)
  m.castShadow = true
  m.receiveShadow = true
  m.position.x = (-SACHET.l / 2 + SACHET.tear) / 2
  const body = new THREE.Group()
  body.add(m)
  const tear = new THREE.Mesh(sachetGeometry(SACHET.tear, SACHET.l / 2), mat)
  tear.castShadow = true
  tear.receiveShadow = true
  return { body, tear }
}

// ─── Vaso plegable de silicona: cuatro aros que pasan de disco plano a vaso ─────────────────────
// Cada aro es una banda algo abombada; plegado, todos caben uno dentro de otro (de 1,7 cm de alto) y,
// desplegado, quedan apilados con un escalón entre uno y otro.
const CUP = { n: 4, h: 1.7, rb: 2.3, dr: 0.16, step: 0.13, wall: 0.1, bulge: 0.06, liquid: 3.0 }
const cupRing = (i) => {
  const rb = CUP.rb + i * (CUP.dr + CUP.step)
  return { rb, rt: rb + CUP.dr }
}
/** Radio exterior del aro i a la altura s (0-1) de su banda. */
const cupR = (i, s) => cupRing(i).rb + CUP.dr * s + CUP.bulge * Math.sin(Math.PI * s)

export function buildCup({ color = '#f1f4f3', rim = C.teal } = {}) {
  const g = new THREE.Group()
  const { n, h, wall, step } = CUP
  const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.56 })
  const mRim = new THREE.MeshStandardMaterial({ color: rim, roughness: 0.45 })
  const rings = []
  for (let i = 0; i < n; i++) {
    const { rb, rt } = cupRing(i)
    const rIn = i === 0 ? 0 : rb - step - wall
    const outer = []
    const inner = []
    for (let k = 0; k <= 10; k++) {
      const s = k / 10
      outer.push([cupR(i, s), h * s * 0.96])
      inner.push([cupR(i, 1 - s) - wall, Math.max(wall, h * (1 - s) * 0.96)])
    }
    const prof = [
      [rb, 0],
      [rb, 0],
      ...outer,
      ...arc(rt - wall / 2, h * 0.96, wall / 2, 0, 180, 5),
      ...inner,
      [rb - wall, wall],
      [rIn, wall],
      [rIn, wall],
      [rIn, 0],
      [rIn, 0],
      [rb, 0],
    ]
    const ring = new THREE.Mesh(lathe(prof, 80), mat)
    ring.castShadow = true
    ring.receiveShadow = true
    g.add(ring)
    rings.push(ring)
  }
  // borde rígido del aro de arriba, del color de la marca
  const top = cupRing(n - 1)
  const lip = new THREE.Mesh(new THREE.TorusGeometry(top.rt - wall / 2 + 0.02, 0.1, 12, 80).rotateX(Math.PI / 2), mRim)
  lip.position.y = h * 0.96
  lip.castShadow = true
  rings[n - 1].add(lip)
  // muestra de orina (aparece en el paso 3), en el segundo aro
  const yl = CUP.liquid
  const rl = cupR(1, (yl - h) / h) - wall + 0.004
  const liquid = new THREE.Mesh(
    new THREE.CircleGeometry(rl, 48).rotateX(-Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: '#efe3a8', roughness: 0.06, transparent: true, opacity: 0, depthWrite: false }),
  )
  liquid.position.y = yl
  liquid.renderOrder = 3
  liquid.visible = false
  g.add(liquid)
  g.userData.expand = (t) => {
    rings.forEach((r, i) => (r.position.y = i * h * t))
  }
  g.userData.fill = (t) => {
    liquid.material.opacity = 0.92 * t
    liquid.visible = t > 0.001
  }
  return g
}

// ─── Tubo de orina con tapón de rosca ─────────────────────────────────────────────────────────
const TUBE = { r: 0.6, body: 4.95, cap: 0.72, top: 5.95 }

function tubeLabel() {
  const k = 110
  const w = 2 * Math.PI * (TUBE.r + 0.004) * (300 / 360)
  const h = 2.3
  const c = makeCanvas(w * k, h * k)
  const ctx = c.getContext('2d')
  const X = (v) => v * k
  ctx.fillStyle = C.board
  ctx.fillRect(0, 0, c.width, c.height)
  ctx.fillStyle = C.teal
  ctx.fillRect(0, 0, c.width, X(0.16))
  const cx = c.width / 2
  drawLogo(ctx, cx - X(0.62), X(0.72), X(0.24), { word: false })
  text(ctx, 'Orina', cx - X(0.0), X(0.72), X(0.26), { weight: 800, stretch: 'expanded' })
  ctx.fillStyle = C.line
  ;[1.25, 1.75].forEach((y, i) => {
    text(ctx, i ? 'Fecha' : 'Nombre', cx - X(0.95), X(y), X(0.15), { weight: 500, color: C.ink3 })
    ctx.fillStyle = C.line
    ctx.fillRect(cx - X(0.95), X(y + 0.12), X(1.9), X(0.012))
  })
  return c
}

function buildTube(capMat, labelMap) {
  const g = new THREE.Group()
  const { r, body, cap, top } = TUBE
  const glass = new THREE.MeshStandardMaterial({ color: '#f4f7f6', roughness: 0.22, transparent: true, opacity: 0.6 })
  const b = new THREE.Mesh(lathe([[0, 0], ...arc(0, r, r, -90, 0, 8), [r, body], [r - 0.04, body + 0.04], [r - 0.04, body + 0.5], [0, body + 0.5]], 40), glass)
  b.castShadow = true
  g.add(b)
  const ridge = (rr, y, phi) => (y > body - 0.05 && y < top - 0.08 ? rr + 0.012 * Math.pow(0.5 + 0.5 * Math.cos(phi * 36), 0.6) : rr)
  const cm = new THREE.Mesh(
    lathe([[r - 0.02, body - 0.12], [cap, body - 0.12], [cap, top - 0.1], ...arc(cap - 0.1, top - 0.1, 0.1, 0, 90, 4), [0, top]], 72, ridge),
    capMat,
  )
  cm.castShadow = true
  g.add(cm)
  const label = new THREE.Mesh(
    new THREE.CylinderGeometry(r + 0.004, r + 0.004, 2.3, 40, 1, true, Math.PI * (1 - 300 / 360), 2 * Math.PI * (300 / 360)),
    new THREE.MeshStandardMaterial({ map: labelMap, roughness: 0.62 }),
  )
  label.position.y = 2.15
  g.add(label)
  return g
}

// ─── Reloj inteligente genérico: caja redonda, ECG en pantalla y correa de la paleta ─────────────
function watchDisplay() {
  const S = 512
  const c = makeCanvas(S, S)
  const ctx = c.getContext('2d')
  ctx.fillStyle = '#030505'
  ctx.fillRect(0, 0, S, S)
  ctx.save()
  ctx.beginPath()
  ctx.arc(S / 2, S / 2, S / 2 - 6, 0, Math.PI * 2)
  ctx.clip()
  ctx.strokeStyle = 'rgba(95,190,140,0.13)'
  ctx.lineWidth = 1.5
  for (let x = 40; x < S; x += 28) {
    ctx.beginPath()
    ctx.moveTo(x, 170)
    ctx.lineTo(x, 340)
    ctx.stroke()
  }
  for (let y = 170; y <= 340; y += 28) {
    ctx.beginPath()
    ctx.moveTo(30, y)
    ctx.lineTo(S - 30, y)
    ctx.stroke()
  }
  setFont(ctx, 30, { weight: 700, stretch: 'expanded' })
  ctx.fillStyle = C.green
  ctx.textAlign = 'center'
  ctx.fillText('ECG', S / 2, 118)
  setFont(ctx, 24, { mono: true, weight: 500 })
  ctx.fillStyle = '#9fb3b0'
  ctx.fillText('10:09', S / 2, 78)
  const ecg = (t) => {
    const gk = (mu, s, a) => a * Math.exp(-((t - mu) ** 2) / (2 * s * s))
    return gk(0.18, 0.025, 0.12) + gk(0.355, 0.009, -0.13) + gk(0.375, 0.011, 1.0) + gk(0.395, 0.01, -0.24) + gk(0.62, 0.045, 0.28)
  }
  ctx.strokeStyle = '#7fe0b4'
  ctx.lineWidth = 6
  ctx.lineJoin = 'round'
  ctx.beginPath()
  for (let x = 24; x <= S - 24; x++) {
    const t = ((x - 24) / (S - 48)) * 2.4 + 0.42
    const y = 290 - ecg(t % 1) * 120
    if (x === 24) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.stroke()
  setFont(ctx, 76, { weight: 800, stretch: 'expanded' })
  ctx.fillStyle = '#ffffff'
  ctx.textAlign = 'right'
  ctx.fillText('74', S / 2 + 34, 432)
  setFont(ctx, 26, { mono: true, weight: 500 })
  ctx.fillStyle = '#9fb3b0'
  ctx.textAlign = 'left'
  ctx.fillText('lpm', S / 2 + 46, 430)
  ctx.restore()
  return c
}

function buildWatch(dispMap) {
  const g = new THREE.Group()
  const inner = new THREE.Group()
  g.add(inner)
  const R = 2.1
  const T = 1.08
  const mCase = new THREE.MeshStandardMaterial({ color: '#d3d8d8', metalness: 0.78, roughness: 0.3 })
  const prof = [
    [0, -T / 2],
    [R - 0.45, -T / 2],
    ...arc(R - 0.45, -T / 2 + 0.45, 0.45, -90, 0, 7),
    [R, T / 2 - 0.28],
    ...arc(R - 0.28, T / 2 - 0.28, 0.28, 0, 90, 6),
    [R - 0.36, T / 2],
    [R - 0.36, T / 2 - 0.03],
    [0, T / 2 - 0.03],
  ]
  const cs = new THREE.Mesh(lathe(prof, 96).rotateX(Math.PI / 2), mCase)
  cs.castShadow = true
  inner.add(cs)
  const glass = new THREE.Mesh(
    new THREE.CircleGeometry(R - 0.36, 64),
    new THREE.MeshPhysicalMaterial({
      color: '#020303',
      roughness: 0.05,
      clearcoat: 1,
      clearcoatRoughness: 0.03,
      emissive: '#ffffff',
      emissiveMap: dispMap,
      emissiveIntensity: 1.1,
    }),
  )
  glass.position.z = T / 2 - 0.02
  inner.add(glass)
  const crown = new THREE.Mesh(
    lathe([[0, -0.17], [0.27, -0.17], [0.27, 0.17], [0, 0.17]], 40, (r, y, phi) => (r > 0.2 ? r + 0.014 * Math.cos(phi * 28) : r)).rotateZ(Math.PI / 2),
    mCase,
  )
  crown.position.set(R + 0.1, 0, 0)
  inner.add(crown)
  const pusher = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.22, 24).rotateZ(Math.PI / 2), mCase)
  pusher.position.set((R + 0.04) * Math.cos(30 * DEG), (R + 0.04) * Math.sin(30 * DEG), 0)
  pusher.rotation.z = 30 * DEG
  inner.add(pusher)
  // correa: lazo cerrado por detrás de la caja
  const band = new THREE.CatmullRomCurve3(
    [
      new THREE.Vector3(0, R - 0.25, -0.15),
      new THREE.Vector3(0, R + 0.6, -0.7),
      new THREE.Vector3(0, R + 0.95, -2.05),
      new THREE.Vector3(0, R + 0.3, -3.5),
      new THREE.Vector3(0, 0, -4.1),
      new THREE.Vector3(0, -R - 0.3, -3.5),
      new THREE.Vector3(0, -R - 0.95, -2.05),
      new THREE.Vector3(0, -R - 0.6, -0.7),
      new THREE.Vector3(0, -R + 0.25, -0.15),
    ],
    false,
    'centripetal',
  )
  const mBand = new THREE.MeshStandardMaterial({ color: C.teal, roughness: 0.58 })
  const bm = new THREE.Mesh(sweep(band, 140, superellipse(2.0, 0.3, 24, 6)), mBand)
  bm.castShadow = true
  inner.add(bm)
  inner.rotation.x = -15 * DEG
  inner.updateMatrixWorld(true)
  const bb = new THREE.Box3().setFromObject(inner)
  inner.position.y = -bb.min.y
  return g
}

// ─── Tensiómetro de brazo: aparato con pantalla y manguito enrollado ───────────────────────────
function lcdCanvas(wcm, hcm, k, paint) {
  const c = makeCanvas(wcm * k, hcm * k)
  const ctx = c.getContext('2d')
  const g = ctx.createLinearGradient(0, 0, c.width, c.height)
  g.addColorStop(0, '#d5dcd6')
  g.addColorStop(1, '#c4cdc7')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, c.width, c.height)
  paint(ctx, k, c.width, c.height)
  return c
}

function buildMonitor(lcdMap) {
  const g = new THREE.Group()
  const mWhite = new THREE.MeshStandardMaterial({ color: '#f1f4f3', roughness: 0.32 })
  const mDark = new THREE.MeshPhysicalMaterial({ color: '#1c2729', roughness: 0.25, clearcoat: 0.8, clearcoatRoughness: 0.1 })
  const mTeal = new THREE.MeshStandardMaterial({ color: C.teal, roughness: 0.38 })
  const mGrey = new THREE.MeshStandardMaterial({ color: '#c9d3cf', roughness: 0.45 })
  // cuerpo en cuña: perfil lateral (z, y) extruido a lo ancho
  const W = 9.6
  const shape = new THREE.Shape()
  const P = [
    [-5.6, 0],
    [5.6, 0],
    [5.6, 1.9],
    [-5.6, 4.3],
  ].map(([x, y]) => new THREE.Vector2(x, y))
  const rr = 0.8
  for (let i = 0; i < P.length; i++) {
    const prev = P[(i + P.length - 1) % P.length]
    const cur = P[i]
    const next = P[(i + 1) % P.length]
    const a = cur.clone().add(prev.clone().sub(cur).setLength(rr))
    const b = cur.clone().add(next.clone().sub(cur).setLength(rr))
    if (i === 0) shape.moveTo(a.x, a.y)
    else shape.lineTo(a.x, a.y)
    shape.quadraticCurveTo(cur.x, cur.y, b.x, b.y)
  }
  shape.closePath()
  const bev = 0.42
  const geo = new THREE.ExtrudeGeometry(shape, { depth: W - 2 * bev, bevelEnabled: true, bevelThickness: bev, bevelSize: bev * 0.9, bevelSegments: 6, curveSegments: 10 })
  geo.translate(0, 0, -(W - 2 * bev) / 2)
  geo.rotateY(-Math.PI / 2)
  smoothNormals(geo, 50)
  const body = new THREE.Mesh(geo, mWhite)
  body.position.y = bev * 0.9
  body.castShadow = true
  body.receiveShadow = true
  g.add(body)
  const slope = Math.atan2(4.3 - 1.9, 11.2)
  const yAt = (z) => bev * 0.9 + lerp(4.3, 1.9, (z + 5.6) / 11.2) + bev * 0.98
  const face = new THREE.Group()
  face.position.set(0, yAt(-1.3) + 0.005, -1.3)
  face.rotation.x = -Math.PI / 2 + slope
  g.add(face)
  face.add(new THREE.Mesh(roundPlane(7.0, 5.0, 0.45), mDark))
  const screen = new THREE.Mesh(roundPlane(6.3, 4.3, 0.2), new THREE.MeshPhysicalMaterial({ map: lcdMap, roughness: 0.35, clearcoat: 1, clearcoatRoughness: 0.04 }))
  screen.position.z = 0.01
  face.add(screen)
  const btnFace = new THREE.Group()
  btnFace.position.set(0, yAt(3.8), 3.8)
  btnFace.rotation.x = slope
  g.add(btnFace)
  const button = (r, h, segs) => lathe([[0, -0.1], [r, -0.1], [r, h - 0.06], ...arc(r - 0.06, h - 0.06, 0.06, 0, 90, 3), [r * 0.5, h + 0.01], [0, h + 0.015]], segs)
  const btn = new THREE.Mesh(button(0.85, 0.2, 64), mTeal)
  btn.castShadow = true
  btnFace.add(btn)
  const btn2 = new THREE.Mesh(button(0.42, 0.12, 40), mGrey)
  btn2.position.set(-2.4, 0, 0.1)
  btnFace.add(btn2)

  // manguito enrollado, tumbado a la izquierda: tela gris con ribete, la solapa que lo cierra con su
  // anilla en D, la marca de la arteria y el tubo de aire hasta el aparato
  const cuff = new THREE.Group()
  const L = 11.5
  const ro = 3.9
  const thick = 0.55
  const cuffProfile = [
    [ro - thick + 0.2, -L / 2],
    ...arc(ro - 0.25, -L / 2 + 0.25, 0.25, -90, 0, 4),
    ...arc(ro - 0.25, L / 2 - 0.25, 0.25, 0, 90, 4),
    ...arc(ro - thick + 0.2, L / 2 - 0.2, 0.2, 90, 180, 4),
    ...arc(ro - thick + 0.2, -L / 2 + 0.2, 0.2, 180, 270, 4),
  ]
  const weave = makeCanvas(256, 256)
  {
    const ctx = weave.getContext('2d')
    ctx.fillStyle = '#808080'
    ctx.fillRect(0, 0, 256, 256)
    for (let i = 0; i < 256; i += 4) {
      ctx.fillStyle = 'rgba(255,255,255,0.24)'
      ctx.fillRect(i, 0, 2, 256)
      ctx.fillStyle = 'rgba(0,0,0,0.24)'
      ctx.fillRect(0, i, 256, 2)
    }
  }
  const weaveTex = new THREE.CanvasTexture(weave)
  weaveTex.wrapS = weaveTex.wrapT = THREE.RepeatWrapping
  weaveTex.repeat.set(30, 10)
  const mFabric = new THREE.MeshPhysicalMaterial({
    color: '#53646b',
    roughness: 0.96,
    sheen: 1,
    sheenColor: new THREE.Color('#9fb0b3'),
    sheenRoughness: 0.5,
    bumpMap: weaveTex,
    bumpScale: 0.7,
    side: THREE.DoubleSide,
  })
  const cm = new THREE.Mesh(lathe(cuffProfile, 96), mFabric)
  cm.castShadow = true
  cuff.add(cm)
  const mBind = new THREE.MeshStandardMaterial({ color: '#25333a', roughness: 0.85 })
  const mStitch = new THREE.MeshStandardMaterial({ color: '#c7d0cf', roughness: 0.8 })
  for (const s of [-1, 1]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(ro - thick / 2, thick / 2 + 0.04, 10, 96), mBind)
    ring.rotation.x = Math.PI / 2
    ring.position.y = s * (L / 2 - 0.1)
    ring.scale.set(1, 1, 0.5)
    cuff.add(ring)
    // pespunte claro junto al ribete
    const stitch = new THREE.Mesh(new THREE.TorusGeometry(ro + 0.004, 0.018, 4, 120), mStitch)
    stitch.rotation.x = Math.PI / 2
    stitch.position.y = s * (L / 2 - 0.42)
    cuff.add(stitch)
  }
  // solapa: la última vuelta de tela, algo separada, con su borde y la anilla
  const fa0 = 1.2
  const fa1 = 1.75
  const flap = new THREE.Mesh(new THREE.CylinderGeometry(ro + 0.06, ro + 0.06, L - 0.6, 64, 1, true, fa0, fa1), mFabric)
  flap.castShadow = true
  cuff.add(flap)
  const edgeA = fa0 + fa1
  const edge = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, L - 0.6, 10), mBind)
  edge.position.set((ro + 0.06) * Math.sin(edgeA), 0, (ro + 0.06) * Math.cos(edgeA))
  cuff.add(edge)
  const dring = new THREE.Mesh(
    new THREE.TorusGeometry(1.4, 0.075, 10, 40, Math.PI),
    new THREE.MeshStandardMaterial({ color: '#cfd5d4', metalness: 0.85, roughness: 0.3 }),
  )
  dring.position.set((ro + 0.12) * Math.sin(edgeA + 0.18), 0, (ro + 0.12) * Math.cos(edgeA + 0.18))
  dring.rotation.y = edgeA + 0.18 + Math.PI / 2
  dring.rotation.order = 'YXZ'
  dring.rotation.x = 0.12
  cuff.add(dring)
  // marca de la arteria: triángulo y línea en una etiqueta clara
  const tagC = makeCanvas(160, 240)
  {
    const ctx = tagC.getContext('2d')
    ctx.fillStyle = '#eef1f0'
    ctx.fillRect(0, 0, 160, 240)
    ctx.fillStyle = C.teal
    ctx.beginPath()
    ctx.moveTo(36, 70)
    ctx.lineTo(124, 70)
    ctx.lineTo(80, 150)
    ctx.closePath()
    ctx.fill()
    ctx.fillRect(76, 150, 8, 70)
  }
  const tagTex = new THREE.CanvasTexture(tagC)
  tagTex.colorSpace = THREE.SRGBColorSpace
  const tag = new THREE.Mesh(new THREE.CylinderGeometry(ro + 0.075, ro + 0.075, 2.6, 16, 1, true, fa0 + 0.6, 0.38), new THREE.MeshStandardMaterial({ map: tagTex, roughness: 0.6 }))
  tag.position.y = -1.6
  cuff.add(tag)
  cuff.rotation.order = 'YXZ'
  cuff.rotation.set(0, -58 * DEG, Math.PI / 2)
  cuff.position.set(-10.2, ro, -3.2)
  g.add(cuff)
  cuff.updateMatrix()
  const end = new THREE.Vector3(-W / 2 - 0.1, 2.0, -2.2)
  const center = new THREE.Vector3().applyMatrix4(cuff.matrix)
  const axis = new THREE.Vector3(0, 1, 0).transformDirection(cuff.matrix)
  const radial = end.clone().sub(center)
  radial.addScaledVector(axis, -radial.dot(axis)).normalize()
  radial.lerp(new THREE.Vector3(0, 1, 0), 0.25)
  radial.addScaledVector(axis, -radial.dot(axis)).normalize()
  const sw = center.clone().addScaledVector(axis, 1.2).addScaledVector(radial, ro + 0.05)
  const sag = sw.clone().lerp(end, 0.5)
  sag.y = 0.24
  sag.z += 3.2
  const hose = new THREE.CatmullRomCurve3([sw, sw.clone().addScaledVector(radial, 1.2), sag, end.clone().add(new THREE.Vector3(-1.5, -0.8, 0.3)), end])
  const hm = new THREE.Mesh(new THREE.TubeGeometry(hose, 140, 0.19, 12), new THREE.MeshStandardMaterial({ color: '#33464a', roughness: 0.5 }))
  hm.castShadow = true
  g.add(hm)
  const port = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.5, 24), mGrey)
  port.rotation.z = Math.PI / 2
  port.position.copy(end).add(new THREE.Vector3(0.15, 0, 0))
  g.add(port)
  return g
}

function monitorLCD() {
  return lcdCanvas(6.3, 4.3, 90, (ctx, k, Wc) => {
    const X = (v) => v * k
    text(ctx, 'SYS', X(0.32), X(0.8), X(0.4), { weight: 700, color: '#1b2729' })
    text(ctx, 'mmHg', X(0.32), X(1.22), X(0.28), { mono: true, color: '#1b2729' })
    text(ctx, 'DIA', X(0.32), X(2.42), X(0.4), { weight: 700, color: '#1b2729' })
    text(ctx, 'mmHg', X(0.32), X(2.84), X(0.28), { mono: true, color: '#1b2729' })
    text(ctx, 'PUL /min', X(0.32), X(4.0), X(0.28), { mono: true, color: '#1b2729' })
    drawSeven(ctx, '128', Wc - X(0.38), X(0.28), X(1.6), { align: 'right' })
    ctx.fillStyle = 'rgba(27,39,41,0.5)'
    ctx.fillRect(X(0.28), X(2.05), Wc - X(0.56), X(0.03))
    drawSeven(ctx, '82', Wc - X(0.38), X(2.2), X(1.25), { align: 'right' })
    drawSeven(ctx, '74', Wc - X(0.38), X(3.55), X(0.62), { align: 'right' })
  })
}

// ─── Montaje ────────────────────────────────────────────────────────────────────────────────
/**
 * Monta el kit en `container` (que debe tener tamaño). Devuelve { setProgress(p, {immediate}), progress,
 * ready, snapshot(), timings, destroy() }. snapshot() dibuja y devuelve el fotograma en PNG.
 */
export async function mountKit(container, opts = {}) {
  if (!container) throw new Error('mountKit: falta el contenedor')
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const o = {
    progress: 0,
    background: null,
    parallax: !reduceMotion,
    smoothing: reduceMotion ? 0 : 0.14,
    maxPixelRatio: 2,
    fade: 0.05,
    ...opts,
  }

  let renderer
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: o.background == null, powerPreference: 'high-performance' })
  } catch (err) {
    throw new Error(`WebGL no disponible: ${err.message}`)
  }
  // texturas en paralelo con la puesta en marcha del renderer
  const t0 = performance.now()
  const timings = {}
  const mark = (k) => (timings[k] = Math.round(performance.now() - t0))
  // lo que se ve al principio; la tira leída (DEMO) y la plantilla limpia llegan después, en un rato libre
  const stripsP = loadKitFonts().then(() => Promise.all([stripCanvas(SECA), templateCanvas(768)]))

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, o.maxPixelRatio))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.NeutralToneMapping
  renderer.toneMappingExposure = 1.0
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.VSMShadowMap
  renderer.shadowMap.autoUpdate = false
  if (o.background == null) renderer.setClearColor(0xffffff, 0)
  else renderer.setClearColor(o.background, 1)

  const canvas = renderer.domElement
  canvas.setAttribute('aria-hidden', 'true')
  canvas.style.display = 'block'
  canvas.style.width = '100%'
  canvas.style.height = '100%'
  // los bordes se funden con la página: las sombras y lo que asoma por el borde no se cortan en seco
  if (o.fade > 0) {
    const f = `${(o.fade * 100).toFixed(1)}%`
    const g = (dir) => `linear-gradient(${dir}, transparent, #000 ${f}, #000 calc(100% - ${f}), transparent)`
    const mask = `${g('to right')}, ${g('to bottom')}`
    canvas.style.webkitMaskImage = mask
    canvas.style.webkitMaskComposite = 'source-in'
    canvas.style.maskImage = mask
    canvas.style.maskComposite = 'intersect'
  }
  // se engancha ya (transparente) para que el navegador prepare su capa mientras cargan las texturas
  renderer.setSize(Math.max(1, container.clientWidth), Math.max(1, container.clientHeight), false)
  container.appendChild(canvas)

  const aniso = Math.min(8, renderer.capabilities.getMaxAnisotropy())
  const textures = new Set()
  const tex = (c, { srgb = true } = {}) => {
    const t = new THREE.CanvasTexture(c)
    if (srgb) t.colorSpace = THREE.SRGBColorSpace
    t.anisotropy = aniso
    textures.add(t)
    return t
  }

  const scene = new THREE.Scene()
  if (o.background != null) scene.background = new THREE.Color(o.background)
  const camera = new THREE.PerspectiveCamera(20, 1, 1, 1500)

  // Entorno de estudio + luz principal con sombra blanda.
  mark('renderer')
  const pmrem = new THREE.PMREMGenerator(renderer)
  const room = new RoomEnvironment()
  const envRT = pmrem.fromScene(room, 0.035)
  room.dispose()
  pmrem.dispose()
  scene.environment = envRT.texture
  scene.environmentIntensity = 0.92
  scene.environmentRotation.set(0, -35 * DEG, 0)

  const key = new THREE.DirectionalLight('#fffaf2', 1.3)
  key.position.set(-30, 62, 36)
  key.target.position.set(0, 0, 2)
  key.castShadow = true
  key.shadow.mapSize.set(1024, 1024)
  Object.assign(key.shadow.camera, { left: -45, right: 45, top: 45, bottom: -45, near: 20, far: 150 })
  key.shadow.radius = 6
  key.shadow.blurSamples = 16
  key.shadow.bias = -0.0003
  scene.add(key, key.target)
  // relleno suave desde delante: que las caras verticales de la caja no se queden grises
  const fill = new THREE.DirectionalLight('#f4f8ff', 0.6)
  fill.position.set(18, 22, 60)
  scene.add(fill)

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(140, 140).rotateX(-Math.PI / 2), new THREE.ShadowMaterial({ color: '#16292c', opacity: 0.1, depthWrite: false }))
  floor.position.y = -0.01
  floor.receiveShadow = true
  scene.add(floor)

  const contact = contactShadows(renderer, {
    size: 130,
    res: 1024,
    height: 8,
    darkness: 1.5,
    layers: [
      { blur: 0.22, opacity: 0.6 },
      { blur: 2.6, opacity: 0.32, res: 512, passes: 3 },
    ],
  })
  scene.add(contact.group)

  // ── Texturas ──
  mark('entorno')
  let seca, tplEmpty
  try {
    ;[seca, tplEmpty] = await stripsP
  } catch (err) {
    renderer.dispose()
    renderer.forceContextLoss()
    canvas.remove()
    throw new Error(`Kit 3D: no se pudieron preparar las texturas (${err && err.message})`)
  }
  mark('svg')
  const secaMap = tex(seca)
  const stripMaps = { seca: secaMap, demo: secaMap }
  const shadowCanvas = stripShadowCanvas()
  const shadowTex = tex(shadowCanvas, { srgb: false })
  const cartonMap = tex(paintCarton(seca))

  // ── El kit (todo lo que se aparta en el paso 4 va en kitGroup) ──
  const kitGroup = new THREE.Group()
  scene.add(kitGroup)

  const box = buildBox(cartonMap)
  const BOXPOSE = pose(-11.6, 0, -5.4, 0, 22, 0)
  box.position.copy(BOXPOSE.pos)
  box.quaternion.copy(BOXPOSE.q)
  kitGroup.add(box)
  const inBox = (l) => compose(BOXPOSE, l)

  const template = buildTemplate({ empty: tex(tplEmpty) }, { shadowTexture: shadowTex })
  kitGroup.add(template)

  const strip = buildStrip(stripMaps)
  kitGroup.add(strip)

  const mSachet = sachetMaterial(tex)
  const sachetParts = [0, 1, 2].map(() => buildSachet(mSachet))
  const sachets = sachetParts.map(({ body }) => (kitGroup.add(body), body))
  const tearPieces = sachetParts.map(({ tear }) => (kitGroup.add(tear), tear))
  const TEAR_OFF = SACHET.tearCenter // centro del trozo que se rasga, en x del sobre

  const cup = buildCup()
  kitGroup.add(cup)

  const mCap = new THREE.MeshStandardMaterial({ color: C.teal, roughness: 0.42 })
  const labelMap = tex(tubeLabel())
  const tubes = [0, 1].map(() => {
    const t = buildTube(mCap, labelMap)
    kitGroup.add(t)
    return t
  })

  mark('kit')

  // ── Recorridos ──
  // Dentro de la caja (de pie): la plantilla delante, los sobres, el vaso plegado y encima los tubos.
  const qStandTpl = qEuler(90, 0, 0)
  const qStandSachet = qBasis([0, 1, 0], [0, 0, 1])
  const qStandCup = qBasis([1, 0, 0], [0, 0, 1])
  const UP = 13.6 // altura a la que sale todo por arriba

  const TPLPOSE = pose(0.4, 0, 1.0, 0, -4, 0)
  const tplY = 0.3 + TPL.h / 2
  const tplTrack = new Track(template, inBox(local(0, tplY, 1.18, qStandTpl)), [
    { at: [0.278, 0.318], to: inBox(local(0, tplY + UP, 1.18, qStandTpl)), lift: 0, land: 0, ease: smooth },
    { at: [0.318, 0.402], to: TPLPOSE, lift: 2.5, land: 4, rot: [0.05, 0.85] },
  ])

  const FAN = { pivot: new THREE.Vector3(12.8, 0, 10.6), yaw: [104, 116, 128] }
  const sachetPose = (k) => {
    const yaw = FAN.yaw[k] * DEG
    const lift = 0.13 * k
    const tilt = Math.atan2(lift, SACHET.l - 1.2)
    const dir = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw))
    const center = FAN.pivot.clone().addScaledVector(dir, SACHET.l / 2)
    center.y = 0.075 + lift / 2
    return { pos: center, q: qEuler(0, FAN.yaw[k], -tilt / DEG) }
  }
  const sachetTracks = sachets.map(
    (s, k) =>
      new Track(s, inBox(local(0, 0.4 + SACHET.l / 2, 0.98 - 0.15 * k, qStandSachet)), [
        { at: [0.292, 0.331], to: inBox(local(0, 0.4 + SACHET.l / 2 + UP, 0.98 - 0.15 * k, qStandSachet)), lift: 0, land: 0, ease: smooth },
        {
          at: [0.331, 0.355],
          to: inBox(local((k - 1) * 1.6, 0.4 + SACHET.l / 2 + UP + 0.6, 0.98 - 0.15 * k, qEuler(0, 0, (1 - k) * 20).multiply(qStandSachet))),
          lift: 0.4,
          land: 0.2,
        },
        { at: [0.355 + 0.0106 * k, 0.424 + 0.007 * k], to: sachetPose(k), lift: 1.5, land: 3.2, rot: [0.05, 0.8] },
      ]),
  )

  const CUPPOSE = pose(7.9, 0, -2.6, 0, 0, 0)
  const cupTrack = new Track(cup, inBox(local(0, 3.45, -1.33, qStandCup)), [
    { at: [0.3, 0.34], to: inBox(local(0, 3.45 + UP, -1.33, qStandCup)), lift: 0, land: 0, ease: smooth },
    { at: [0.34, 0.402], to: CUPPOSE, lift: 2, land: 5, rot: [0.05, 0.8] },
  ])

  const tubeTracks = tubes.map(
    (t, i) =>
      new Track(t, inBox(local((i ? 1 : -1) * 0.74, 7.0, -0.5)), [
        { at: [0.305 + 0.007 * i, 0.338 + 0.007 * i], to: inBox(local((i ? 1 : -1) * 0.74, 7.0 + 6.6, -0.5)), lift: 0, land: 0, ease: smooth },
        { at: [0.338 + 0.007 * i, 0.415 + 0.009 * i], to: pose(-15.4 + 0.8 * i, 0.71, 0.6 + 1.65 * i, 0, -12 + 7 * i, -88.6), lift: 2.5, land: 3, rot: [0.05, 0.85] },
      ]),
  )

  // Paso 3: el sobre de arriba se rasga, la tira sale, pasa por el vaso y queda en la plantilla.
  const top = 2
  const SP = sachetPose(top)
  const tearTrack = new Track(tearPieces[top], compose(SP, local(TEAR_OFF, 0, 0)), [
    { at: [0.515, 0.53], to: compose(SP, local(TEAR_OFF + 0.35, 0.25, 0.25, qEuler(14, -28, 8))), lift: 0.15, land: 0.1 },
    { at: [0.53, 0.552], to: compose(SP, local(TEAR_OFF + 1.6, -0.06, 2.3, qEuler(0, -70, 0))), lift: 1.2, land: 0.6 },
  ])
  const qStripInSachet = qEuler(0, 180, 0)
  const qStripDip = qBasis([0, -1, 0], [0, 0, 1])
  const cupC = CUPPOSE.pos
  const dipTop = cupC.clone().setY(STRIP.l + 7.7) // la punta, por encima del borde del vaso
  const dipLow = cupC.clone().setY(STRIP.l + 1.25) // las almohadillas, bajo el nivel de la muestra
  const onTpl = stripOnTemplate()
  const STRIPLAND = compose(TPLPOSE, onTpl)
  const stripTrack = new Track(strip, compose(SP, local(SACHET.handle, -0.04, 0, qStripInSachet)), [
    { at: [0.54, 0.575], to: compose(SP, local(SACHET.handle + STRIP.l + 1.0, 0.06, 0, qStripInSachet)), lift: 0.05, land: 0.12, ease: easeInOut },
    { at: [0.575, 0.606], to: { pos: dipTop, q: qStripDip }, lift: 4, land: 2.5, rot: [0.05, 0.8] },
    { at: [0.606, 0.622], to: { pos: dipLow, q: qStripDip }, lift: 0, land: 0, ease: smooth },
    { at: [0.63, 0.648], to: { pos: dipTop, q: qStripDip }, lift: 0, land: 0, ease: smooth },
    { at: [0.648, 0.7], to: STRIPLAND, lift: 2.5, land: 2.2, rot: [0.15, 0.85] },
  ])

  // Paso 4: el kit se aparta y entran los complementos. El reloj y el tensiómetro se construyen después
  // del primer fotograma, en un rato libre (o en el momento, si el scroll llega antes).
  const KIT_AWAY = new THREE.Vector3(-38, 0, -8)
  const MONPOSE = pose(2.2, 0, 1.6, 0, -8, 0)
  const WATCHPOSE = pose(12.6, 0, 3.4, 0, -26, 0)
  const offIn = (p) => pose(p.pos.x + 32, p.pos.y + 9, p.pos.z - 9, 0, 0, 0)
  let lateP = null
  function loadLate() {
    lateP ??= Promise.all([stripCanvas(DEMO), templateCanvas(768, { clean: true })])
      .then(([demoC, cleanC]) => {
        if (destroyed) return
        strip.userData.setDemo(tex(demoC))
        template.userData.setClean(tex(cleanC))
        sceneDirty = true
        requestFrame()
      })
      .catch((err) => console.warn('Kit 3D: texturas de la tira leída', err))
    return lateP
  }

  let extras = null
  function buildExtras() {
    if (extras || destroyed) return extras
    const watch = buildWatch(tex(watchDisplay()))
    const monitor = buildMonitor(tex(monitorLCD()))
    watch.visible = monitor.visible = false
    scene.add(watch, monitor)
    extras = {
      watch,
      monitor,
      tracks: [
        new Track(monitor, compose(offIn(MONPOSE), local(0, 0, 0, qEuler(0, 30, 0))), [
          { at: [0.797, 0.898], to: MONPOSE, lift: 0, land: 2.4, ease: easeOut },
        ]),
        new Track(watch, compose(offIn(WATCHPOSE), local(0, 0, 0, qEuler(0, 20, 0))), [
          { at: [0.825, 0.93], to: WATCHPOSE, lift: 0, land: 2, ease: easeOut },
        ]),
      ],
    }
    return extras
  }

  // ── Cámara ──
  // Cada clave encuadra una caja del mundo (min, max) desde un acimut y una elevación; la distancia se
  // busca para que las ocho esquinas quepan, sea cual sea la proporción del contenedor. Se interpola con
  // curvas de Hermite y velocidad nula en las claves de reposo.
  const bx = BOXPOSE.pos
  const BOXV = [
    [bx.x - 3.9, 0, bx.z - 2.8],
    [bx.x + 3.9, BOX.h + 0.3, bx.z + 2.8],
  ]
  const RISE = [
    [bx.x - 6, 0, bx.z - 4],
    [bx.x + 6, tplY + UP + TPL.h / 2, bx.z + 4],
  ]
  const ALL = [
    [-15.8, 0, -8.2],
    [14.4, 12.6, 12],
  ]
  // la plantilla con la tira puesta (el vaso asoma por la esquina)
  const tp = TPLPOSE.pos
  const TPLV = [
    [tp.x - TPL.w / 2 - 0.5, 0, tp.z - TPL.h / 2 - 0.45],
    [tp.x + TPL.w / 2 + 0.5, 0.6, tp.z + TPL.h / 2 + 0.45],
  ]
  const DEV = [
    [-15.2, 0, -8.2],
    [15.2, 6.5, 8.6],
  ]
  const KEYS = [
    { p: 0, b: BOXV, az: 64, el: 18, m: 0.74, rest: true },
    { p: 0.24, b: BOXV, az: 40, el: 20, m: 0.74, rest: true },
    { p: 0.324, b: RISE, az: 22, el: 20, m: 0.8 },
    { p: 0.44, b: ALL, az: 10, el: 34, m: 0.9, rest: true },
    { p: 0.515, b: ALL, az: 8, el: 35, m: 0.9, rest: true },
    { p: 0.565, b: [[-3, 0, -6.6], [14.4, 4, 12]], az: 6, el: 38, m: 0.88 },
    { p: 0.625, b: [[-3, 0, -6.6], [11.8, STRIP.l + 8, 5]], az: 2, el: 26, m: 0.86 },
    { p: 0.708, b: TPLV, az: -4, el: 70, m: 0.86, rest: true },
    { p: 0.765, b: TPLV, az: -4, el: 70, m: 0.86, rest: true },
    { p: 0.807, b: [[-22, 0, -11], [22, 8, 10]], az: -2, el: 36, m: 0.9 },
    { p: 0.93, b: DEV, az: -4, el: 26, m: 0.88, rest: true },
    { p: 1, b: DEV, az: -4, el: 26, m: 0.88, rest: true },
  ]
  const keyVals = KEYS.map((k) => [...k.b[0], ...k.b[1], k.az, k.el, k.m])
  const NV = keyVals[0].length
  const keyTan = KEYS.map((k, i) =>
    keyVals[i].map((_, j) => {
      if (k.rest || i === 0 || i === KEYS.length - 1) return 0
      return (keyVals[i + 1][j] - keyVals[i - 1][j]) / (KEYS[i + 1].p - KEYS[i - 1].p)
    }),
  )
  const camVals = new Array(NV).fill(0)
  const cam = { min: new THREE.Vector3(), max: new THREE.Vector3(), az: 0, el: 0, m: 0.8 }
  function cameraAt(p) {
    let i = 0
    while (i < KEYS.length - 2 && p > KEYS[i + 1].p) i++
    const h = KEYS[i + 1].p - KEYS[i].p
    const t = clamp((p - KEYS[i].p) / h)
    const t2 = t * t
    const t3 = t2 * t
    const h00 = 2 * t3 - 3 * t2 + 1
    const h10 = t3 - 2 * t2 + t
    const h01 = -2 * t3 + 3 * t2
    const h11 = t3 - t2
    for (let j = 0; j < NV; j++) camVals[j] = h00 * keyVals[i][j] + h10 * h * keyTan[i][j] + h01 * keyVals[i + 1][j] + h11 * h * keyTan[i + 1][j]
    cam.min.set(camVals[0], camVals[1], camVals[2])
    cam.max.set(camVals[3], camVals[4], camVals[5])
    cam.az = camVals[6]
    cam.el = camVals[7]
    cam.m = camVals[8]
  }

  const par = { x: 0, y: 0, tx: 0, ty: 0 }
  const _dir = new THREE.Vector3()
  const _tgt = new THREE.Vector3()
  const _corner = new THREE.Vector3()
  function fits(dist) {
    camera.position.copy(_tgt).addScaledVector(_dir, dist)
    camera.lookAt(_tgt)
    camera.updateMatrixWorld()
    for (let i = 0; i < 8; i++) {
      _corner.set(i & 1 ? cam.max.x : cam.min.x, i & 2 ? cam.max.y : cam.min.y, i & 4 ? cam.max.z : cam.min.z)
      _corner.applyMatrix4(camera.matrixWorldInverse)
      if (_corner.z > -1) return false // detrás de la cámara o pegado a ella
      _corner.applyMatrix4(camera.projectionMatrix)
      if (Math.abs(_corner.x) > cam.m || Math.abs(_corner.y) > cam.m) return false
    }
    return true
  }
  function placeCamera() {
    const az = (cam.az + par.x * 3) * DEG
    const el = (cam.el - par.y * 2) * DEG
    _dir.set(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el))
    _tgt.addVectors(cam.min, cam.max).multiplyScalar(0.5)
    camera.near = 0.5
    camera.far = 5000
    camera.updateProjectionMatrix()
    let lo = 2
    let hi = 1200
    for (let i = 0; i < 26; i++) {
      const mid = (lo + hi) / 2
      if (fits(mid)) hi = mid
      else lo = mid
    }
    camera.position.copy(_tgt).addScaledVector(_dir, hi)
    camera.lookAt(_tgt)
    camera.near = Math.max(0.5, hi * 0.2)
    camera.far = hi * 3 + 150
    camera.updateProjectionMatrix()
  }

  // ── Estado ──
  const state = { p: clamp(+o.progress || 0), target: clamp(+o.progress || 0) }
  let sceneDirty = true

  function applyProgress(p) {
    box.userData.open(seg(p, 0.252, 0.305))
    tplTrack.update(p)
    sachetTracks.forEach((t) => t.update(p))
    // los trozos que se rasgan siguen a su sobre hasta que toca rasgar el de arriba
    tearPieces.forEach((piece, k) => {
      if (k === top && p > 0.5) tearTrack.update(p)
      else {
        piece.position.set(TEAR_OFF, 0, 0).applyQuaternion(sachets[k].quaternion).add(sachets[k].position)
        piece.quaternion.copy(sachets[k].quaternion)
      }
    })
    cupTrack.update(p)
    cup.userData.expand(easeOutBack(seg(p, 0.396, 0.44)))
    cup.userData.fill(seg(p, 0.5, 0.535))
    tubeTracks.forEach((t) => t.update(p))
    strip.visible = p > 0.5
    stripTrack.update(p)
    strip.userData.develop.value = smooth(seg(p, 0.652, 0.69))
    template.userData.stripOn(smooth(seg(p, 0.692, 0.708)))
    const away = easeInOut(seg(p, 0.752, 0.839))
    kitGroup.position.copy(KIT_AWAY).multiplyScalar(away)
    kitGroup.visible = away < 0.999
    if (p > 0.5) loadLate()
    if (p > 0.75) buildExtras()
    if (extras) {
      extras.tracks.forEach((t) => t.update(p))
      extras.monitor.visible = extras.watch.visible = p > 0.797
    }
    cameraAt(p)
  }

  function draw() {
    if (sceneDirty) {
      contact.update(scene, [floor])
      renderer.shadowMap.needsUpdate = true
      sceneDirty = false
    }
    placeCamera()
    renderer.render(scene, camera)
  }

  // ── Bucle a demanda ──
  let raf = 0
  let last = 0
  let visible = true
  let destroyed = false
  function requestFrame() {
    if (!raf && !destroyed) raf = requestAnimationFrame(frame)
  }
  function frame(now) {
    raf = 0
    const dt = last ? Math.min(0.1, (now - last) / 1000) : 1 / 60
    last = now
    let moving = false
    if (state.p !== state.target) {
      if (o.smoothing > 0) {
        state.p += (state.target - state.p) * (1 - Math.exp(-dt / o.smoothing))
        if (Math.abs(state.target - state.p) < 2e-4) state.p = state.target
      } else state.p = state.target
      applyProgress(state.p)
      sceneDirty = true
      moving = state.p !== state.target
    }
    if (o.parallax) {
      const a = 1 - Math.exp(-dt / 0.45)
      par.x += (par.tx - par.x) * a
      par.y += (par.ty - par.y) * a
      if (Math.abs(par.tx - par.x) + Math.abs(par.ty - par.y) > 2e-3) moving = true
      else {
        par.x = par.tx
        par.y = par.ty
      }
    }
    if (visible) draw()
    if (moving && visible) requestFrame()
    else last = 0
  }

  function resize() {
    const w = Math.max(1, container.clientWidth)
    const h = Math.max(1, container.clientHeight)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, o.maxPixelRatio))
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    requestFrame()
  }

  applyProgress(state.p)
  const w0 = Math.max(1, container.clientWidth)
  const h0 = Math.max(1, container.clientHeight)
  renderer.setSize(w0, h0, false)
  camera.aspect = w0 / h0
  placeCamera()
  mark('geometria')
  // compilación en paralelo si el navegador la ofrece; si no, se compila con el primer fotograma
  const parallel = !!renderer.compileAsync && renderer.extensions.has('KHR_parallel_shader_compile')
  if (parallel) await renderer.compileAsync(scene, camera)
  mark('shaders')
  if (destroyed) return null

  const ro = new ResizeObserver(resize)
  ro.observe(container)
  const io = new IntersectionObserver(
    (entries) => {
      visible = entries[entries.length - 1].isIntersecting
      if (visible) requestFrame()
    },
    { rootMargin: '120px' },
  )
  io.observe(container)
  const onPointer = (e) => {
    if (!o.parallax || e.pointerType !== 'mouse' || !visible) return
    const r = container.getBoundingClientRect()
    par.tx = clamp(((e.clientX - r.left) / r.width) * 2 - 1, -1, 1)
    par.ty = clamp(((e.clientY - r.top) / r.height) * 2 - 1, -1, 1)
    requestFrame()
  }
  const onLeave = () => {
    par.tx = par.ty = 0
    requestFrame()
  }
  window.addEventListener('pointermove', onPointer, { passive: true })
  document.documentElement.addEventListener('pointerleave', onLeave)
  const onLost = (e) => {
    e.preventDefault()
    destroyed = true
  }
  canvas.addEventListener('webglcontextlost', onLost)

  draw()
  mark('primer fotograma')
  // el resto (complementos, tira leída y plantilla limpia), cuando el navegador tenga un rato libre
  let readyDone
  const ready = new Promise((r) => (readyDone = r))
  const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 300))
  idle(
    async () => {
      if (!destroyed) {
        buildExtras()
        applyProgress(state.p)
        await Promise.all([loadLate(), parallel ? renderer.compileAsync(scene, camera).catch(() => {}) : null])
        timings.completo = Math.round(performance.now() - t0)
        sceneDirty = true
        requestFrame()
      }
      readyDone()
    },
    { timeout: 1500 },
  )

  return {
    timings,
    /** Se cumple cuando ya está todo (complementos y texturas tardías): para las imágenes fijas. */
    ready,
    setProgress(p, { immediate = false } = {}) {
      const v = clamp(Number(p) || 0)
      state.target = v
      if (immediate || !(o.smoothing > 0)) {
        state.p = v
        applyProgress(v)
        sceneDirty = true
      }
      requestFrame()
    },
    get progress() {
      return state.target
    },
    snapshot(type = 'image/png') {
      state.p = state.target
      applyProgress(state.p)
      sceneDirty = true
      draw()
      return canvas.toDataURL(type)
    },
    destroy() {
      if (destroyed && !canvas.isConnected) return
      destroyed = true
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
      window.removeEventListener('pointermove', onPointer)
      document.documentElement.removeEventListener('pointerleave', onLeave)
      canvas.removeEventListener('webglcontextlost', onLost)
      const mats = new Set()
      scene.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose()
        if (obj.material) [].concat(obj.material).forEach((m) => mats.add(m))
      })
      mats.forEach((m) => {
        for (const v of Object.values(m)) if (v && v.isTexture) v.dispose()
        m.dispose()
      })
      textures.forEach((t) => t.dispose())
      contact.dispose()
      envRT.dispose()
      renderer.dispose()
      renderer.forceContextLoss()
      canvas.remove()
    },
  }
}

export { C as PALETTE }
