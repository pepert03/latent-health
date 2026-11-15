// Shared utilities: US English formatting, calls to the model and UI pieces.

const formatters = new Map()

function nf(decimals) {
  if (!formatters.has(decimals)) {
    formatters.set(
      decimals,
      new Intl.NumberFormat('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
        useGrouping: 'always',
      }),
    )
  }
  return formatters.get(decimals)
}

/** 9526 -> "9,526"; 7.44 with 1 decimal -> "7.4". */
export function num(value, decimals = 0) {
  return Number.isFinite(value) ? nf(decimals).format(value) : '—'
}

/** Values in mg/g: one decimal below 10, none above. */
export function mg(value) {
  return num(value, value < 10 ? 1 : 0)
}

/** Probability 0–1 -> "61%". Never shows 0% or 100% unless it really is. */
export function pct(p) {
  if (!Number.isFinite(p)) return '—'
  const v = Math.min(1, Math.max(0, p)) * 100
  if (v > 0 && v < 1) return '<1%'
  if (v < 100 && v > 99) return '>99%'
  return `${num(v)}%`
}

const parse = (iso) => new Date(`${iso.slice(0, 10)}T00:00:00Z`)
const dShort = new Intl.DateTimeFormat('en-US', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' })
const dLong = new Intl.DateTimeFormat('en-US', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' })

/** '2026-11-14' -> "11/14/2026". */
export const fecha = (iso) => (iso ? dShort.format(parse(iso)) : '—')

/** '2026-11-16' -> "Monday, November 16". */
export function fechaLarga(iso) {
  if (!iso) return '—'
  const s = dLong.format(parse(iso))
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function addDays(iso, days) {
  const d = parse(iso)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export const daysBetween = (a, b) => Math.round((parse(b) - parse(a)) / 86_400_000)

/** Escapes text for insertion into HTML. */
export function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
}

export const $ = (selector, root = document) => root.querySelector(selector)
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)]

export const OFFLINE = 'The model is not responding. Check that the local server is still running (web\\start.ps1).'

/**
 * Calls the local server. Returns { data, ms }. Throws an Error with a message to show.
 * Every route lives under /api and is served by the same process as this page.
 */
// Page language, sent to the server so its texts come back in the same language.
const LANG = document.documentElement.lang || 'en'

export async function api(path, body, signal) {
  const started = performance.now()
  let response
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? { 'X-Lang': LANG } : { 'Content-Type': 'application/json', 'X-Lang': LANG },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error(OFFLINE)
  }
  if (!response.ok) {
    let detail = `Error ${response.status}`
    try {
      const data = await response.json()
      if (typeof data.detail === 'string') detail = data.detail
      else if (Array.isArray(data.detail) && data.detail[0]?.msg) detail = data.detail[0].msg
    } catch {
      // response without JSON: keep the status code
    }
    throw new Error(response.status >= 500 ? OFFLINE : detail)
  }
  return { data: await response.json(), ms: Math.round(performance.now() - started) }
}

// --- The strip's color chart ---------------------------------------------------------------
export const ALBUMIN = [
  { v: 10, color: 'var(--a10)' },
  { v: 30, color: 'var(--a30)' },
  { v: 80, color: 'var(--a80)' },
  { v: 150, color: 'var(--a150)', inv: true },
]
export const CREATININE = [
  { v: 10, color: 'var(--c10)' },
  { v: 50, color: 'var(--c50)' },
  { v: 100, color: 'var(--c100)' },
  { v: 200, color: 'var(--c200)' },
  { v: 300, color: 'var(--c300)', inv: true },
]
export const padColor = (scale, value) => scale.find((p) => p.v === value)?.color ?? '#f1f2ea'

/** Pad picker: a row of color blocks; calls onPick(value). */
export function picker(root, { title, unit, scale, value, onPick }) {
  root.innerHTML = `<p class="cap"><b>${title}</b> ${unit}</p><div class="cells" role="group" aria-label="${title}, ${unit}">${scale
    .map(
      (p) =>
        `<button type="button" data-v="${p.v}" class="${p.inv ? 'inv' : ''}" style="background:${p.color}" aria-pressed="${p.v === value}" aria-label="${p.v} ${unit}">${p.v}</button>`,
    )
    .join('')}</div>`
  root.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-v]')
    if (!button) return
    $$('button', root).forEach((b) => b.setAttribute('aria-pressed', String(b === button)))
    onPick(Number(button.dataset.v))
  })
}

// --- Clinical states: color + shape + text --------------------------------------------------
const STATE_ICON = {
  sin_medir: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2"/>',
  descartada: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2"/>',
  dudosa: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M13 1v12H1z" fill="currentColor"/>',
  pendiente_cronicidad: '<path d="M0 0h14v14H0z" fill="currentColor"/>',
  confirmada: '<path d="M0 0h14v14H0z" fill="currentColor"/><path d="M3 7.4l2.8 2.8L11 4.2" fill="none" stroke="#0b7774" stroke-width="2"/>',
}
const STATE_CLASS = {
  sin_medir: 's-sin',
  descartada: 's-des',
  dudosa: 's-dud',
  pendiente_cronicidad: 's-muy',
  confirmada: 's-con',
}

export function stateChip(status, label) {
  return `<span class="state ${STATE_CLASS[status] ?? 's-sin'}"><svg viewBox="0 0 14 14" aria-hidden="true">${STATE_ICON[status] ?? ''}</svg>${esc(label)}</span>`
}

/** Model texts already come as "4%", which is right in English: passed through unchanged. */
export const fixPct = (text) => String(text ?? '')
