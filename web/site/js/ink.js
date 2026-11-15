// Tinta que se expande: una gota de tinta sobre papel húmedo, en WebGL2 y sin dependencias.
//
// Cómo funciona. Al crear la tinta se calcula una sola vez (en un worker) el tiempo de llegada T de
// la tinta a cada punto: se resuelve la ecuación eikonal |∇T| = 1/v por fast marching sobre una
// rejilla, con una velocidad v que cambia con el papel (zonas más húmedas, canales, fibras). Cada
// fotograma es solo una lectura de ese campo: hay tinta donde T < t. Por eso los dedos avanzan a
// velocidades distintas, la forma cambia al crecer en vez de escalarse, el scroll puede ir hacia
// atrás y cada fotograma cuesta poco. El shader pone lo que la rejilla no resuelve: deformación del
// dominio con fbm, detalle fractal del borde, zarcillos, borde más oscuro, halo diluido por delante,
// líneas de marea, nubes de densidad, vetas del flujo y granulado del pigmento. Los colores se
// mezclan como tintes (Beer-Lambert: se suman absorbancias), así amarillo y verde azulado dan verde.
//
//   const ink = createInk(el, { colors: ['#c8de6e', '#0b7774'], opacity: 0.26, duration: 7000 })
//   ink.play()
//
// Opciones:
//   color      un solo color de tinta.
//   colors     de 2 a 6 colores de una escala; sustituye a `color`.
//   colorMode  'edge': del primero en el borde al último en el centro (la mancha vira con el
//              tiempo); 'zones': por zonas, con franjas de mezcla.
//   opacity    densidad máxima; con 1 y `cover` se llega justo a `color` (o al último de `colors`).
//   origin     punto de partida, 0-1 del contenedor; puede caer fuera.
//   seed       semilla: la misma da siempre la misma mancha.
//   mode       'time' (se reproduce con play()) o 'scroll' (la mueve setProgress()).
//   duration   ms de play().
//   cover      con avance 1 cubre todo el contenedor, de un color uniforme (para transiciones).
//   flat       con cover y false: lo cubre todo pero no se aplana al final; se queda como una
//              aguada con textura (nubes, granulado, vetas, líneas de marea suaves).
//   radius     sin cover: radio medio final, en fracción del lado menor del contenedor; o
//              [rx, ry], en fracciones del ancho y del alto, para una mancha elíptica.
//   sync       solo para pruebas y capturas: calcula y compila en el hilo principal, sin worker ni
//              compilación en paralelo, para que la imagen esté lista en el primer fotograma.
//
// Devuelve { setProgress(p), play(), destroy() }; play() devuelve una promesa que se cumple al acabar.

const DEFAULTS = {
  color: '#0b7774',
  colors: null,
  colorMode: 'edge',
  opacity: 1,
  origin: [0.5, 0.5],
  seed: 1,
  mode: 'time',
  duration: 4000,
  cover: false,
  flat: true,
  radius: 0.42,
}
const MAX_COLORS = 6

// Aspecto según el uso: mancha suelta (acuarela), tinta que lo cubre todo y acaba plana
// (transición) o que lo cubre todo y se queda como aguada con textura (fondo de sección).
const LOOK = {
  bloom: { rim: 0.6, halo: 0.16, tendril: 4, grain: 0.16, inner: 0.55, tide: 0.14, cloud: 0.18, soft: 0.7, fringe: 0.3, fringeW: 6, sat: 0, flow: 0.015 },
  cover: { rim: 0.35, halo: 0.12, tendril: 6, grain: 0.12, inner: 0.72, tide: 0.06, cloud: 0.16, soft: 0.45, fringe: 0.4, fringeW: 7, sat: 0.3, flow: 0.045 },
  wash: { rim: 0.45, halo: 0.14, tendril: 5, grain: 0.16, inner: 0.62, tide: 0.12, cloud: 0.26, soft: 0.6, fringe: 0.32, fringeW: 6, sat: 0, flow: 0.04 },
}

const TAU = Math.PI * 2

// ------------------------------------------------------------------------------- ruido en la CPU
// Todo lo que va de aquí a buildField es puro: se copia tal cual al worker.
function hash(x, y, s) {
  let h = Math.imul(x | 0, 0x27d4eb2d) ^ Math.imul(y | 0, 0x165667b1) ^ Math.imul(s | 0, 0x9e3779b1)
  h = Math.imul(h ^ (h >>> 15), 0x85ebca6b)
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35)
  return (h ^ (h >>> 16)) >>> 0
}

function rng(seed) {
  let a = hash(seed, 0x5bd1, 0x2f) | 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const GX = new Float32Array(64)
const GY = new Float32Array(64)
for (let i = 0; i < 64; i++) {
  GX[i] = Math.cos((i / 64) * TAU)
  GY[i] = Math.sin((i / 64) * TAU)
}
const PERM = new Uint8Array(512)
{
  const r = rng(12345)
  const p = Array.from({ length: 256 }, (_, i) => i)
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(r() * (i + 1))
    ;[p[i], p[j]] = [p[j], p[i]]
  }
  for (let i = 0; i < 512; i++) PERM[i] = p[i & 255]
}

// Ruido de gradiente 2D en [-0,71, 0,71]; se repite cada `per` celdas (64, 128 o 256).
function perlin(x, y, s = 0, per = 256) {
  const fx0 = Math.floor(x)
  const fy0 = Math.floor(y)
  const fx = x - fx0
  const fy = y - fy0
  const m = per - 1
  const x0 = (fx0 + s) & m
  const y0 = (fy0 + s * 7) & m
  const x1 = (x0 + 1) & m
  const y1 = (y0 + 1) & m
  const a = PERM[PERM[x0] + y0] & 63
  const b = PERM[PERM[x1] + y0] & 63
  const c = PERM[PERM[x0] + y1] & 63
  const d = PERM[PERM[x1] + y1] & 63
  const na = GX[a] * fx + GY[a] * fy
  const nb = GX[b] * (fx - 1) + GY[b] * fy
  const nc = GX[c] * fx + GY[c] * (fy - 1)
  const nd = GX[d] * (fx - 1) + GY[d] * (fy - 1)
  const u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
  const v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
  const ab = na + u * (nb - na)
  return ab + v * (nc + u * (nd - nc) - ab)
}

// fbm normalizado a desviación típica ≈ 1, con giro entre octavas para que no se alinee con la rejilla.
function fbm(x, y, s, oct) {
  let sum = 0
  let amp = 1
  let norm = 0
  for (let o = 0; o < oct; o++) {
    sum += amp * perlin(x, y, s + o * 101)
    norm += amp * amp
    const nx = 1.6 * x - 1.2 * y + 3.1
    y = 1.2 * x + 1.6 * y - 1.7
    x = nx
    amp *= 0.5
  }
  return sum / (0.21 * Math.sqrt(norm))
}

// Crestas: 1 sobre las líneas donde el ruido pasa por cero, 0 lejos de ellas.
function ridge(x, y, s) {
  const n = 1 - Math.min(1, Math.abs(perlin(x, y, s)) * 2.4)
  return n * n
}

// Textura de ruido compartida (256², se repite): RGB, ruido de gradiente con celdas de 4 texels;
// A, grano fino del papel.
let NOISE = null
function noiseData() {
  if (NOISE) return NOISE
  const S = 256
  const d = new Uint8Array(S * S * 4)
  const to8 = (n) => Math.max(0, Math.min(255, Math.round(127.5 + n * 180)))
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      const i = (y * S + x) * 4
      d[i] = to8(perlin(x / 4, y / 4, 11, 64))
      d[i + 1] = to8(perlin(x / 4, y / 4, 23, 64))
      d[i + 2] = to8(perlin(x / 4, y / 4, 37, 64))
      d[i + 3] = to8(perlin(x / 2, y / 2, 53, 128) * 0.85 + (hash(x, y, 71) / 4294967296 - 0.5) * 0.32)
    }
  }
  return (NOISE = d)
}

// ------------------------------------------------------------------------- el papel y la tinta
// Velocidad de la tinta en cada celda (unidades: lados del contenedor por unidad de tiempo): zonas
// más o menos húmedas (fbm en escala logarítmica), canales y fibras (crestas) y una ligera
// inclinación del papel. Sus rasgos miden más de 10 celdas: se evalúa a media resolución.
function speedField(W, H, wL, hL, seed, cover) {
  const r = rng(seed)
  const s = (seed * 7919) & 255
  const ox = r() * 40
  const oy = r() * 40
  const ang = r() * TAU
  const bx = Math.cos(ang)
  const by = Math.sin(ang)
  const kBig = cover ? 0.36 : 0.42
  const kMid = cover ? 0.26 : 0.22
  const W2 = (W >> 1) + 2
  const H2 = (H >> 1) + 2
  const C = new Float32Array(W2 * H2)
  for (let j = 0; j < H2; j++) {
    const Y = ((2 * j + 0.5) / H) * hL
    for (let i = 0; i < W2; i++) {
      const X = ((2 * i + 0.5) / W) * wL
      const big = fbm(X * 1.7 + ox, Y * 1.7 + oy, s, 3)
      const mid = fbm(X * 5.5 - oy, Y * 5.5 + ox, s + 7, 3)
      const r1 = ridge(X * 8 + ox, Y * 8 - ox, s + 13)
      const r2 = ridge(X * 21 - oy, Y * 21 + oy, s + 19)
      const lv = kBig * big + kMid * mid + 0.3 * (X * bx + Y * by)
      const v = Math.exp(lv) * (1 + 0.8 * r1 * r1 * r1 + 0.5 * r2 * r2 * r2 * r2)
      C[j * W2 + i] = Math.min(5, Math.max(0.2, v))
    }
  }
  const F = new Float32Array(W * H)
  for (let j = 0; j < H; j++) {
    const j2 = j >> 1
    const ty = (j & 1) * 0.5
    for (let i = 0; i < W; i++) {
      const i2 = i >> 1
      const tx = (i & 1) * 0.5
      const k = j2 * W2 + i2
      const top = C[k] + (C[k + 1] - C[k]) * tx
      const bot = C[k + W2] + (C[k + W2 + 1] - C[k + W2]) * tx
      F[j * W + i] = top + (bot - top) * ty
    }
  }
  return F
}

// Fast marching (primer orden, con la plantilla de los ejes y la de las diagonales).
function arrivalTimes(F, W, H, hc, ox, oy) {
  const N = W * H
  const T = new Float64Array(N).fill(Infinity)
  const K = new Uint8Array(N)
  let cap = N * 2 + 64
  let hk = new Float64Array(cap)
  let hv = new Int32Array(cap)
  let n = 0
  let popKey = 0

  const push = (key, v) => {
    if (n === cap) {
      cap *= 2
      const k2 = new Float64Array(cap)
      k2.set(hk)
      hk = k2
      const v2 = new Int32Array(cap)
      v2.set(hv)
      hv = v2
    }
    let i = n++
    while (i > 0) {
      const p = (i - 1) >> 1
      if (hk[p] <= key) break
      hk[i] = hk[p]
      hv[i] = hv[p]
      i = p
    }
    hk[i] = key
    hv[i] = v
  }
  const pop = () => {
    const top = hv[0]
    popKey = hk[0]
    const key = hk[--n]
    const v = hv[n]
    let i = 0
    for (;;) {
      let c = 2 * i + 1
      if (c >= n) break
      if (c + 1 < n && hk[c + 1] < hk[c]) c++
      if (hk[c] >= key) break
      hk[i] = hk[c]
      hv[i] = hv[c]
      i = c
    }
    hk[i] = key
    hv[i] = v
    return top
  }
  const quad = (a, b, f) => {
    if (a > b) {
      const t = a
      a = b
      b = t
    }
    if (b - a >= f) return a + f
    return 0.5 * (a + b + Math.sqrt(2 * f * f - (b - a) * (b - a)))
  }
  const solve = (i) => {
    const x = i % W
    const y = (i - x) / W
    const f = hc / F[i]
    let a = Infinity
    let b = Infinity
    let c = Infinity
    let d = Infinity
    if (x > 0) {
      if (K[i - 1]) a = T[i - 1]
      if (y > 0 && K[i - W - 1]) c = T[i - W - 1]
      if (y < H - 1 && K[i + W - 1]) d = T[i + W - 1]
    }
    if (x < W - 1) {
      if (K[i + 1] && T[i + 1] < a) a = T[i + 1]
      if (y < H - 1 && K[i + W + 1] && T[i + W + 1] < c) c = T[i + W + 1]
      if (y > 0 && K[i - W + 1] && T[i - W + 1] < d) d = T[i - W + 1]
    }
    if (y > 0 && K[i - W]) b = T[i - W]
    if (y < H - 1 && K[i + W] && T[i + W] < b) b = T[i + W]
    return Math.min(quad(a, b, f), quad(c, d, f * Math.SQRT2))
  }

  // Semillas: las celdas cercanas al origen (o, si cae fuera, la franja del borde más cercana).
  const ex = Math.max(0, -ox, ox - W)
  const ey = Math.max(0, -oy, oy - H)
  const rs = Math.hypot(ex, ey) + 1.5
  const x0 = Math.max(0, Math.floor(ox - rs))
  const x1 = Math.min(W - 1, Math.ceil(ox + rs))
  const y0 = Math.max(0, Math.floor(oy - rs))
  const y1 = Math.min(H - 1, Math.ceil(oy + rs))
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dist = Math.hypot(x + 0.5 - ox, y + 0.5 - oy)
      if (dist > rs) continue
      const i = y * W + x
      T[i] = (dist * hc) / F[i]
      push(T[i], i)
    }
  }

  while (n) {
    const i = pop()
    if (K[i] || popKey > T[i]) continue
    K[i] = 1
    const x = i % W
    const y = (i - x) / W
    for (let dy = -1; dy <= 1; dy++) {
      const yy = y + dy
      if (yy < 0 || yy >= H) continue
      for (let dx = -1; dx <= 1; dx++) {
        const xx = x + dx
        if (xx < 0 || xx >= W || (dx === 0 && dy === 0)) continue
        const j = yy * W + xx
        if (K[j]) continue
        const t = solve(j)
        if (t < T[j]) {
          T[j] = t
          push(t, j)
        }
      }
    }
  }
  return T
}

// Desenfoque por cajas separable con suma móvil, repetido: aproxima un gaussiano.
function blur(src, W, H, r, passes) {
  const a = Float32Array.from(src)
  const b = new Float32Array(W * H)
  const inv = 1 / (2 * r + 1)
  for (let p = 0; p < passes; p++) {
    for (let y = 0; y < H; y++) {
      const row = y * W
      let s = a[row] * (r + 1)
      for (let k = 1; k <= r; k++) s += a[row + Math.min(W - 1, k)]
      for (let x = 0; x < W; x++) {
        b[row + x] = s * inv
        s += a[row + Math.min(W - 1, x + r + 1)] - a[row + Math.max(0, x - r)]
      }
    }
    for (let x = 0; x < W; x++) {
      let s = b[x] * (r + 1)
      for (let k = 1; k <= r; k++) s += b[Math.min(H - 1, k) * W + x]
      for (let y = 0; y < H; y++) {
        a[y * W + x] = s * inv
        s += b[Math.min(H - 1, y + r + 1) * W + x] - b[Math.max(0, y - r) * W + x]
      }
    }
  }
  return a
}

function smoothstep(a, b, x) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

function detailUnit(L) {
  return Math.min(1.8, Math.max(0.16, L / 1100))
}

// Campo completo para un contenedor de cw × h px: tiempos de llegada y cómo avanza el frente. Con
// `radius: [rx, ry]` la mancha es elíptica: el campo se calcula en un espacio estirado (sx) y se
// encaja en el contenedor.
function buildField(cw, h, o, look) {
  const t0 = performance.now()
  const sx = !o.cover && Array.isArray(o.radius) ? Math.min(3, Math.max(1 / 3, (o.radius[0] * cw) / (o.radius[1] * h))) : 1
  const w = cw / sx
  const L = Math.max(w, h)
  const G = Math.round(Math.min(256, Math.max(40, L / 5.5)))
  const W = Math.max(8, Math.round((G * w) / L))
  const H = Math.max(8, Math.round((G * h) / L))
  const wL = w / L
  const hL = h / L
  const hc = wL / W
  const F = speedField(W, H, wL, hL, o.seed, o.cover)
  const T = arrivalTimes(F, W, H, hc, o.origin[0] * W, o.origin[1] * H)
  const Tb = blur(T, W, H, 3, 3)
  const Vb = blur(F, W, H, 1, 1)

  // Escala de tiempo: con cover, lo que tarda en llegar al último rincón (más un margen para el
  // detalle del borde); sin cover, lo que tarda de mediana en recorrer el radio.
  let tEnd
  let margin = 0
  let vMin = Infinity
  let tMax = 0
  for (let i = 0; i < W * H; i++) {
    if (T[i] > tMax) tMax = T[i]
    if (Vb[i] < vMin) vMin = Vb[i]
  }
  const u = detailUnit(Math.max(cw, h))
  if (o.cover) {
    margin = ((14 + look.tendril) * u + 4 + look.soft) / (L * Math.max(0.2, vMin))
    tEnd = tMax + margin
  } else {
    const R = (Array.isArray(o.radius) ? o.radius[1] * h : o.radius * Math.min(cw, h)) / L
    const ratios = []
    const ocx = o.origin[0] * wL
    const ocy = o.origin[1] * hL
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const r = Math.hypot(((x + 0.5) / W) * wL - ocx, ((y + 0.5) / H) * hL - ocy)
        if (r > 0.6 * R && r < R) ratios.push(T[y * W + x] / r)
      }
    }
    ratios.sort((p, q) => p - q)
    tEnd = R * (ratios.length ? ratios[ratios.length >> 1] : 1)
  }

  // Avance → frente: la superficie manchada crece en proporción al avance, como en la imbibición
  // capilar (Washburn: área ∝ tiempo). Tabla de cuantiles de T dentro de la mancha final, sacada
  // de una muestra de una de cada cuatro celdas.
  const sample = (src) => {
    const out = new Float32Array(Math.ceil(src.length / 4))
    for (let i = 0, j = 0; i < src.length; i += 4, j++) out[j] = src[i]
    return out.sort()
  }
  const sorted = sample(T)
  let count = sorted.length
  if (!o.cover) {
    let lo = 0
    let hi = sorted.length
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (sorted[mid] <= tEnd) lo = mid + 1
      else hi = mid
    }
    count = Math.max(2, lo)
  }
  const quant = new Float32Array(65)
  for (let i = 0; i <= 64; i++) quant[i] = sorted[Math.min(count - 1, Math.round((i / 64) * (count - 1)))]
  quant[0] = 0
  if (!o.cover) quant[64] = tEnd
  const vSorted = sample(Vb)
  const vMed = vSorted[vSorted.length >> 1]

  // Textura: R + G = T (parte gruesa exacta en media precisión + resto), B = T suavizado, A = v.
  const data = new Float32Array(W * H * 4)
  for (let i = 0; i < W * H; i++) {
    const t = Math.min(T[i], 3.99)
    const hi = Math.round(t * 512) / 512
    data[i * 4] = hi
    data[i * 4 + 1] = t - hi
    data[i * 4 + 2] = Tb[i]
    data[i * 4 + 3] = Vb[i]
  }
  // Lt: px del contenedor por unidad de T (en el espacio estirado, media geométrica de los ejes).
  return { W, H, data, tEnd, margin, quant, vMed, w: cw, h, Lt: L * Math.sqrt(sx), ms: performance.now() - t0 }
}

// ----------------------------------------------------------------- el cálculo, fuera del hilo
// Un worker compartido calcula los campos (de 20 a 60 ms cada uno en un portátil) sin bloquear la
// página. Si no se puede crear (p. ej., una CSP que no deja workers de blob:), se calcula aquí.
let worker = null
let workerOff = typeof Worker === 'undefined'
let nextId = 0
const waiting = new Map()

function workerSource() {
  const fns = [hash, rng, perlin, fbm, ridge, noiseData, speedField, arrivalTimes, blur, smoothstep, detailUnit, buildField]
  return [
    `const TAU = Math.PI * 2;`,
    `const GX = new Float32Array([${GX}]);`,
    `const GY = new Float32Array([${GY}]);`,
    `const PERM = new Uint8Array([${PERM}]);`,
    `let NOISE = null;`,
    ...fns.map(String),
    `onmessage = (e) => {
      const { id, w, h, o, look, noise } = e.data;
      const field = buildField(w, h, o, look);
      postMessage({ id, field, noise: noise ? noiseData() : null }, [field.data.buffer]);
    };`,
  ].join('\n')
}

function localField({ w, h, o, look }) {
  noiseData()
  return buildField(w, h, o, look)
}

function stopWorker() {
  workerOff = true
  worker?.terminate()
  worker = null
  for (const [, job] of waiting) job.resolve(localField(job.args))
  waiting.clear()
}

function requestField(args, sync) {
  if (sync) return Promise.resolve(localField(args))
  return new Promise((resolve) => {
    if (!worker && !workerOff) {
      try {
        const url = URL.createObjectURL(new Blob([workerSource()], { type: 'text/javascript' }))
        worker = new Worker(url)
        setTimeout(() => URL.revokeObjectURL(url), 30000)
        worker.onmessage = (e) => {
          const job = waiting.get(e.data.id)
          waiting.delete(e.data.id)
          if (e.data.noise && !NOISE) NOISE = e.data.noise
          job?.resolve(e.data.field)
        }
        worker.onerror = (e) => {
          e.preventDefault?.()
          stopWorker()
        }
      } catch {
        stopWorker()
      }
    }
    if (workerOff) {
      setTimeout(() => resolve(localField(args)), 0)
      return
    }
    const id = ++nextId
    waiting.set(id, { resolve, args })
    worker.postMessage({ id, ...args, noise: !NOISE })
  })
}

// Posición del frente para un avance p (0-1).
function frontAt(field, p) {
  const x = Math.min(1, Math.max(0, p)) * 64
  const i = Math.min(63, Math.floor(x))
  const f = x - i
  const t = field.quant[i] * (1 - f) + field.quant[i + 1] * f
  return t + field.margin * smoothstep(0.82, 1, p)
}

// ------------------------------------------------------------------------------------- shaders
const VERT = `#version 300 es
out vec2 vUv;
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`

const FRAG = `#version 300 es
precision highp float;
precision highp sampler2D;

uniform sampler2D uField;  // R + G: T, B: T suavizado, A: velocidad
uniform sampler2D uNoise;  // RGB: ruido (celda de 4 texels), A: grano (celda de 2)
uniform vec2 uOrigin;      // origen, px CSS
uniform vec2 uSize;        // contenedor, px CSS
uniform float uL;          // px CSS por unidad de T
uniform float uU;          // unidad de detalle
uniform float uPx;         // px CSS por píxel del canvas
uniform float uT;          // posición del frente
uniform float uTEnd;       // posición del frente con avance 1
uniform float uVm;         // velocidad mediana
uniform float uFill;       // llenado final (cover)
uniform float uSatAge;     // edad a la que la tinta se vuelve uniforme (cover); 0, nunca
uniform float uOpacity;
uniform float uChroma;     // 0: mezcla con blanco; 1: Beer-Lambert
uniform vec3 uKs[${MAX_COLORS}];        // absorbancia de cada color de la escala
uniform int uNK;           // cuántos colores
uniform int uMode;         // 0: del borde al centro; 1: por zonas
uniform vec4 uOff;         // desplazamientos del ruido según la semilla
uniform vec3 uTide;        // frentes antiguos que dejan línea de marea
uniform vec4 uS1;          // borde, halo, zarcillos (px), granulado
uniform vec4 uS2;          // densidad interior, mareas, nubes, suavidad del borde (px)
uniform vec4 uS3;          // flecos: densidad, ancho (px); vetas del flujo dentro

in vec2 vUv;
out vec4 outColor;

const mat2 R1 = mat2(0.8, 0.6, -0.6, 0.8);
const mat2 R2 = mat2(0.28, 0.96, -0.96, 0.28);

// Ruido con celda de c px: RGB tiene 64 celdas por baldosa; A, 128. Normalizado a σ ≈ 1.
vec4 nz(vec2 p, float c) { return (texture(uNoise, p / (c * 64.0)) - 0.5) * 7.0; }
float gr(vec2 p, float c) { return (texture(uNoise, p / (c * 128.0)).a - 0.5) * 7.0; }

// Hebras: ruido que solo depende del ángulo alrededor del origen (constante a lo largo de cada rayo,
// así los zarcillos nacen del borde y no quedan islas) y de unos w px de ancho a cualquier distancia:
// octavas angulares que se funden según el radio, de modo que las hebras se bifurcan al alejarse.
float hairs(vec2 from, float r, float w, float off) {
  float lv = log2(max(r, 2.0 * w) / w);
  float n0 = floor(lv);
  float f = lv - n0;
  vec2 c = from / max(length(from), 1e-4);
  vec2 o0 = vec2(off) + n0 * vec2(0.37, 0.71);
  float h0 = textureLod(uNoise, c * exp2(n0) / 64.0 + o0, 0.0).b;
  float h1 = textureLod(uNoise, c * exp2(n0 + 1.0) / 64.0 + o0 + vec2(0.37, 0.71), 0.0).b;
  return (mix(h0, h1, f) - 0.5) * 7.0 / sqrt(f * f + (1.0 - f) * (1.0 - f));
}

// Absorbancia en la posición c (0 … n-1) de la escala: los tintes se mezclan sumando absorbancias.
// (Interpolación con pesos «tienda» e índices constantes: compila rápido también en Direct3D.)
vec3 inkK(float c) {
  float cc = clamp(c, 0.0, float(uNK - 1));
  vec3 K = vec3(0.0);
  for (int i = 0; i < ${MAX_COLORS}; i++) K += uKs[i] * max(0.0, 1.0 - abs(cc - float(i)));
  return K;
}

// Línea de marea de un frente antiguo tk: fina, con un poco más de pigmento justo por dentro.
float tideLine(float T, float tk, float k, float rimW) {
  float dk = (T - tk) / k;
  return step(tk, uT) * (exp(-dk * dk / 3.0) + 0.5 * exp(min(dk, 0.0) / (rimW * 2.0)) * step(dk, 0.0));
}

void main() {
  vec2 px = vec2(vUv.x, 1.0 - vUv.y) * uSize;
  float u = uU;

  // 1. Dominio deformado: dos niveles de fbm, el segundo deformado por el primero.
  vec2 w1 = nz(px + uOff.xy * 400.0, 190.0 * u).rg;
  vec2 w2 = nz(R1 * px + w1 * 30.0 * u + uOff.zw * 400.0, 55.0 * u).gb;
  vec2 pw = px + (w1 * 16.0 + w2 * 6.0) * u;

  // 2. Tiempo de llegada. k pasa de diferencias de T a px con la velocidad local (la eikonal dice
  // |∇T| = 1/v); kG, con la velocidad mediana.
  vec4 F = texture(uField, pw / uSize);
  float T = F.r + F.g;
  float Tb = F.b;
  float v = max(F.a, 0.15);
  float k = 1.0 / (uL * v);
  float kG = 1.0 / (uL * uVm);

  // 3. Hebras finas (zarcillos y flecos) y vetas anchas (flujo dentro de la mancha). Se miden sobre
  // el dominio deformado, así los rayos ondulan.
  vec2 from = pw - uOrigin;
  float r = length(from);
  float hair = hairs(from, r, max(2.6 * u, 1.6), uOff.x);
  float streak = hairs(from, r, max(10.0 * u, 3.0), uOff.y);

  // 4. Cuando dos frentes se juntan, la rendija que queda se cierra antes (tensión superficial):
  // T no puede quedar muy por encima de su versión suavizada.
  T = min(T, Tb + 6.0 * u * k);

  // 5. Detalle fractal del frente: lóbulos redondeados y entrantes en pico (ruido «billow»), y
  // zarcillos que siguen las hebras; como estas no cambian a lo largo del rayo, nacen del borde. No
  // salen por igual en todo el borde: hay tramos con muchos y tramos lisos.
  float b1 = nz(R1 * pw + 17.3, 26.0 * u).b;
  float b2 = nz(R2 * pw + 41.7, max(9.0 * u, 3.0)).r;
  float disp = (abs(b1) - 0.8) * 6.0 * u + (abs(b2) - 0.8) * 2.0 * max(u, 0.4);
  float hairy = smoothstep(-0.9, 0.9, nz(R2 * pw - 23.0, 70.0 * u).g);
  disp += smoothstep(0.7, 2.3, hair) * uS1.z * u * (0.25 + 0.75 * hairy);
  T -= disp * k;

  // 6. Distancia con signo al frente, en px (positiva dentro). El borde se suaviza en píxeles del
  // canvas con el gradiente real de T (fwidth) más una suavidad propia en px.
  float s = (uT - T) / k;
  float sd = (uT - T) / max(fwidth(T), 1e-8);
  float aa = 0.7 + uS2.w / uPx;
  float cov = smoothstep(-aa, aa, sd);

  // 7. Densidad dentro: más pigmento en el borde, nubes, vetas y líneas de marea (frentes antiguos).
  float sIn = max(s, 0.0);
  float rimW = 2.0 + 3.0 * u;
  float rim = exp(-sIn / rimW);
  float rim2 = exp(-sIn / (rimW * 8.0));
  float cloud = nz(px - uOff.wz * 400.0, 150.0 * u).r * 0.7 + nz(R2 * px + uOff.xy * 300.0, 38.0 * u).g * 0.3;
  float Din = uS2.x * (1.0 + uS2.z * cloud);
  Din += uS1.x * (0.7 * rim + 0.3 * rim2);
  Din *= 1.0 + uS3.z * streak;
  float tide = tideLine(T, uTide.x, k, rimW) + tideLine(T, uTide.y, k, rimW) + tideLine(T, uTide.z, k, rimW);
  Din += uS2.y * tide;
  float sat = uSatAge > 0.0 ? smoothstep(0.0, uSatAge, uT - T) : 0.0;
  Din = mix(Din, 1.0, sat);

  // 8. Fuera: hebras pegadas al frente y, más allá, el halo del agua: una franja diluida, más
  // densa junto a la tinta, con su propio borde irregular y una línea tenue donde se para el agua.
  float frW = uS3.y * max(u, 0.35);
  float fringe = exp(min(s, 0.0) / frW) * smoothstep(0.0, 2.0, hair) * (0.35 + 0.65 * hairy);
  fringe *= smoothstep(-8.0 * frW, -4.0 * frW, (uT - T) / kG);
  float haloW = 6.0 + 18.0 * u;
  float sh = (uT - Tb) / kG + 0.3 * haloW * cloud;
  float hx = max(-sh, 0.0) / haloW;
  float plateau = 1.0 - smoothstep(0.7, 1.05, hx);
  float halo = plateau * mix(0.45, 1.0, exp(-2.5 * hx)) + 0.3 * exp(-pow((hx - 0.86) / 0.08, 2.0));
  halo *= 0.85 + 0.15 * cloud;
  float Dout = (uS1.y * halo + uS3.x * fringe) * smoothstep(0.0, 0.02, uT);

  // 9. Granulado: el pigmento se queda en los valles del papel. Al llenar (cover), uniforme.
  float grain = gr(px, 1.1) * 0.6 + gr(R2 * px + 77.0, 2.6) * 0.4;
  float D = mix(Dout, Din, cov);
  D *= 1.0 + uS1.w * grain * (1.0 - uFill);
  D = mix(D, 1.0, uFill * cov);
  D = max(D, 0.0) * uOpacity;

  // 10. Color. Con varios: del borde al centro según la edad de la tinta (la mancha vira con el
  // tiempo), o por zonas con franjas de mezcla. Al llenar (cover) todo acaba en el último.
  float n1 = float(uNK - 1);
  float cpos;
  if (uMode == 0) {
    cpos = n1 * smoothstep(0.0, 0.62, (uT - T) / uTEnd + 0.04 * cloud);
  } else {
    float z = nz(R1 * pw + uOff.zx * 500.0, 210.0 * u).b * 0.8 + cloud * 0.35;
    float c = clamp(0.5 + 0.3 * z, 0.0, 1.0) * n1;
    float fi = floor(c);
    cpos = fi + smoothstep(0.12, 0.88, c - fi);
  }
  cpos = mix(cpos, n1, max(uFill, sat));
  vec3 Kc = inkK(cpos);
  // El tinte que corre con el agua (halo y flecos) es algo más cian: absorbe más rojo.
  vec3 Kh = Kc * vec3(1.12, 0.95, 0.93);
  Kh *= (Kc.r + Kc.g + Kc.b) / max(Kh.r + Kh.g + Kh.b, 1e-4);
  vec3 K = mix(Kh, Kc, cov);

  // Transmitancia sobre papel blanco: Beer-Lambert (o mezcla lineal con blanco), con tramado para
  // que los degradados suaves no hagan bandas; se escribe con alfa premultiplicado.
  vec3 bl = exp(-K * D);
  vec3 lin = 1.0 - min(D, 1.0) * (1.0 - exp(-K));
  vec3 tr = mix(lin, bl, uChroma);
  float dz = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5;
  tr = clamp(tr + dz * smoothstep(0.0, 0.01, D) / 255.0, 0.0, 1.0);
  float a = 1.0 - min(min(tr.r, tr.g), tr.b);
  outColor = vec4(tr - (1.0 - a), a);
}`

// ---------------------------------------------------------------------------------- utilidades
function parseColor(c) {
  let s = String(c).trim().replace('#', '')
  if (s.length === 3) s = [...s].map((ch) => ch + ch).join('')
  const n = parseInt(s.slice(0, 6), 16)
  if (!Number.isFinite(n)) return [0.04, 0.47, 0.45]
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
}

// Reloj → avance en modo 'time'. El avance ya es proporcional al área; esto solo frena al final.
const easeSpread = (t) => 1 - Math.pow(1 - t, 1.7)

// Sin preguntar aún si compiló: eso obligaría a esperar. Los errores se miran al enlazar.
function compile(gl, type, src) {
  const sh = gl.createShader(type)
  gl.shaderSource(sh, src)
  gl.compileShader(sh)
  return sh
}

// ------------------------------------------------------------------------------------------ API
export function createInk(container, options = {}) {
  const o = { ...DEFAULTS, ...options }
  o.origin = [Number(o.origin[0]) || 0, Number(o.origin[1]) || 0]
  o.seed = Math.floor(Number(o.seed) || 0)
  const flat = !!o.cover && o.flat !== false
  const look = o.cover ? (flat ? LOOK.cover : LOOK.wash) : LOOK.bloom
  const palette = (Array.isArray(o.colors) && o.colors.length ? o.colors : [o.color]).slice(0, MAX_COLORS).map(parseColor)
  const color = palette[palette.length - 1]
  const reduced = matchMedia('(prefers-reduced-motion: reduce)')
  const fieldArgs = () => ({ w, h, o: { seed: o.seed, origin: o.origin, cover: !!o.cover, radius: o.radius }, look })

  let progress = 0
  let anim = null
  let raf = 0
  let visible = false
  let destroyed = false
  let w = 0
  let h = 0
  let dpr = 1
  let scale = 1
  let field = null
  let fieldStale = true
  let pendingKey = ''
  let noiseReady = false
  let lastFrame = 0
  const slow = []
  const stats = { fieldMs: 0, grid: '', compileMs: 0, contextMs: 0 }

  // --- el lienzo
  const canvas = document.createElement('canvas')
  canvas.className = 'ink-canvas'
  canvas.setAttribute('aria-hidden', 'true')
  Object.assign(canvas.style, {
    position: 'absolute',
    top: '0',
    left: '0',
    width: '100%',
    height: '100%',
    display: 'block',
    pointerEvents: 'none',
    zIndex: '-1',
    borderRadius: 'inherit',
  })
  const restore = {}
  const cs = getComputedStyle(container)
  if (cs.position === 'static') {
    restore.position = container.style.position
    container.style.position = 'relative'
  }
  if (cs.isolation !== 'isolate') {
    restore.isolation = container.style.isolation
    container.style.isolation = 'isolate'
  }
  container.prepend(canvas)

  // --- WebGL (o el degradado de reserva). El contexto se crea cuando la tinta se acerca a la vista y
  // el shader se compila en paralelo (KHR_parallel_shader_compile), sin bloquear la página.
  let gl = null
  let glState = 'none' // none · compiling · ready · lost
  let prog = null
  let loc = {}
  let texField = null
  let texNoise = null
  let fallback = null

  function startGL() {
    if (glState !== 'none' || fallback || destroyed) return
    const tc = performance.now()
    try {
      gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false })
    } catch {
      gl = null
    }
    stats.contextMs = performance.now() - tc
    if (!gl) return useFallback()
    const ext = o.sync ? null : gl.getExtension('KHR_parallel_shader_compile')
    const vs = compile(gl, gl.VERTEX_SHADER, VERT)
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG)
    prog = gl.createProgram()
    gl.attachShader(prog, vs)
    gl.attachShader(prog, fs)
    gl.linkProgram(prog)
    glState = 'compiling'
    const t0 = performance.now()
    const done = () => {
      if (destroyed || glState !== 'compiling') return
      if (gl.isContextLost()) return
      if (ext && !gl.getProgramParameter(prog, ext.COMPLETION_STATUS_KHR)) return setTimeout(done, 16)
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        console.warn('ink:', gl.getShaderInfoLog(fs) || gl.getProgramInfoLog(prog))
        return useFallback()
      }
      stats.compileMs = performance.now() - t0
      setupGL()
      glState = 'ready'
      schedule()
    }
    done()
  }

  function setupGL() {
    gl.useProgram(prog)
    loc = {}
    const n = gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS)
    for (let i = 0; i < n; i++) {
      const name = gl.getActiveUniform(prog, i).name
      loc[name.replace('[0]', '')] = gl.getUniformLocation(prog, name)
    }
    gl.uniform1i(loc.uField, 0)
    gl.uniform1i(loc.uNoise, 1)

    const texture = (unit, wrap, filter) => {
      const tex = gl.createTexture()
      gl.activeTexture(unit)
      gl.bindTexture(gl.TEXTURE_2D, tex)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrap)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, wrap)
      return tex
    }
    texNoise = texture(gl.TEXTURE1, gl.REPEAT, gl.LINEAR_MIPMAP_LINEAR)
    texField = texture(gl.TEXTURE0, gl.CLAMP_TO_EDGE, gl.LINEAR)
    noiseReady = false

    // Uniformes que no cambian.
    const r = rng(o.seed + 101)
    gl.uniform4f(loc.uOff, r(), r(), r(), r())
    const Ks = new Float32Array(MAX_COLORS * 3)
    palette.forEach((c, i) => c.forEach((ch, j) => (Ks[i * 3 + j] = -Math.log(Math.max(ch, 1 / 255)))))
    gl.uniform3fv(loc.uKs, Ks)
    gl.uniform1i(loc.uNK, palette.length)
    gl.uniform1i(loc.uMode, o.colorMode === 'zones' ? 1 : 0)
    gl.uniform1f(loc.uOpacity, Math.max(0, Number(o.opacity)))
    gl.uniform1f(loc.uChroma, 0.55)
    gl.uniform4f(loc.uS1, look.rim, look.halo, look.tendril, look.grain)
    gl.uniform4f(loc.uS2, look.inner, look.tide, look.cloud, look.soft)
    gl.uniform4f(loc.uS3, look.fringe, look.fringeW, look.flow, 0)
    if (field) uploadField()
  }

  function uploadNoise() {
    if (noiseReady || !NOISE) return
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_2D, texNoise)
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, 256, 256, 0, gl.RGBA, gl.UNSIGNED_BYTE, NOISE)
    gl.generateMipmap(gl.TEXTURE_2D)
    noiseReady = true
  }

  function uploadField() {
    gl.useProgram(prog)
    uploadNoise()
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, texField)
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 4)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, field.W, field.H, 0, gl.RGBA, gl.FLOAT, field.data)
    const r = rng(o.seed + 202)
    const t = field.tEnd
    gl.uniform3f(loc.uTide, t * (0.3 + 0.1 * r()), t * (0.55 + 0.1 * r()), t * (0.8 + 0.08 * r()))
    gl.uniform1f(loc.uTEnd, field.tEnd)
    gl.uniform1f(loc.uVm, field.vMed)
    gl.uniform1f(loc.uSatAge, field.tEnd * look.sat)
  }

  function useFallback() {
    if (fallback) return
    gl = null
    glState = 'none'
    canvas.remove()
    fallback = document.createElement('div')
    fallback.className = 'ink-canvas ink-fallback'
    fallback.setAttribute('aria-hidden', 'true')
    Object.assign(fallback.style, {
      position: 'absolute',
      top: '0',
      left: '0',
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
      zIndex: '-1',
      borderRadius: 'inherit',
    })
    container.prepend(fallback)
    schedule()
  }

  // --- el campo: se pide al worker en cuanto el contenedor tiene tamaño y está cerca de la vista
  const ready = () => !!fallback || (glState === 'ready' && field && noiseReady)

  function ensureField() {
    if (fallback || destroyed || !w || !h || (field && !fieldStale)) return
    const key = `${w}x${h}`
    if (pendingKey === key) return
    pendingKey = key
    requestField(fieldArgs(), !!o.sync).then((f) => {
      if (destroyed || pendingKey !== key) return
      pendingKey = ''
      field = f
      fieldStale = false
      stats.fieldMs = f.ms
      stats.grid = `${f.W}×${f.H}`
      if (glState === 'ready' && !gl.isContextLost()) uploadField()
      schedule()
    })
  }

  // --- tamaño
  function measure() {
    const cw = container.clientWidth
    const ch = container.clientHeight
    const d = Math.min(window.devicePixelRatio || 1, 2) * scale
    if (cw === w && ch === h && d === dpr) return false
    const ref = field || { w: cw, h: ch }
    const aspectChanged = Math.abs(cw / Math.max(ch, 1) - ref.w / Math.max(ref.h, 1)) > 0.01
    const sizeChanged = Math.abs(Math.max(cw, ch) / Math.max(ref.w, ref.h, 1) - 1) > 0.3
    if (!field || aspectChanged || sizeChanged) fieldStale = true
    w = cw
    h = ch
    dpr = d
    if (!fallback) {
      canvas.width = Math.max(1, Math.round(w * dpr))
      canvas.height = Math.max(1, Math.round(h * dpr))
    }
    return true
  }

  // --- dibujo
  const effective = () => (reduced.matches ? 1 : progress)

  function draw() {
    if (destroyed || !w || !h) return
    const p = effective()
    if (!fallback) startGL()
    if (fallback) return drawFallback(p)
    if (fieldStale) ensureField()
    if (!ready() || gl.isContextLost()) return
    gl.viewport(0, 0, canvas.width, canvas.height)
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    if (p <= 0) return
    gl.useProgram(prog)
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, texField)
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_2D, texNoise)
    gl.uniform2f(loc.uSize, w, h)
    gl.uniform2f(loc.uOrigin, o.origin[0] * w, o.origin[1] * h)
    gl.uniform1f(loc.uL, field.Lt * (w / field.w))
    gl.uniform1f(loc.uU, detailUnit(Math.max(w, h)))
    gl.uniform1f(loc.uPx, (w / canvas.width + h / canvas.height) / 2)
    gl.uniform1f(loc.uT, frontAt(field, p))
    gl.uniform1f(loc.uFill, flat ? smoothstep(0.9, 1, p) : 0)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
  }

  function drawFallback(p) {
    const a = Math.min(1, Math.max(0, Number(o.opacity)))
    const rgba = (c, k) => `rgba(${c.map((x) => Math.round(x * 255)).join(',')},${(a * k).toFixed(3)})`
    const first = palette[0]
    const ox = o.origin[0] * w
    const oy = o.origin[1] * h
    const far = Math.max(Math.hypot(ox, oy), Math.hypot(w - ox, oy), Math.hypot(ox, h - oy), Math.hypot(w - ox, h - oy))
    const ell = Array.isArray(o.radius)
    const g = Math.sqrt(p) * 1.12
    const rx = (o.cover ? far * 1.25 : ell ? o.radius[0] * w : o.radius * Math.min(w, h)) * g
    const ry = (o.cover ? far * 1.25 : ell ? o.radius[1] * h : o.radius * Math.min(w, h)) * g
    if (o.cover && p >= 1) {
      fallback.style.background = flat ? rgba(color, 1) : `linear-gradient(160deg, ${rgba(first, 0.7)}, ${rgba(color, 0.75)})`
      return
    }
    fallback.style.background =
      p <= 0
        ? 'none'
        : `radial-gradient(${rx}px ${ry}px at ${ox}px ${oy}px, ${rgba(color, o.cover ? 1 : 0.8)} 0%, ` +
          `${rgba(first, 1)} 71%, ${rgba(first, 0.15)} 89%, ${rgba(first, 0)} 100%)`
  }

  // --- bucle: solo cuando algo cambia
  function schedule() {
    if (!raf && !destroyed) raf = requestAnimationFrame(frame)
  }

  function frame(now) {
    raf = 0
    if (!visible) return
    if (anim && !ready()) {
      // El reloj de play() no corre hasta que hay campo que dibujar.
      anim.last = null
      ensureField()
      return
    }
    if (anim) {
      if (anim.last != null) anim.elapsed += Math.min(250, now - anim.last)
      anim.last = now
      const t = Math.min(1, anim.elapsed / anim.duration)
      progress = easeSpread(t)
      if (t >= 1) {
        const done = anim.resolve
        anim = null
        done()
      }
    }
    draw()
    if (anim) {
      governor(now)
      schedule()
    } else lastFrame = 0
  }

  // Si el lienzo es grande y los fotogramas se alargan de forma sostenida, se baja la resolución.
  function governor(now) {
    if (lastFrame) slow.push(now - lastFrame)
    lastFrame = now
    if (slow.length < 40) return
    const sorted = slow.slice().sort((p, q) => p - q)
    slow.length = 0
    if (sorted[20] > 24 && canvas.width * canvas.height > 1.2e6 && scale > 0.55) {
      scale *= 0.8
      measure()
    }
  }

  // --- observadores: tamaño, cercanía (para calcular el campo antes de que se vea) y visibilidad
  const ro = new ResizeObserver(() => {
    if (!measure()) return
    if (visible || near) {
      startGL()
      ensureField()
    }
    schedule()
  })
  ro.observe(container)
  let near = false
  const ioNear = new IntersectionObserver(
    (entries) => {
      near = entries[entries.length - 1].isIntersecting
      if (!near || !w || !h) return
      startGL()
      ensureField()
    },
    { rootMargin: '100% 0px' },
  )
  ioNear.observe(container)
  const io = new IntersectionObserver(
    (entries) => {
      visible = entries[entries.length - 1].isIntersecting
      if (anim) anim.last = null
      if (visible) schedule()
    },
    { rootMargin: '80px 0px' },
  )
  io.observe(container)
  const onResize = () => {
    if (measure()) schedule()
  }
  window.addEventListener('resize', onResize)
  const onMotion = () => schedule()
  reduced.addEventListener?.('change', onMotion)

  // Si el navegador pierde el contexto (GPU reiniciada, demasiados contextos), al recuperarlo se
  // vuelve a compilar y a subir el campo.
  const onLost = (e) => {
    e.preventDefault()
    glState = 'lost'
    noiseReady = false
  }
  const onRestored = () => {
    glState = 'none'
    startGL()
    schedule()
  }
  canvas.addEventListener('webglcontextlost', onLost)
  canvas.addEventListener('webglcontextrestored', onRestored)

  measure()

  // --- API
  function setProgress(p) {
    const q = Math.min(1, Math.max(0, Number(p) || 0))
    if (anim) {
      anim.resolve()
      anim = null
    }
    if (q === progress) return
    progress = q
    schedule()
  }

  function play() {
    if (anim) anim.resolve()
    return new Promise((resolve) => {
      if (reduced.matches) {
        anim = null
        progress = 1
        schedule()
        return resolve()
      }
      anim = { elapsed: 0, last: null, duration: Math.max(1, Number(o.duration) || 1), resolve }
      progress = 0
      schedule()
    })
  }

  function destroy() {
    if (destroyed) return
    destroyed = true
    if (raf) cancelAnimationFrame(raf)
    if (anim) anim.resolve()
    anim = null
    ro.disconnect()
    io.disconnect()
    ioNear.disconnect()
    window.removeEventListener('resize', onResize)
    reduced.removeEventListener?.('change', onMotion)
    canvas.removeEventListener('webglcontextlost', onLost)
    canvas.removeEventListener('webglcontextrestored', onRestored)
    if (gl && !gl.isContextLost()) {
      gl.deleteTexture(texField)
      gl.deleteTexture(texNoise)
      gl.deleteProgram(prog)
      gl.getExtension('WEBGL_lose_context')?.loseContext()
    }
    canvas.remove()
    fallback?.remove()
    for (const [k, v] of Object.entries(restore)) container.style[k] = v
  }

  const api = { setProgress, play, destroy }
  // Para medir (no forman parte de la API): dibujar ya, sin esperar al siguiente fotograma, y lo
  // que costó calcular el campo.
  Object.defineProperty(api, '_draw', { value: draw })
  Object.defineProperty(api, '_stats', { value: stats })
  return api
}
