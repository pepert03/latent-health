// The kit's color card: a white 6 × 10.8 cm card where the strip is placed for the photo.
// The four corner marks tell the app where it is and how it is rotated (the top-left one has a green
// center); the known color patches correct each home's lighting before the pads are read: the albumin
// scale on the left, the creatinine scale on the right and a gray scale at the bottom.
// Units: tenths of a millimeter, portrait.
import { logoGroup, INK } from './marca.js'
import { TIRA, tiraMarkup } from './tira.js'

const ALB = ['#f6ec9b', '#c8de6e', '#5fbe8c', '#0b7774']
const CRE = ['#fdeadf', '#f8c6aa', '#f29a78', '#d9766e', '#a9505f']
const GRIS = ['#ffffff', '#e3e7e5', '#c0c8c5', '#8c9794', '#4b5856', '#0d2226']

const CARD_W = 600
const CARD_H = 1080
// The strip, upright and centered: tip up, handle down.
const SLOT = { x: CARD_W / 2 - TIRA.h / 2, y: 190, w: TIRA.h, h: TIRA.w }
const padCenter = (key) => [CARD_W / 2, SLOT.y + SLOT.h - (TIRA.pads[key][0] + TIRA.pads[key][1]) / 2]

function layout() {
  const parches = []
  ALB.forEach((color, i) => parches.push({ grupo: 'albumin', color, x: 140, y: 190 + i * 72, w: 60, h: 60 }))
  CRE.forEach((color, i) => parches.push({ grupo: 'creatinine', color, x: 400, y: 190 + i * 72, w: 60, h: 60 }))
  GRIS.forEach((color, i) => parches.push({ grupo: 'gray', color, x: 153 + i * 50, y: 990, w: 44, h: 40 }))
  return parches
}

// Geometry for anyone who has to draw or find things on it (the 3D kit, the app camera).
export const PLANTILLA = {
  w: CARD_W,
  h: CARD_H,
  marcas: [
    [70, 70],
    [530, 70],
    [70, 1010],
    [530, 1010],
  ], // centers, in order: top left (the green-centered one), top right, bottom left, bottom right
  marca: 72, // side of each mark
  tira: SLOT, // the strip upright, handle down
  almohadillas: { a: padCenter('a'), c: padCenter('c') }, // centers with the strip in place
  parches: layout(),
}

function marca([cx, cy], centro) {
  const s = PLANTILLA.marca
  const x = cx - s / 2
  const y = cy - s / 2
  return (
    `<rect x="${x}" y="${y}" width="${s}" height="${s}" rx="13" fill="${INK}"/>` +
    `<rect x="${x + 21}" y="${y + 21}" width="${s - 42}" height="${s - 42}" rx="5" fill="${centro}"/>`
  )
}

/**
 * Card SVG. tira: { a, c } draws the strip in place with those pad colors
 * (null leaves it empty, with the slot outlined). Use a different `id` for each card on the same page.
 */
export function plantillaSVG({ tira = null, id = 'pl', cls = '', title = '' } = {}) {
  const P = PLANTILLA
  const t = P.tira
  const label = title ? `role="img" aria-label="${title}"` : 'aria-hidden="true"'
  const text = (x, y, s, anchor = 'start', fill = '#44575a', weight = 600) =>
    `x="${x}" y="${y}" font-family="Archivo, 'Arial Nova', Arial, sans-serif" font-size="${s}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}" letter-spacing=".6"`
  let svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${P.w} ${P.h}"${cls ? ` class="${cls}"` : ''} ${label}>` +
    '<defs>' +
    `<filter id="${id}-sombra" x="-30%" y="-5%" width="160%" height="110%"><feGaussianBlur stdDeviation="6"/></filter>` +
    '</defs>' +
    `<rect width="${P.w}" height="${P.h}" rx="26" fill="#ffffff"/>` +
    logoGroup({ x: 158.5, y: 84, cap: 20 }) +
    P.marcas.map((m, i) => marca(m, i === 0 ? '#c8de6e' : '#ffffff')).join('') +
    `<text ${text(140, 172, 17)}>ALBUMIN</text>` +
    `<text ${text(460, 172, 17, 'end')}>CREATININE</text>` +
    P.parches
      .map(
        (p) =>
          `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="6" fill="${p.color}"` +
          (p.color === '#ffffff' ? ' stroke="#cfd6d3" stroke-width="2"' : '') +
          '/>',
      )
      .join('') +
    `<rect x="${t.x - 14}" y="${t.y - 14}" width="${t.w + 28}" height="${t.h + 28}" rx="14" fill="none" stroke="#a9b6b2" stroke-width="3" stroke-dasharray="12 9"/>`
  if (tira) {
    svg +=
      `<rect x="${t.x + 5}" y="${t.y + 9}" width="${t.w}" height="${t.h}" rx="6" fill="#0d2226" opacity=".22" filter="url(#${id}-sombra)"/>` +
      `<g transform="translate(${t.x} ${t.y + t.h}) rotate(-90)">${tiraMarkup({ ...tira, id: `${id}-t` })}</g>`
  } else {
    svg += `<text ${text(300, t.y + t.h + 62, 18, 'middle', '#6f7f81', 500)}>Place strip here</text>`
  }
  return svg + '</svg>'
}
