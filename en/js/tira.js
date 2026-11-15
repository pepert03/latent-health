// La tira de orina de LatentHealth. Una sola definición para toda la web, el kit en 3D y la foto que
// lee la cámara: 64 × 7,2 mm de plástico blanco, el mango con la marca y dos almohadillas en la punta,
// albúmina y creatinina. Unidades: décimas de milímetro, en horizontal y con el mango a la izquierda.
import { logoGroup } from './marca.js'

export const TIRA = {
  w: 640,
  h: 72,
  // Almohadillas de 6,2 × 6,2 mm: [inicio, fin] a lo largo de la tira.
  pads: { a: [482, 544], c: [560, 622] },
  // Plástico blanco liso entre la marca y las almohadillas: la cámara lo usa de blanco de referencia.
  blanco: [380, 36],
}

// Colores de las almohadillas sin mojar y los de la lectura de ejemplo de toda la web
// (albúmina 30 mg/l y creatinina 100 mg/dl, la tira «dudosa» de Pilar).
export const SECA = { a: '#f3ecb4', c: '#fbebe0' }
export const DEMO = { a: '#c8de6e', c: '#f29a78' }

/** Defs y dibujo de la tira, en horizontal (0-640 × 0-72), para meterlos dentro de otro SVG. */
export function tiraMarkup({ a = SECA.a, c = SECA.c, id = 'tira' } = {}) {
  const { w, h } = TIRA
  const pad = (key, fill) => {
    const [x0, x1] = TIRA.pads[key]
    const s = x1 - x0
    const y = (h - s) / 2
    return (
      `<rect class="tp-${key}" x="${x0}" y="${y}" width="${s}" height="${s}" rx="3" fill="${fill}"/>` +
      `<rect x="${x0}" y="${y}" width="${s}" height="${s}" rx="3" fill="url(#${id}-wet)"/>` +
      `<rect x="${x0}" y="${y}" width="${s}" height="${s}" rx="3" fill="#000" filter="url(#${id}-fib)"/>` +
      `<rect x="${x0 + 0.7}" y="${y + 0.7}" width="${s - 1.4}" height="${s - 1.4}" rx="2.4" fill="none" stroke="#000" stroke-opacity=".10" stroke-width="1.4"/>`
    )
  }
  return (
    '<defs>' +
    `<linearGradient id="${id}-body" x1="0" y1="0" x2="0" y2="1">` +
    '<stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#f8f9f7"/><stop offset="1" stop-color="#e8ebe9"/>' +
    '</linearGradient>' +
    `<radialGradient id="${id}-wet" cx=".45" cy=".42" r=".75">` +
    '<stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset=".6" stop-color="#fff" stop-opacity="0"/>' +
    '<stop offset="1" stop-color="#000" stop-opacity=".12"/>' +
    '</radialGradient>' +
    `<filter id="${id}-fib" x="0" y="0" width="100%" height="100%">` +
    '<feTurbulence type="fractalNoise" baseFrequency=".42" numOctaves="2" seed="7" result="n"/>' +
    '<feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .26 -.07" result="d"/>' +
    '<feComposite in="d" in2="SourceGraphic" operator="in"/>' +
    '</filter>' +
    '</defs>' +
    `<rect x=".7" y=".7" width="${w - 1.4}" height="${h - 1.4}" rx="6" fill="url(#${id}-body)" stroke="#d3dad7" stroke-width="1.4"/>` +
    logoGroup({ x: 26, y: 44, cap: 16 }) +
    pad('a', a) +
    pad('c', c)
  )
}

/**
 * SVG de la tira. vertical: true la pone de pie, con el mango abajo y las almohadillas arriba.
 * `id` tiene que ser distinto en cada tira de la misma página (lo usan los degradados).
 */
export function tiraSVG({ a, c, id = 'tira', vertical = false, cls = '', title = '' } = {}) {
  const { w, h } = TIRA
  const body = tiraMarkup({ a, c, id })
  const label = title ? `role="img" aria-label="${title}"` : 'aria-hidden="true"'
  const klass = cls ? ` class="${cls}"` : ''
  if (!vertical) {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}"${klass} ${label}>${body}</svg>`
  }
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${h} ${w}"${klass} ${label}>` +
    `<g transform="translate(0 ${w}) rotate(-90)">${body}</g></svg>`
  )
}
