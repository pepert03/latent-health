// «El modelo, en vivo»: cada cambio es una petición real a POST /api/model/albuminuria.
import { $, $$, ALBUMIN, CREATININE, api, esc, fecha, fixPct, mg, num, pct, picker, stateChip } from './lib.js'

const TODAY = '2026-11-16'
const state = {
  patient: { age: 58, female: true, diabetes: false, egfr: 88 },
  samples: [],
  kind: 'tira',
  strip: { albumin: 30, creatinine: 100 },
}
let examples = []
let controller = null
let timer = 0

const asOf = () => state.samples.reduce((latest, s) => (s.date > latest ? s.date : latest), TODAY)

function sampleLabel(s) {
  return s.kind === 'tira'
    ? `Tira: albúmina ${s.albumin_mg_l} mg/l, creatinina ${s.creatinine_mg_dl} mg/dl`
    : `Laboratorio: ${num(s.uacr)} mg/g, ${s.sample_type === 'random' ? 'muestra aleatoria' : 'primera orina de la mañana'}`
}

function renderInputs() {
  const p = state.patient
  $('#lab-age').value = p.age
  $('#lab-age-out').textContent = `${p.age} años`
  $('#lab-egfr').value = p.egfr
  $('#lab-egfr-out').textContent = String(p.egfr)
  $$('#lab-sex button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === String(p.female))))
  $$('#lab-dm button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === String(p.diabetes))))
  const list = $('#lab-samples')
  list.innerHTML = state.samples.length
    ? state.samples
        .map(
          (s, i) =>
            `<li><span>${esc(sampleLabel(s))}</span><span class="dt">${fecha(s.date)}</span><button type="button" data-i="${i}" aria-label="Quitar la muestra del ${fecha(s.date)}">×</button></li>`,
        )
        .join('')
    : '<li class="empty">Sin muestras. El modelo solo conoce la historia clínica: añade una tira.</li>'
}

// --- Gráfica: lo que el filtro cree sobre el valor verdadero, en escala logarítmica ----------
const W = 640
const H = 250
const M = { l: 14, r: 26, t: 22, b: 46 }
const X0 = Math.log(0.6)
const X1 = Math.log(3000)
const x = (v) => M.l + ((Math.log(Math.min(Math.max(v, 0.6), 3000)) - X0) / (X1 - X0)) * (W - M.l - M.r)
const TICKS = [1, 3, 10, 30, 100, 300, 1000, 3000]

function curve(dist, peak, close) {
  const base = H - M.b
  const pts = dist.uacr
    .map((u, i) => [u, dist.mass[i]])
    .filter(([u]) => u >= 0.6 && u <= 3000)
    .map(([u, m]) => `${x(u).toFixed(1)},${(base - (m / peak) * (base - M.t - 8)).toFixed(1)}`)
  if (!pts.length) return ''
  return close ? `M${x(0.6)},${base}L${pts.join('L')}L${x(3000)},${base}Z` : `M${pts.join('L')}`
}

function marker(s) {
  const cx = x(s.value_mg_g).toFixed(1)
  const cy = H - M.b + 1
  const title = `<title>${esc(s.label)}: ${mg(s.value_mg_g)} mg/g (${fecha(s.date)})</title>`
  if (s.kind === 'tira') return `<rect x="${cx - 5}" y="${cy - 5}" width="10" height="10" fill="#fff" stroke="#0d2226" stroke-width="2">${title}</rect>`
  if (s.sample_type === 'random')
    return `<path d="M0-7 7 0 0 7-7 0z" transform="translate(${cx} ${cy})" fill="#fff" stroke="#0d2226" stroke-width="2">${title}</path>`
  return `<circle cx="${cx}" cy="${cy}" r="5.5" fill="#0d2226" stroke="#fff" stroke-width="1.5">${title}</circle>`
}

function renderChart(r) {
  const base = H - M.b
  const peak = Math.max(...r.belief.mass, ...r.prior.mass)
  const refs = [30, 300]
    .map(
      (v) =>
        `<line class="ref" x1="${x(v)}" x2="${x(v)}" y1="${M.t - 4}" y2="${base}"/><text x="${x(v) + 5}" y="${M.t + 6}">${v} mg/g</text>`,
    )
    .join('')
  const zones = [
    ['A1', 4.2],
    ['A2', 95],
    ['A3', 950],
  ]
    .map(([name, v]) => `<text class="k" x="${x(v)}" y="12" text-anchor="middle">${name}</text>`)
    .join('')
  const ticks = TICKS.map(
    (v) => `<line class="gl" x1="${x(v)}" x2="${x(v)}" y1="${base}" y2="${base + 5}"/><text x="${x(v)}" y="${base + 24}" text-anchor="middle">${v}</text>`,
  ).join('')
  $('#lab-chart').innerHTML = `
    ${zones}${refs}
    <path d="${curve(r.belief, peak, true)}" fill="#6cb99f" fill-opacity=".8" stroke="#0b7774" stroke-width="2"/>
    <path d="${curve(r.prior, peak, false)}" fill="none" stroke="#44575a" stroke-width="1.5" stroke-dasharray="5 4"/>
    <line x1="${x(r.median)}" x2="${x(r.median)}" y1="${M.t + 12}" y2="${base}" stroke="#0d2226" stroke-width="2"/>
    <line x1="${M.l}" x2="${W - M.r}" y1="${base}" y2="${base}" stroke="#0d2226" stroke-width="1.5"/>
    ${ticks}
    <text x="${W - M.r}" y="${H - 4}" text-anchor="end">cociente albúmina/creatinina verdadero, mg/g (escala logarítmica)</text>
    ${r.samples.map(marker).join('')}`
}

function renderResult(r) {
  $('#lab-state').innerHTML = stateChip(r.status, r.status_label)
  $('#lab-median').textContent = `${mg(r.median)} mg/g`
  $('#lab-interval').textContent = `${mg(r.low)}–${mg(r.high)} mg/g`
  const bars = [
    ['A1 (menos de 30 mg/g)', r.p_a1, 'var(--a10)'],
    ['A2 (30 a 300 mg/g)', r.p_a2, 'var(--a80)'],
    ['A3 (más de 300 mg/g)', r.p_a3, 'var(--a150)'],
  ]
  $('#lab-bars').innerHTML = bars
    .map(
      ([label, p, color]) =>
        `<li><span>${label}</span><b>${pct(p)}</b><span class="bar"><i style="width:${(p * 100).toFixed(1)}%;background:${color}"></i></span></li>`,
    )
    .join('')
  const next = $('#lab-next')
  next.hidden = !r.next_sample_resolves
  if (r.next_sample_resolves) {
    next.innerHTML = `Otra muestra de primera orina resolvería la duda con una probabilidad del <b>${pct(r.next_sample_resolves.first_morning)}</b> (con una aleatoria, ${pct(r.next_sample_resolves.random)}).`
  }
  $('#lab-action').innerHTML = `<b>Qué dice el modelo:</b> ${esc(fixPct(r.action))}`
  renderChart(r)
  $('#lab-proj').innerHTML =
    '<thead><tr><th>Cuándo</th><th>Valor estimado</th><th>Intervalo del 80 %</th><th>P(30 mg/g o más)</th></tr></thead><tbody>' +
    r.projection
      .map(
        (p) =>
          `<tr><td>${p.months === 0 ? 'Hoy' : `En ${p.months} meses`}</td><td>${mg(p.median)} mg/g</td><td>${mg(p.low)}–${mg(p.high)} mg/g</td><td>${pct(p.p_a2_plus)}</td></tr>`,
      )
      .join('') +
    '</tbody>'
}

function wire(kind, text) {
  const el = $('#lab-wire')
  el.className = `wire ${kind}`
  el.lastElementChild.textContent = text
}

async function ask() {
  controller?.abort()
  controller = new AbortController()
  wire('busy', 'POST /api/model/albuminuria …')
  try {
    const { data, ms } = await api(
      '/model/albuminuria',
      { patient: state.patient, samples: state.samples, as_of: asOf() },
      controller.signal,
    )
    renderResult(data)
    wire('', `POST /api/model/albuminuria · 200 · ${ms} ms · ${state.samples.length} muestra${state.samples.length === 1 ? '' : 's'} · evaluado a ${fecha(data.as_of)}`)
  } catch (error) {
    if (error.name === 'AbortError') return
    wire('err', error.message)
  }
}

function changed({ debounce = false } = {}) {
  renderInputs()
  clearTimeout(timer)
  timer = setTimeout(ask, debounce ? 160 : 0)
}

function loadExample(id) {
  const example = examples.find((e) => e.id === id)
  if (!example) {
    state.patient = { age: 58, female: true, diabetes: false, egfr: 88 }
    state.samples = []
  } else {
    const body = example.albuminuria
    state.patient = {
      age: Math.round(body.patient.age),
      female: body.patient.female,
      diabetes: body.patient.diabetes,
      egfr: Math.round(body.patient.egfr ?? 90),
    }
    state.samples = body.samples.map((s) => ({ ...s }))
  }
  changed()
}

export async function initLab() {
  picker($('#lab-pick-a'), { title: 'Albúmina', unit: 'mg/l', scale: ALBUMIN, value: state.strip.albumin, onPick: (v) => (state.strip.albumin = v) })
  picker($('#lab-pick-c'), { title: 'Creatinina', unit: 'mg/dl', scale: CREATININE, value: state.strip.creatinine, onPick: (v) => (state.strip.creatinine = v) })

  const dateInput = $('#lab-date')
  dateInput.value = TODAY
  dateInput.max = TODAY

  $('#lab-age').addEventListener('input', (e) => { state.patient.age = Number(e.target.value); changed({ debounce: true }) })
  $('#lab-egfr').addEventListener('input', (e) => { state.patient.egfr = Number(e.target.value); changed({ debounce: true }) })
  $('#lab-sex').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) { state.patient.female = b.dataset.v === 'true'; changed() } })
  $('#lab-dm').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) { state.patient.diabetes = b.dataset.v === 'true'; changed() } })
  $('#lab-kind').addEventListener('click', (e) => {
    const b = e.target.closest('button')
    if (!b) return
    state.kind = b.dataset.v
    $$('#lab-kind button').forEach((o) => o.setAttribute('aria-pressed', String(o === b)))
    $('#lab-add-strip').hidden = state.kind !== 'tira'
    $('#lab-add-lab').hidden = state.kind !== 'laboratorio'
  })
  $('#lab-add').addEventListener('click', () => {
    const date = dateInput.value || TODAY
    if (state.samples.length >= 30) return wire('err', 'El modelo admite como mucho 30 muestras.')
    if (state.kind === 'tira') {
      state.samples.push({ kind: 'tira', date, albumin_mg_l: state.strip.albumin, creatinine_mg_dl: state.strip.creatinine })
    } else {
      const uacr = Number($('#lab-uacr').value)
      if (!(uacr > 0 && uacr <= 30000)) return wire('err', 'El cociente debe estar entre 1 y 30.000 mg/g.')
      state.samples.push({ kind: 'laboratorio', date, uacr, sample_type: $('#lab-type').value })
    }
    state.samples.sort((a, b) => a.date.localeCompare(b.date))
    changed()
  })
  $('#lab-samples').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-i]')
    if (!b) return
    state.samples.splice(Number(b.dataset.i), 1)
    changed()
  })
  $('#lab-clear').addEventListener('click', () => { state.samples = []; changed() })

  const select = $('#lab-example')
  select.innerHTML = '<option value="">Empezar de cero: mujer de 58 años, sin muestras</option>'
  select.addEventListener('change', () => loadExample(select.value))
  $('.legend', $('#lab-out')).insertAdjacentHTML(
    'beforeend',
    '<span><svg width="14" height="14" viewBox="-7 -7 14 14"><rect x="-5" y="-5" width="10" height="10" fill="#fff" stroke="#0d2226" stroke-width="2"/></svg>Tira</span>' +
      '<span><svg width="14" height="14" viewBox="-7 -7 14 14"><circle r="5.5" fill="#0d2226"/></svg>Laboratorio, primera orina</span>' +
      '<span><svg width="16" height="16" viewBox="-8 -8 16 16"><path d="M0-7 7 0 0 7-7 0z" fill="#fff" stroke="#0d2226" stroke-width="2"/></svg>Laboratorio, aleatoria</span>',
  )

  changed()
  try {
    const { data } = await api('/model/examples')
    examples = data.patients
    select.insertAdjacentHTML('beforeend', examples.map((e) => `<option value="${esc(e.id)}">${esc(e.title)}</option>`).join(''))
  } catch {
    // Sin ejemplos se puede seguir usando el bloque a mano.
  }
}
