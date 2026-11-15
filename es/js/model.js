// «El modelo, en vivo»: cada cambio es una petición real a POST /api/model/albuminuria.
import { $, $$, ALBUMIN, CREATININE, api, esc, fecha, fixPct, mg, num, padColor, pct, picker, stateChip } from './lib.js'

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
let last = null // última respuesta del modelo: la gráfica se vuelve a pintar si cambia de tamaño

const asOf = () => state.samples.reduce((latest, s) => (s.date > latest ? s.date : latest), TODAY)

const NBSP = ' '
const icon = (paths) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`
const ICON_X = icon('<path d="M7 7l10 10M17 7 7 17"/>')
const ICON_INFO = icon('<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>')

// Forma de cada muestra: la misma en la lista, en la gráfica y en la leyenda.
const SHAPE = {
  tira: '<rect x="-5" y="-5" width="10" height="10" class="m-tira"/>',
  first_morning: '<circle r="5.5" class="m-fm"/>',
  random: '<path d="M0-7 7 0 0 7-7 0z" class="m-rnd"/>',
}
const shapeOf = (s) => (s.kind === 'tira' ? SHAPE.tira : SHAPE[s.sample_type === 'random' ? 'random' : 'first_morning'])

function sampleLabel(s) {
  return s.kind === 'tira'
    ? `Tira: albúmina ${s.albumin_mg_l} mg/l, creatinina ${s.creatinine_mg_dl} mg/dl`
    : `Laboratorio: ${num(s.uacr)} mg/g, ${s.sample_type === 'random' ? 'muestra aleatoria' : 'primera orina de la mañana'}`
}

function sampleItem(s, i) {
  const when = fecha(s.date)
  const strip = s.kind === 'tira'
  // La tira enseña sus dos almohadillas leídas; el laboratorio, la forma con la que sale en la gráfica.
  const mark = strip
    ? `<span class="mk" aria-hidden="true"><i style="background:${padColor(ALBUMIN, s.albumin_mg_l)}"></i><i style="background:${padColor(CREATININE, s.creatinine_mg_dl)}"></i></span>`
    : `<span class="mk" aria-hidden="true"><svg viewBox="-8 -8 16 16">${shapeOf(s)}</svg></span>`
  const value = strip
    ? `${s.albumin_mg_l} mg/l · ${s.creatinine_mg_dl} mg/dl`
    : `${num(s.uacr)} mg/g · ${s.sample_type === 'random' ? 'aleatoria' : 'primera orina'}`
  return (
    `<li title="${esc(sampleLabel(s))} (${when})">${mark}` +
    `<span class="txt"><b>${esc(value)}</b><small>${strip ? 'Tira en casa' : 'Laboratorio'} · <span class="dt">${when}</span></small></span>` +
    `<button type="button" data-i="${i}" aria-label="Quitar la muestra del ${when}: ${esc(sampleLabel(s))}" title="Quitar la muestra">${ICON_X}</button></li>`
  )
}

function setRange(selector, value) {
  const el = $(selector)
  el.value = value
  const min = Number(el.min)
  const max = Number(el.max)
  el.style.setProperty('--p', `${((Number(el.value) - min) / (max - min)) * 100}%`)
}

function renderInputs() {
  const p = state.patient
  setRange('#lab-age', p.age)
  $('#lab-age-out').textContent = `${p.age} años`
  setRange('#lab-egfr', p.egfr)
  $('#lab-egfr-out').textContent = String(p.egfr)
  $$('#lab-sex button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === String(p.female))))
  $$('#lab-dm button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === String(p.diabetes))))
  const n = state.samples.length
  $('#lab-count').textContent = String(n)
  $('#lab-clear').disabled = n === 0
  $('#lab-samples').innerHTML = n
    ? state.samples.map(sampleItem).join('')
    : `<li class="empty">${ICON_INFO}<span>Sin muestras. El modelo solo conoce la historia clínica: añade una tira.</span></li>`
}

// --- Gráfica: lo que el filtro cree sobre el valor verdadero, en escala logarítmica ----------
// Se pinta al tamaño real de su caja, para que el texto no se encoja ni se estire.
let W = 640
let H = 250
const M = { l: 12, r: 14, t: 28, b: 42 }
const X0 = Math.log(0.6)
const X1 = Math.log(3000)
const x = (v) => M.l + ((Math.log(Math.min(Math.max(v, 0.6), 3000)) - X0) / (X1 - X0)) * (W - M.l - M.r)
const TICKS = [1, 3, 10, 30, 100, 300, 1000, 3000]
const ZONES = [
  ['A1', 0.6, 30],
  ['A2', 30, 300],
  ['A3', 300, 3000],
]
const f1 = (v) => v.toFixed(1)

function curve(dist, peak, close) {
  const base = H - M.b
  const pts = dist.uacr
    .map((u, i) => [u, dist.mass[i]])
    .filter(([u]) => u >= 0.6 && u <= 3000)
    .map(([u, m]) => `${f1(x(u))},${f1(base - (m / peak) * (base - M.t - 10))}`)
  if (!pts.length) return ''
  return close ? `M${f1(x(0.6))},${base}L${pts.join('L')}L${f1(x(3000))},${base}Z` : `M${pts.join('L')}`
}

function marker(s) {
  const title = `<title>${esc(s.label)}: ${mg(s.value_mg_g)} mg/g (${fecha(s.date)})</title>`
  return `<g transform="translate(${f1(x(s.value_mg_g))} ${H - M.b})">${title}${shapeOf(s)}</g>`
}

function renderChart(r) {
  const svg = $('#lab-chart')
  const box = svg.getBoundingClientRect()
  if (box.width > 80 && box.height > 80) {
    W = Math.round(box.width)
    H = Math.round(box.height)
  }
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`)
  const base = H - M.b
  const top = M.t - 8
  const peak = Math.max(...r.belief.mass, ...r.prior.mass)
  const zones = ZONES.map(
    ([name, lo, hi], k) =>
      `<rect class="zone z${k + 1}" x="${f1(x(lo))}" y="${top}" width="${f1(x(hi) - x(lo))}" height="${base - top}"/>` +
      `<text class="zl" x="${f1(x(lo) + 7)}" y="${top - 7}">${name}</text>`,
  ).join('')
  const refs = [30, 300].map((v) => `<line class="ref" x1="${f1(x(v))}" x2="${f1(x(v))}" y1="${top}" y2="${base}"/>`).join('')
  const ticks = (W < 420 ? TICKS.filter((v) => v !== 3 && v !== 3000) : TICKS).map(
    (v) =>
      `<line class="gl" x1="${f1(x(v))}" x2="${f1(x(v))}" y1="${base}" y2="${base + 5}"/>` +
      `<text x="${f1(x(v))}" y="${base + 18}" text-anchor="middle">${num(v)}</text>`,
  ).join('')
  const area = curve(r.belief, peak, true)
  const lo = x(r.low)
  const hi = x(r.high)
  const med = x(r.median)
  const right = W - M.r - med > 70
  const axis = W < 480 ? 'CAC verdadero, mg/g (escala logarítmica)' : 'cociente albúmina/creatinina verdadero, mg/g (escala logarítmica)'
  svg.innerHTML = `
    <defs>
      <linearGradient id="lab-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#5fbe8c" stop-opacity=".5"/><stop offset="1" stop-color="#5fbe8c" stop-opacity=".1"/>
      </linearGradient>
      <clipPath id="lab-clip"><rect x="${f1(lo)}" y="0" width="${f1(Math.max(1, hi - lo))}" height="${H}"/></clipPath>
    </defs>
    ${zones}${refs}
    <path d="${area}" fill="url(#lab-grad)"/>
    <path class="belief-in" d="${area}" clip-path="url(#lab-clip)"/>
    <path class="belief-line" d="${curve(r.belief, peak, false)}"/>
    <path class="prior" d="${curve(r.prior, peak, false)}"/>
    <line class="med" x1="${f1(med)}" x2="${f1(med)}" y1="${M.t + 4}" y2="${base}"/>
    <text class="med-l" x="${f1(med + (right ? 6 : -6))}" y="${M.t + 13}" text-anchor="${right ? 'start' : 'end'}">mediana</text>
    <line class="axis" x1="${M.l}" x2="${W - M.r}" y1="${base}" y2="${base}"/>
    ${ticks}
    <text class="ax" x="${W - M.r}" y="${H - 5}" text-anchor="end">${axis}</text>
    ${r.samples.map(marker).join('')}`
}

// --- Proyección en pequeño: mediana e intervalo del 80 % si no se vuelve a medir --------------
// Solo se dibuja si su caja tiene sitio; los números exactos están en la tabla de debajo.
function renderFan(r) {
  const svg = $('#lab-fan')
  const box = svg.getBoundingClientRect()
  const w = Math.round(box.width)
  const h = Math.round(box.height)
  if (w < 140 || h < 64 || !r.projection?.length) {
    svg.innerHTML = ''
    return
  }
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`)
  const m = { l: 5, r: 5, t: 10, b: 20 }
  const pts = r.projection
  const span = Math.max(...pts.map((p) => p.months)) || 12
  const lo = Math.min(30, ...pts.map((p) => p.low)) / 1.6
  const hi = Math.max(30, ...pts.map((p) => p.high)) * 1.6
  const px = (months) => m.l + (months / span) * (w - m.l - m.r)
  const py = (v) => m.t + ((Math.log(hi) - Math.log(v)) / (Math.log(hi) - Math.log(lo))) * (h - m.t - m.b)
  const at = (p, key) => `${f1(px(p.months))},${f1(py(p[key]))}`
  const band = `M${pts.map((p) => at(p, 'high')).join('L')}L${[...pts].reverse().map((p) => at(p, 'low')).join('L')}Z`
  const y30 = py(30)
  const end = pts[pts.length - 1]
  const below = Math.abs(py(end.median) - y30) < 16 || Math.abs(py(end.high) - y30) < 10
  const labels = pts
    .map((p, i) => {
      const anchor = i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'middle'
      return `<text x="${f1(px(p.months))}" y="${h - 4}" text-anchor="${anchor}">${p.months === 0 ? 'Hoy' : `${p.months} meses`}</text>`
    })
    .join('')
  svg.innerHTML = `
    <line class="base" x1="${m.l}" x2="${w - m.r}" y1="${h - m.b}" y2="${h - m.b}"/>
    <path class="band" d="${band}"/>
    <line class="thr" x1="${m.l}" x2="${w - m.r}" y1="${f1(y30)}" y2="${f1(y30)}"/>
    <text class="thr-l" x="${w - m.r}" y="${f1(below ? y30 + 13 : y30 - 5)}" text-anchor="end">30 mg/g</text>
    <path class="mid" d="M${pts.map((p) => at(p, 'median')).join('L')}"/>
    ${pts.map((p) => `<circle class="dot" cx="${f1(px(p.months))}" cy="${f1(py(p.median))}" r="3.2"/>`).join('')}
    ${labels}`
}

function renderResult(r) {
  last = r
  $('#lab-state').innerHTML = stateChip(r.status, r.status_label)
  // En monoespaciada la coma ocupa una celda entera: se recoge un poco en las cifras grandes.
  const tight = (text) => esc(text).replace(/,/g, '<span class="dec">,</span>')
  $('#lab-median').innerHTML = `${tight(mg(r.median))}<small>mg/g</small>`
  $('#lab-interval').innerHTML = `${tight(`${mg(r.low)}–${mg(r.high)}`)}<small>mg/g</small>`
  const bars = [
    ['A1', 'menos de 30 mg/g', r.p_a1, 'var(--a10)'],
    ['A2', '30 a 300 mg/g', r.p_a2, 'var(--a80)'],
    ['A3', 'más de 300 mg/g', r.p_a3, 'var(--a150)'],
  ]
  $('#lab-bars').innerHTML = bars
    .map(
      ([cat, range, p, color]) =>
        `<li${cat === r.category ? ' class="lead"' : ''}><span class="cat">${cat}</span><span class="rng">${range}</span>` +
        `<span class="bar"><i style="width:${(p * 100).toFixed(1)}%;background:${color}"></i></span><b>${esc(pct(p))}</b></li>`,
    )
    .join('')
  const next = $('#lab-next')
  const resolves = r.next_sample_resolves
  next.hidden = !resolves
  if (resolves) {
    next.innerHTML =
      '<p class="cap">Otra muestra resolvería la duda</p>' +
      [
        ['Primera orina', resolves.first_morning],
        ['Aleatoria', resolves.random],
      ]
        .map(
          ([label, p]) =>
            `<p class="pr"><span>${label}</span><span class="bar"><i style="width:${(p * 100).toFixed(1)}%"></i></span><b>${esc(pct(p))}</b></p>`,
        )
        .join('')
  }
  $('#lab-action').textContent = fixPct(r.action)
  renderChart(r)
  renderFan(r)
  $('#lab-proj').innerHTML =
    `<thead><tr><th scope="col">Cuándo</th><th scope="col">Valor<br>estimado</th><th scope="col">Intervalo<br>del 80${NBSP}%</th><th scope="col">P(30${NBSP}mg/g<br>o más)</th></tr></thead><tbody>` +
    r.projection
      .map(
        (p) =>
          `<tr${p.months === 0 ? ' class="now"' : ''}><th scope="row">${p.months === 0 ? 'Hoy' : `En ${p.months} meses`}</th>` +
          `<td>${mg(p.median)}</td><td>${mg(p.low)}–${mg(p.high)}</td><td>${esc(pct(p.p_a2_plus))}</td></tr>`,
      )
      .join('') +
    '</tbody>'
}

function wire(kind, text) {
  const el = $('#lab-wire')
  el.className = `wire ${kind}`
  el.lastElementChild.textContent = text
  el.title = text // la barra de estado puede cortar el texto en pantallas justas
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
    let sample
    if (state.kind === 'tira') {
      sample = { kind: 'tira', date, albumin_mg_l: state.strip.albumin, creatinine_mg_dl: state.strip.creatinine }
    } else {
      const uacr = Number($('#lab-uacr').value)
      if (!(uacr > 0 && uacr <= 30000)) return wire('err', 'El cociente debe estar entre 1 y 30.000 mg/g.')
      sample = { kind: 'laboratorio', date, uacr, sample_type: $('#lab-type').value }
    }
    state.samples.push(sample)
    state.samples.sort((a, b) => a.date.localeCompare(b.date))
    changed()
    // Enseña la muestra recién añadida dentro de la lista (que hace scroll en su panel).
    const item = $('#lab-samples').children[state.samples.indexOf(sample)]
    if (item) {
      item.classList.add('new')
      item.scrollIntoView({ block: 'nearest' })
    }
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

  // Las gráficas se adaptan a su caja: si la ventana cambia, se vuelven a pintar con la última respuesta.
  let frame = 0
  const resized = new ResizeObserver(() => {
    if (!last) return
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => {
      renderChart(last)
      renderFan(last)
    })
  })
  resized.observe($('#lab-chart'))
  resized.observe($('#lab-fan'))

  changed()
  try {
    const { data } = await api('/model/examples')
    examples = data.patients
    select.insertAdjacentHTML('beforeend', examples.map((e) => `<option value="${esc(e.id)}">${esc(e.title)}</option>`).join(''))
  } catch {
    // Sin ejemplos se puede seguir usando el bloque a mano.
  }
}
