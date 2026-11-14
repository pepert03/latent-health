/**
 * Formato en español de España: coma decimal, punto de miles (también en 9.526),
 * espacio fino antes de % y fechas dd/mm/aaaa. Las unidades las pone quien llama.
 */

const NBSP = ' '
const formatters = new Map<number, Intl.NumberFormat>()

function numberFormat(decimals: number): Intl.NumberFormat {
  let f = formatters.get(decimals)
  if (!f) {
    f = new Intl.NumberFormat('es-ES', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
      useGrouping: 'always',
    })
    formatters.set(decimals, f)
  }
  return f
}

/** 9526 -> «9.526»; 7.44 con 1 decimal -> «7,4». Un valor no finito sale como «—». */
export function num(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return numberFormat(decimals).format(value)
}

/** Probabilidad 0–1 -> «61 %». Nunca enseña 0 % ni 100 % si no lo son: «< 1 %», «> 99 %». */
export function pct(probability: number | null | undefined, decimals = 0): string {
  if (probability === null || probability === undefined || !Number.isFinite(probability)) return '—'
  const v = probability * 100
  const step = 10 ** -decimals
  if (v > 0 && v < step) return `<${NBSP}${num(step, decimals)}${NBSP}%`
  if (v < 100 && v > 100 - step) return `>${NBSP}${num(100 - step, decimals)}${NBSP}%`
  return `${num(v, decimals)}${NBSP}%`
}

/** Valor con unidad, unidos con espacio duro: «52 ml/min/1,73 m²». */
export function withUnit(value: number | null | undefined, unit: string, decimals = 0): string {
  return `${num(value, decimals)}${NBSP}${unit}`
}

/** Intervalo: «6–29». */
export function range(low: number, high: number, decimals = 0): string {
  return `${num(low, decimals)}–${num(high, decimals)}`
}

const dateFormat = new Intl.DateTimeFormat('es-ES', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  timeZone: 'UTC',
})
const longDateFormat = new Intl.DateTimeFormat('es-ES', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  timeZone: 'UTC',
})

/** 'YYYY-MM-DD' se lee como medianoche UTC para que el día no cambie con el huso horario. */
function parseIso(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`)
}

/** '2026-11-14' -> «14/11/2026». */
export function fecha(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = parseIso(iso)
  return Number.isNaN(d.getTime()) ? '—' : dateFormat.format(d)
}

/** '2026-11-16' -> «lunes, 16 de noviembre». */
export function fechaLarga(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = parseIso(iso)
  return Number.isNaN(d.getTime()) ? '—' : longDateFormat.format(d)
}

/** Suma días a una fecha ISO y devuelve otra fecha ISO. */
export function addDays(iso: string, days: number): string {
  const d = parseIso(iso)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Días entre dos fechas ISO (b − a). */
export function daysBetween(a: string, b: string): number {
  return Math.round((parseIso(b).getTime() - parseIso(a).getTime()) / 86_400_000)
}
