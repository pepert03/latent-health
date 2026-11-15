// La plantilla de color del kit: una cartulina blanca de 6 × 10,8 cm donde se pone la tira para la
// foto. Las cuatro marcas de las esquinas le dicen a la app dónde está y cómo está girada (la de arriba a
// la izquierda tiene el centro verde); los parches de color conocidos corrigen la luz de cada casa antes
// de leer las almohadillas: la escala de albúmina a la izquierda, la de creatinina a la derecha y una
// escala de grises abajo. Unidades: décimas de milímetro, en vertical.
import { logoGroup, INK } from './marca.js'
import { TIRA, tiraMarkup } from './tira.js'

const ALB = ['#f6ec9b', '#c8de6e', '#5fbe8c', '#0b7774']
const CRE = ['#fdeadf', '#f8c6aa', '#f29a78', '#d9766e', '#a9505f']
const GRIS = ['#ffffff', '#e3e7e5', '#c0c8c5', '#8c9794', '#4b5856', '#0d2226']

const CARD_W = 600
const CARD_H = 1080
// La tira, de pie y centrada: punta arriba, mango abajo.
const SLOT = { x: CARD_W / 2 - TIRA.h / 2, y: 190, w: TIRA.h, h: TIRA.w }
const padCenter = (key) => [CARD_W / 2, SLOT.y + SLOT.h - (TIRA.pads[key][0] + TIRA.pads[key][1]) / 2]

function layout() {
  const parches = []
  ALB.forEach((color, i) => parches.push({ grupo: 'albúmina', color, x: 140, y: 190 + i * 72, w: 60, h: 60 }))
  CRE.forEach((color, i) => parches.push({ grupo: 'creatinina', color, x: 400, y: 190 + i * 72, w: 60, h: 60 }))
  GRIS.forEach((color, i) => parches.push({ grupo: 'gris', color, x: 153 + i * 50, y: 990, w: 44, h: 40 }))
  return parches
}

// Geometría para quien tenga que dibujar o encontrar cosas encima (el kit en 3D, la cámara de la app).
export const PLANTILLA = {
  w: CARD_W,
  h: CARD_H,
  marcas: [
    [70, 70],
    [530, 70],
    [70, 1010],
    [530, 1010],
  ], // centros, en orden: arriba izquierda (la del centro verde), arriba derecha, abajo izquierda, abajo derecha
  marca: 72, // lado de cada marca
  tira: SLOT, // la tira de pie, mango abajo
  almohadillas: { a: padCenter('a'), c: padCenter('c') }, // centros con la tira puesta
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
 * SVG de la plantilla. tira: { a, c } dibuja la tira puesta con esos colores en las almohadillas
 * (null la deja vacía, con el hueco marcado). `id` distinto en cada plantilla de la misma página.
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
    `<text ${text(140, 172, 17)}>ALBÚMINA</text>` +
    `<text ${text(460, 172, 17, 'end')}>CREATININA</text>` +
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
    svg += `<text ${text(300, t.y + t.h + 62, 18, 'middle', '#6f7f81', 500)}>Pon aquí la tira</text>`
  }
  return svg + '</svg>'
}
