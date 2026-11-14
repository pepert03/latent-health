// La app del paciente, dentro del marco de teléfono. No guarda nada en el servidor: el estado
// (paciente, fecha, muestras) vive aquí y cada pantalla se lo manda entero al modelo.
import { $, $$, ALBUMIN, CREATININE, addDays, api, daysBetween, esc, fecha, fechaLarga, fixPct, mg, padColor, pct, picker, stateChip } from './lib.js'

const view = () => $('#app-view')

const app = {
  config: null,
  patient: null,
  today: null,
  samples: [],
  step: null, // última respuesta de POST /api/home/step
  due: null, // { kind: 'tira' | 'tubo', on } o null si no hay nada pendiente
  flow: 'idle', // idle | questions | strip | tube | result
  answers: {},
  strip: { albumin: 10, creatinine: 100 },
  history: [], // pruebas hechas en esta sesión, con lo que contestó el modelo
  tab: 'hoy',
  chat: [],
  chatMode: null,
  chatBusy: false,
  sent: [],
  extras: null, // tensión y pulso (lecturas sintéticas de ejemplo)
  error: null,
}

const OUTCOME = {
  fin_normal: 'Ya está',
  tira: 'Repite mañana',
  tubo: 'Manda el tubo',
  repetir_cronicidad: 'Repetir a los 3 meses',
  centro: 'Te llamará tu centro de salud',
  esperar: 'Prueba aplazada',
}

// --- Llamadas al modelo ---------------------------------------------------------------------
function logCall(text, ms) {
  $('#app-calls').insertAdjacentHTML('afterbegin', `<li>${text}${ms === undefined ? '' : ` · ${ms} ms`}</li>`)
}

const patientBody = () => ({
  age: app.patient.age,
  female: app.patient.female,
  diabetes: app.patient.diabetes,
  egfr: app.patient.egfr,
})

async function askStep(answers) {
  const body = { patient: patientBody(), channel: app.patient.channel, today: app.today, samples: app.samples }
  if (answers) body.answers = answers
  const { data, ms } = await api('/home/step', body)
  logCall(`<b>POST /api/home/step</b> → ${esc(data.action_label)} · ${fecha(data.on)}`, ms)
  return data
}

/** Qué queda pendiente tras una respuesta del modelo. */
function dueFrom(step, previous) {
  if (step.action === 'tira') return { kind: 'tira', on: step.on }
  if (step.action === 'tubo' || step.action === 'repetir_cronicidad') return { kind: 'tubo', on: step.on }
  if (step.action === 'esperar') return { kind: previous?.kind ?? 'tira', on: step.on }
  if (step.action === 'fin_normal') return { kind: 'tira', on: step.on, yearly: true }
  return null // centro: sigue en el centro de salud
}

async function guard(task) {
  app.error = null
  try {
    await task()
  } catch (error) {
    app.error = error.message
  }
  render()
}

// --- Acciones ------------------------------------------------------------------------------
async function start(patient) {
  Object.assign(app, {
    patient,
    today: app.config.today,
    samples: [],
    history: [],
    flow: 'idle',
    chat: [],
    chatMode: null,
    sent: [],
    extras: null,
    tab: 'hoy',
    step: null,
    due: null,
  })
  $$('#app-people button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.id === patient.id)))
  $('#app-calls').innerHTML = ''
  selectTab('hoy')
  await guard(async () => {
    app.step = await askStep()
    app.due = dueFrom(app.step, null)
  })
  loadExtras()
}

async function advance() {
  if (!app.due) return
  app.today = app.due.on
  await guard(async () => {
    if (app.due.yearly) {
      // Ha pasado un año: el modelo decide de nuevo qué toca.
      app.step = await askStep()
      app.due = dueFrom(app.step, app.due)
      if (app.due) {
        app.today = app.due.on
        app.due.yearly = false
      }
    }
    app.flow = 'idle'
  })
}

function beginTest() {
  app.answers = Object.fromEntries(app.step.questions.map((q) => [q.key, false]))
  app.flow = 'questions'
  render()
}

async function submitAnswers() {
  await guard(async () => {
    const step = await askStep(app.answers)
    if (step.action === 'esperar') {
      app.step = step
      app.due = dueFrom(step, app.due)
      app.history.unshift({ date: app.today, label: 'Prueba aplazada por tus respuestas', step })
      app.flow = 'result'
    } else {
      app.flow = app.due.kind === 'tubo' ? 'tube' : 'strip'
    }
  })
}

async function submitSample(sample) {
  await guard(async () => {
    app.samples.push({ ...sample, date: app.today, answers: app.answers })
    const step = await askStep()
    app.step = step
    app.due = dueFrom(step, app.due)
    const echo = step.samples[step.samples.length - 1]
    app.history.unshift({ date: app.today, label: echo?.label ?? 'Prueba', step })
    app.flow = 'result'
  })
}

async function loadExtras() {
  const day = (n) => addDays(app.config.today, n)
  const sbp = [131, 133, 127, 129, 129, 131, 126, 128, 128, 127, 130, 132, 125, 126]
  const dbp = [82, 83, 79, 80, 81, 82, 78, 79, 80, 78, 81, 82, 77, 78]
  const readings = sbp.map((s, i) => ({ date: day(-9 + Math.floor(i / 2)), sbp: s, dbp: dbp[i], evening: i % 2 === 1 }))
  const patient = app.patient
  try {
    const [bp, rhythm] = await Promise.all([
      api('/home/bp', { readings }),
      api('/home/rhythm', {
        age: patient.age,
        female: patient.female,
        checks: [
          { date: day(-6), irregular: false },
          { date: day(-4), irregular: false },
        ],
      }),
    ])
    if (app.patient !== patient) return
    logCall('<b>POST /api/home/bp</b> → 14 lecturas de una semana', bp.ms)
    logCall('<b>POST /api/home/rhythm</b> → 2 comprobaciones del pulso', rhythm.ms)
    app.extras = { bp: bp.data, rhythm: rhythm.data, from: day(-9), to: day(-3) }
    if (app.tab === 'registro') render()
  } catch {
    // El registro sigue funcionando sin estas dos medidas.
  }
}

async function sendChat(text) {
  const content = text.trim()
  if (!content || app.chatBusy) return
  app.chat.push({ role: 'user', content })
  app.chatBusy = true
  render()
  try {
    const { data, ms } = await api('/home/chat', {
      patient: patientBody(),
      channel: app.patient.channel,
      today: app.today,
      samples: app.samples,
      messages: app.chat.slice(-19), // número impar: la conversación empieza y acaba en el paciente
    })
    app.chat.push({ role: 'assistant', content: data.reply })
    app.chatMode = data
    logCall(`<b>POST /api/home/chat</b> → ${data.mode === 'ia' ? 'modelo de lenguaje' : 'modo guiado'}`, ms)
  } catch (error) {
    app.chat.push({ role: 'assistant', content: error.message })
  }
  app.chatBusy = false
  render()
}

// --- Pantallas -----------------------------------------------------------------------------
function kitLine() {
  const k = app.step.kit
  const bars = (total, used, cls) => Array.from({ length: total }, (_, i) => `<i class="${cls} ${i < used ? 'used' : ''}"></i>`).join('')
  return `<p class="kitline" aria-label="Kit: ${k.strips_used} de ${k.strips_total} tiras usadas y ${k.tubes_used} de ${k.tubes_total} tubos usados">${bars(k.strips_total, k.strips_used, '')}<span>${k.strips_total - k.strips_used} tiras</span>${bars(k.tubes_total, k.tubes_used, 'tube')}<span>${k.tubes_total - k.tubes_used} tubos</span></p>`
}

function screenHome() {
  const s = app.step
  const name = esc(app.patient.name.split(' ')[0])
  const head = `<p class="date">${fechaLarga(app.today)}</p><h3>Hola, ${name}</h3>`
  if (!app.due) {
    return `${head}<div class="remind done"><p class="date">Sin pruebas pendientes en casa</p><p class="when">${esc(OUTCOME[s.action] ?? s.action_label)}</p><p>${esc(s.patient_message)}</p></div>
      <button type="button" class="btn btn-2" data-act="tab" data-tab="medica">Escribir a mi médica</button>${kitLine()}`
  }
  const left = daysBetween(app.today, app.due.on)
  const what = app.due.kind === 'tubo' ? 'Tubo para el laboratorio' : 'Tira de orina'
  if (left <= 0) {
    return `${head}<div class="remind"><p class="date">Hoy toca</p><p class="when">${what}</p><p>Con la primera orina del día. Antes, unas preguntas rápidas.</p>
      <button type="button" class="btn" data-act="begin">Empezar la prueba</button></div>${kitLine()}`
  }
  const when = left === 1 ? 'Mañana' : `Dentro de ${left} días`
  return `${head}<div class="remind"><p class="date">Recordatorio · ${what}</p><p class="when">${when}, ${fechaLarga(app.due.on).toLowerCase()}</p><p>${esc(s.patient_message)}</p></div>
    ${kitLine()}
    <button type="button" class="btn btn-2" data-act="advance">Simular que llega ese día</button>
    <p class="hint">Botón de la demo: adelanta la fecha del móvil hasta el día de la prueba.</p>`
}

function screenQuestions() {
  return `<p class="date">${fechaLarga(app.today)}</p><h3>Antes de la prueba</h3><p>Algunas cosas alteran el resultado sin que pase nada. Si hoy se da alguna, mejor otro día.</p>
    <ul class="qs">${app.step.questions
      .map(
        (q) =>
          `<li><span>${esc(q.text)}</span><span class="yn"><button type="button" data-act="answer" data-key="${q.key}" data-v="true" aria-pressed="${app.answers[q.key] === true}">Sí</button><button type="button" data-act="answer" data-key="${q.key}" data-v="false" aria-pressed="${app.answers[q.key] === false}">No</button></span></li>`,
      )
      .join('')}</ul>
    <button type="button" class="btn btn-1" data-act="answers">Continuar</button>`
}

function screenStrip() {
  return `<p class="date">${fechaLarga(app.today)}</p><h3>Lee la tira</h3>
    <div class="ministrip" aria-hidden="true"><i id="ms-a" style="background:${padColor(ALBUMIN, app.strip.albumin)}"></i><i id="ms-c" style="background:${padColor(CREATININE, app.strip.creatinine)}"></i><span>TIRA</span></div>
    <div class="picker" id="app-pick-a"></div><div class="picker" id="app-pick-c"></div>
    <p class="hint">En la app real la cámara del móvil lee los colores. En esta demo los eliges tú.</p>
    <button type="button" class="btn btn-1" data-act="strip">Enviar lectura</button>`
}

function screenTube() {
  return `<p class="date">${fechaLarga(app.today)}</p><h3>Manda el tubo</h3>
    <p>Llena el tubo con la primera orina del día y échalo al buzón en el sobre del kit.</p>
    <h4>Demo · resultado que devuelve el laboratorio, en mg/g</h4>
    <div class="chips">${[6, 18, 31, 58, 64, 71, 140, 380].map((v) => `<button type="button" data-act="tube" data-v="${v}">${v}</button>`).join('')}</div>
    <p class="hint">El laboratorio mide el valor exacto. Por debajo de 30 mg/g es normal.</p>`
}

function screenResult() {
  const s = app.step
  return `<p class="date">${fechaLarga(app.today)}</p><h3>${esc(OUTCOME[s.action] ?? s.action_label)}</h3>
    <div class="bubble"><p class="who">LatentHealth</p><p>${esc(s.patient_message)}</p></div>
    <div class="statbox"><h4>Lo que sabe ahora el modelo</h4><p style="margin:6px 0">${stateChip(s.assessment.status, s.assessment.status_label)}</p>
      <p>Probabilidad de albúmina mantenida en la orina: <b class="mono">${pct(s.p_albuminuria)}</b></p></div>
    <button type="button" class="btn btn-1" data-act="home">Ver mi recordatorio</button>
    <button type="button" class="btn btn-2" data-act="tab" data-tab="chat">Preguntar al asistente</button>`
}

function screenLog() {
  const s = app.step
  const a = s.assessment
  const tests = app.history.length
    ? `<ul class="log">${app.history
        .map(
          (h) =>
            `<li><i style="background:${h.step.action === 'fin_normal' ? 'var(--a30)' : h.step.action === 'esperar' ? 'var(--line)' : 'var(--teal)'}"></i><span><b>${esc(h.label)}</b></span><span class="dt">${fecha(h.date)} · ${esc(OUTCOME[h.step.action] ?? h.step.action_label)}</span></li>`,
        )
        .join('')}</ul>`
    : '<p class="hint">Aún no has hecho ninguna prueba de orina. Cuando la hagas aparecerá aquí.</p>'
  const estimate = s.samples.length
    ? `<p class="v">${mg(a.median)} mg/g</p><p class="hint">Valor estimado con todas tus pruebas. Intervalo del 80 %: ${mg(a.low)}–${mg(a.high)} mg/g. Por debajo de 30 es normal.</p>`
    : '<p class="hint">Sin pruebas todavía.</p>'
  const x = app.extras
  const extras = x
    ? `<h4>Tensión · del ${fecha(x.from)} al ${fecha(x.to)}</h4><div class="statbox"><p class="v">${Math.round(x.bp.sbp)}/${Math.round(x.bp.dbp)} mmHg</p><p>${esc(x.bp.message)}</p><p class="hint">${x.bp.n} lecturas en ${x.bp.days} días, sin contar el primero.</p></div>
       <h4>Pulso · 2 comprobaciones</h4><div class="statbox"><p class="v">${pct(x.rhythm.probability)}</p><p class="hint">Probabilidad de fibrilación auricular con dos pulsos regulares. Antes de medir: ${pct(x.rhythm.prior)}.</p></div>
       <p class="hint">Tensión y pulso son lecturas sintéticas de ejemplo; el cálculo es del modelo.</p>`
    : ''
  return `<h3>Mi registro</h3><div class="statbox"><h4>Orina · albúmina</h4><p style="margin:6px 0">${stateChip(a.status, a.status_label)}</p>${estimate}</div>
    <h4>Pruebas de orina en casa</h4>${tests}${extras}`
}

function screenChat() {
  const name = esc(app.patient.name.split(' ')[0])
  const mode = app.chatMode
    ? app.chatMode.mode === 'ia'
      ? `Respuestas redactadas por IA (${esc(app.chatMode.model)}) con los datos del modelo clínico.`
      : 'Modo guiado: sin modelo de lenguaje conectado, respuestas fijas con los datos del modelo clínico.'
    : 'Explica y orienta. No diagnostica ni pauta tratamientos.'
  const ideas = ['¿Cómo voy?', '¿Cuándo me toca la próxima prueba?', '¿Por qué tengo que repetir?', '¿Qué es la albúmina?']
  return `<div class="chat"><div class="chat-log" id="chat-log">
      <p class="msg">Hola, ${name}. Soy el asistente de LatentHealth. Pregúntame por tus pruebas de casa.</p>
      ${app.chat.map((m) => `<p class="msg ${m.role === 'user' ? 'me' : ''}">${esc(m.content)}</p>`).join('')}
      ${app.chatBusy ? '<p class="msg wait">Escribiendo…</p>' : ''}
    </div>
    <div class="chat-foot">
      <div class="chips">${ideas.map((t) => `<button type="button" data-act="idea">${t}</button>`).join('')}</div>
      <form id="chat-form"><input type="text" id="chat-input" placeholder="Escribe tu pregunta" autocomplete="off" maxlength="600" aria-label="Tu pregunta" /><button class="send" type="submit" aria-label="Enviar">↑</button></form>
      <p class="mode">${mode}</p>
    </div></div>`
}

function screenDoctor() {
  const sent = app.sent
    .map((m) => `<div class="sent"><p class="date">Enviado el ${fecha(m.date)}${m.attach ? ' · con tus pruebas de casa' : ''}</p><p>${esc(m.text)}</p></div>`)
    .join('')
  return `<h3>Mi médica</h3><p>Centro de salud · Medicina de familia</p>
    <label for="doc-text"><h4>Tu mensaje</h4></label>
    <textarea id="doc-text" rows="4" placeholder="Cuéntale qué necesitas"></textarea>
    <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="doc-attach" checked style="width:20px;height:20px;accent-color:var(--teal)" />Adjuntar mis pruebas de casa</label>
    <button type="button" class="btn btn-1" data-act="doctor">Enviar a mi médica</button>
    <button type="button" class="btn btn-2" data-act="callme">Pedir que me llamen</button>
    ${sent}
    <div class="statbox"><h4>Lo que queda anotado en tu historia</h4><p>${esc(fixPct(app.step.clinician_note))}</p></div>
    <p class="hint">Prototipo: el mensaje no sale de este navegador. Si es una urgencia, llama al 112.</p>`
}

function render() {
  const el = view()
  if (!app.step) {
    el.innerHTML = app.error ? `<div class="sent"><p>${esc(app.error)}</p></div>` : '<p class="hint">Conectando con el modelo…</p>'
    return
  }
  let html
  if (app.tab === 'registro') html = screenLog()
  else if (app.tab === 'chat') html = screenChat()
  else if (app.tab === 'medica') html = screenDoctor()
  else html = { idle: screenHome, questions: screenQuestions, strip: screenStrip, tube: screenTube, result: screenResult }[app.flow]()
  el.innerHTML = `<div class="scr-in">${app.error ? `<div class="sent"><p>${esc(app.error)}</p></div>` : ''}${html}</div>`
  el.scrollTop = 0

  if (app.tab === 'hoy' && app.flow === 'strip') {
    picker($('#app-pick-a'), { title: 'Albúmina', unit: 'mg/l', scale: ALBUMIN, value: app.strip.albumin, onPick: (v) => { app.strip.albumin = v; $('#ms-a').style.background = padColor(ALBUMIN, v) } })
    picker($('#app-pick-c'), { title: 'Creatinina', unit: 'mg/dl', scale: CREATININE, value: app.strip.creatinine, onPick: (v) => { app.strip.creatinine = v; $('#ms-c').style.background = padColor(CREATININE, v) } })
  }
  if (app.tab === 'chat') {
    const log = $('#chat-log')
    log.scrollTop = log.scrollHeight
    $('#chat-form').addEventListener('submit', (event) => {
      event.preventDefault()
      sendChat($('#chat-input').value)
    })
    if (!app.chatBusy && document.activeElement === document.body) $('#chat-input').focus({ preventScroll: true })
  }
}

function selectTab(tab) {
  app.tab = tab
  $$('#app-tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)))
}

function onViewClick(event) {
  const button = event.target.closest('[data-act]')
  if (!button) return
  const act = button.dataset.act
  if (act === 'advance') advance()
  else if (act === 'begin') beginTest()
  else if (act === 'answer') {
    app.answers[button.dataset.key] = button.dataset.v === 'true'
    $$(`[data-key="${button.dataset.key}"]`, view()).forEach((b) => b.setAttribute('aria-pressed', String(b === button)))
  } else if (act === 'answers') submitAnswers()
  else if (act === 'strip') submitSample({ kind: 'tira', albumin_mg_l: app.strip.albumin, creatinine_mg_dl: app.strip.creatinine })
  else if (act === 'tube') submitSample({ kind: 'tubo', uacr: Number(button.dataset.v), creatinine_mg_dl: 100 })
  else if (act === 'home') { app.flow = 'idle'; render() }
  else if (act === 'tab') { selectTab(button.dataset.tab); render() }
  else if (act === 'idea') sendChat(button.textContent)
  else if (act === 'doctor' || act === 'callme') {
    const text = act === 'callme' ? 'Quiero que me llamen del centro de salud.' : $('#doc-text').value.trim()
    if (!text) return $('#doc-text').focus()
    app.sent.unshift({ date: app.today, text, attach: $('#doc-attach').checked })
    render()
  }
}

export async function initApp() {
  view().addEventListener('click', onViewClick)
  $('#app-tabs').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-tab]')
    if (!button) return
    selectTab(button.dataset.tab)
    render()
  })
  $('#app-reset').addEventListener('click', () => app.patient && start(app.patient))
  $('#app-people').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-id]')
    if (button) start(app.config.patients.find((p) => p.id === button.dataset.id))
  })
  try {
    const { data } = await api('/home/config')
    app.config = data
    $('#app-people').innerHTML = data.patients
      .map((p) => `<button type="button" data-id="${esc(p.id)}" aria-pressed="false"><b>${esc(p.name)}</b><small>${esc(p.summary)}</small></button>`)
      .join('')
    await start(data.patients.find((p) => p.id === 'pilar') ?? data.patients[0])
  } catch (error) {
    app.error = error.message
    render()
  }
}
