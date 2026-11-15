// The camera viewfinder: the strip on the color card and, on top, what the recognition does.
// First it locks the four corner marks, then it measures the patches to correct the light, then it
// finds the strip and reads the two pads, each with its label alongside.
//
// Everything lives in one SVG in photo coordinates (900 × 1200) with preserveAspectRatio "slice", so the
// photo and the marks crop the same way in any viewfinder. If img/tira-camara.json exists (the photo
// rendered from the 3D kit, with the projected points), the photo is used; otherwise, a drawn scene with
// the same card and the same strip.
import { PLANTILLA, plantillaSVG } from './plantilla.js'
import { DEMO, TIRA } from './tira.js'

const W = 900
const H = 1200
let photo = null // { src, blank, pts } once the photo exists

// --- Drawn scene: the card on a light table, slightly rotated -----------------------------------
const S = 0.75 // photo px per card unit
const ROT = (-4 * Math.PI) / 180
function toFrame([x, y]) {
  const dx = (x - PLANTILLA.w / 2) * S
  const dy = (y - PLANTILLA.h / 2) * S
  return [W / 2 + dx * Math.cos(ROT) - dy * Math.sin(ROT), H / 2 + dx * Math.sin(ROT) + dy * Math.cos(ROT)]
}

/** Corners of a pad on the card, with the strip upright (handle down). */
function padCorners(key) {
  const t = PLANTILLA.tira
  const [s0, s1] = TIRA.pads[key]
  const inset = (TIRA.h - (s1 - s0)) / 2
  const x0 = t.x + inset
  const x1 = t.x + t.w - inset
  const y0 = t.y + t.h - s1
  const y1 = t.y + t.h - s0
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ]
}

function drawnPoints() {
  const P = PLANTILLA
  const t = P.tira
  return {
    marcas: P.marcas.map(toFrame),
    plantilla: [
      [0, 0],
      [P.w, 0],
      [P.w, P.h],
      [0, P.h],
    ].map(toFrame),
    // Tip left, tip right, handle right, handle left.
    tira: [
      [t.x, t.y],
      [t.x + t.w, t.y],
      [t.x + t.w, t.y + t.h],
      [t.x, t.y + t.h],
    ].map(toFrame),
    a: toFrame(P.almohadillas.a),
    c: toFrame(P.almohadillas.c),
    aCorners: padCorners('a').map(toFrame),
    cCorners: padCorners('c').map(toFrame),
    parches: P.parches.map((p) => toFrame([p.x + p.w / 2, p.y + p.h / 2])),
  }
}

/** Loads the 3D render photo if it exists. Returns true if the photo is used from now on. */
export async function loadPhoto() {
  try {
    const res = await fetch('img/tira-camara.json', { cache: 'no-cache' })
    if (!res.ok) return false
    const json = await res.json()
    if (!json.marcas || !json.plantilla || !json.tira) return false
    const px = (p) => [p[0] * W, p[1] * H]
    const many = (list) => list.map(px)
    const blank = await exists('img/tira-camara-blanca.jpg')
    photo = {
      src: blank ? 'img/tira-camara-blanca.jpg' : 'img/tira-camara.jpg',
      blank,
      pts: {
        marcas: many(json.marcas),
        plantilla: many(json.plantilla),
        tira: many(json.tira),
        a: px(json.almohadillas?.a ?? json.a),
        c: px(json.almohadillas?.c ?? json.c),
        aCorners: json.esquinasAlmohadillas?.a ? many(json.esquinasAlmohadillas.a) : null,
        cCorners: json.esquinasAlmohadillas?.c ? many(json.esquinasAlmohadillas.c) : null,
        parches: many(json.parches ?? []),
      },
    }
    return true
  } catch {
    return false
  }
}

async function exists(url) {
  try {
    const res = await fetch(url, { method: 'HEAD', cache: 'no-cache' })
    return res.ok
  } catch {
    return false
  }
}

// --- Mark geometry ----------------------------------------------------------------------------
const pts = (list) => list.map((p) => p.map((v) => v.toFixed(1)).join(',')).join(' ')
const mean = (list) => [list.reduce((s, p) => s + p[0], 0) / list.length, list.reduce((s, p) => s + p[1], 0) / list.length]

/** Grows a polygon from its center: by a factor, plus some px outward. */
function grow(list, k, extra = 0) {
  const [cx, cy] = mean(list)
  return list.map(([x, y]) => {
    const dx = x - cx
    const dy = y - cy
    const d = Math.hypot(dx, dy) || 1
    return [cx + dx * k + (dx / d) * extra, cy + dy * k + (dy / d) * extra]
  })
}

function squareAround([cx, cy], half, angle) {
  const c = Math.cos(angle)
  const s = Math.sin(angle)
  return [
    [-half, -half],
    [half, -half],
    [half, half],
    [-half, half],
  ].map(([x, y]) => [cx + x * c - y * s, cy + x * s + y * c])
}

/** L-shaped corners of a box: what a detector draws when it locks onto a point. */
function brackets(corners, arm) {
  return corners
    .map((p, i) => {
      const toward = (q) => {
        const dx = q[0] - p[0]
        const dy = q[1] - p[1]
        const d = Math.hypot(dx, dy)
        const len = Math.min(arm, d * 0.35)
        return [p[0] + (dx / d) * len, p[1] + (dy / d) * len]
      }
      const a = toward(corners[(i + 3) % 4])
      const b = toward(corners[(i + 1) % 4])
      return `M${a[0].toFixed(1)} ${a[1].toFixed(1)}L${p[0].toFixed(1)} ${p[1].toFixed(1)}L${b[0].toFixed(1)} ${b[1].toFixed(1)}`
    })
    .join('')
}

/** Left and right edge of a quadrilateral at a given height (to place labels outside). */
function edgesAt(quad, y) {
  const lerp = (p, q) => {
    const t = (y - p[1]) / (q[1] - p[1] || 1)
    return p[0] + (q[0] - p[0]) * Math.min(1, Math.max(0, t))
  }
  return { left: lerp(quad[0], quad[3]), right: lerp(quad[1], quad[2]), y }
}

function label({ side, at, padBox, color, name, value, key }) {
  const w = 206
  const h = 88
  const gap = 14
  // The label sits outside the card, level with its pad, and a line joins it to the box.
  const edge = side === 'left' ? Math.min(...padBox.map((p) => p[0])) : Math.max(...padBox.map((p) => p[0]))
  const x = side === 'left' ? Math.max(8, at.left - gap - w) : Math.min(W - w - 8, at.right + gap)
  const y = Math.min(H - h - 8, Math.max(8, at.y - h / 2))
  const lx = side === 'left' ? x + w : x
  return `<path class="cv-lead" pathLength="1" d="M${edge.toFixed(1)} ${at.y.toFixed(1)}H${lx.toFixed(1)}"/>
    <g class="cv-label cv-label--${key}"><g transform="translate(${x.toFixed(1)} ${y.toFixed(1)})">
      <rect class="cv-tag" width="${w}" height="${h}" rx="18"/>
      <rect class="tp-${key}-sw" x="16" y="15" width="26" height="26" rx="6" fill="${color}"/>
      <text class="cv-name" x="52" y="36">${name}</text>
      <text class="cv-value" x="16" y="74" id="cv-${key}-v">${value}</text>
    </g></g>`
}

// --- The scene ---------------------------------------------------------------------------------
function drawnScene(id, a, c) {
  const card = drawnPoints().plantilla
  const shadow = card.map(([x, y]) => [x + 16, y + 24])
  const nested = plantillaSVG({ tira: { a, c }, id: `${id}-pl` }).replace(
    '<svg ',
    `<svg x="${(-PLANTILLA.w * S) / 2}" y="${(-PLANTILLA.h * S) / 2}" width="${PLANTILLA.w * S}" height="${PLANTILLA.h * S}" `,
  )
  return `<defs>
      <linearGradient id="${id}-mesa" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f1e9dc"/><stop offset=".55" stop-color="#e4d7c3"/><stop offset="1" stop-color="#d5c4aa"/></linearGradient>
      <filter id="${id}-veta" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.0032 0.075" numOctaves="3" seed="11"/><feColorMatrix values="0 0 0 0 0.42  0 0 0 0 0.31  0 0 0 0 0.18  0 0 0 0.5 -0.08"/></filter>
      <filter id="${id}-grano" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".75" numOctaves="1" seed="5"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .07 -.012"/></filter>
      <filter id="${id}-blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="16"/></filter>
      <radialGradient id="${id}-luz" cx=".18" cy=".05" r="1.05"><stop offset="0" stop-color="#fff" stop-opacity=".42"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></radialGradient>
      <radialGradient id="${id}-vig" cx=".5" cy=".5" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".3"/></radialGradient>
    </defs>
    <rect width="${W}" height="${H}" fill="url(#${id}-mesa)"/>
    <rect width="${W}" height="${H}" filter="url(#${id}-veta)"/>
    <polygon points="${pts(shadow)}" fill="#3a2c1c" opacity=".3" filter="url(#${id}-blur)"/>
    <g transform="translate(${W / 2} ${H / 2}) rotate(${((ROT * 180) / Math.PI).toFixed(2)})">${nested}</g>
    <rect width="${W}" height="${H}" fill="url(#${id}-luz)"/>
    <rect width="${W}" height="${H}" fill="url(#${id}-vig)"/>
    <rect width="${W}" height="${H}" filter="url(#${id}-grano)"/>`
}

function photoScene(a, c) {
  const p = photo.pts
  let tint = ''
  if (photo.blank && p.aCorners && p.cCorners) {
    tint = `<polygon class="tp-a" points="${pts(p.aCorners)}" fill="${a}" style="mix-blend-mode:multiply"/>
      <polygon class="tp-c" points="${pts(p.cCorners)}" fill="${c}" style="mix-blend-mode:multiply"/>`
  }
  return `<image href="${photo.src}" width="${W}" height="${H}" preserveAspectRatio="none"/>${tint}`
}

/**
 * Viewfinder SVG. a, c: pad colors; valA, valC: the reading on each one.
 * view: 'full' (the whole photo, 3:4 viewfinder) or 'top' (the upper part, where the pads are).
 */
export function camSVG({ id = 'cam', a = DEMO.a, c = DEMO.c, valA = '30 mg/l', valC = '100 mg/dl', view = 'full' } = {}) {
  const p = photo ? photo.pts : drawnPoints()
  const scene = photo ? photoScene(a, c) : drawnScene(id, a, c)
  const [m0, m1] = p.marcas
  const angle = Math.atan2(m1[1] - m0[1], m1[0] - m0[0])
  const unit = Math.hypot(m1[0] - m0[0], m1[1] - m0[1]) / (PLANTILLA.marcas[1][0] - PLANTILLA.marcas[0][0])
  const half = PLANTILLA.marca * unit * 0.78
  const marks = p.marcas
    .map((m, i) => `<path class="cv-mark" style="--i:${i}" d="${brackets(squareAround(m, half, angle), half * 0.55)}"/>`)
    .join('')
  const patches = p.parches.map((q, i) => `<circle class="cv-patch" style="--i:${i}" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="9"/>`).join('')
  const padHalf = ((TIRA.pads.a[1] - TIRA.pads.a[0]) / 2) * unit
  const boxA = p.aCorners ? grow(p.aCorners, 1, 10) : squareAround(p.a, padHalf + 10, angle)
  const boxC = p.cCorners ? grow(p.cCorners, 1, 10) : squareAround(p.c, padHalf + 10, angle)
  const top = Math.max(0, Math.round(Math.min(p.a[1], p.c[1]) - 290))
  const vb = view === 'top' ? `0 ${top} ${W} 760` : `0 0 ${W} ${H}`
  return `<svg class="cam-svg" viewBox="${vb}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    ${scene}
    <g class="cv">
      <polygon class="cv-card" points="${pts(p.plantilla)}"/>
      ${marks}
      ${patches}
      <polygon class="cv-strip" points="${pts(grow(p.tira, 1, 8))}"/>
      <polygon class="cv-pad" style="--i:0" points="${pts(boxC)}"/>
      <polygon class="cv-pad" style="--i:1" points="${pts(boxA)}"/>
      ${label({ side: 'right', at: edgesAt(p.plantilla, p.c[1]), padBox: boxC, color: c, name: 'Creatinine', value: valC, key: 'c' })}
      ${label({ side: 'left', at: edgesAt(p.plantilla, p.a[1]), padBox: boxA, color: a, name: 'Albumin', value: valA, key: 'a' })}
    </g>
  </svg>`
}

/** Changes a pad's color and reading without repainting the viewfinder. */
export function setPad(root, key, color, value) {
  root.querySelectorAll(`.tp-${key}, .tp-${key}-sw`).forEach((el) => el.setAttribute('fill', color))
  const text = root.querySelector(`#cv-${key}-v`)
  if (text) text.textContent = value
}
