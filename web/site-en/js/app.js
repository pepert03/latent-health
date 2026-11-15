// The patient app, inside the phone. Nothing is stored on the server: the state (patient, date,
// samples) lives here and every screen sends all of it to the model. Demo-only controls
// (skip ahead, pick a patient, reset) sit outside the phone.
import { $, $$, ALBUMIN, CREATININE, addDays, api, daysBetween, esc, fecha, fechaLarga, fixPct, mg, padColor, pct, picker, stateChip } from './lib.js'
import { camSVG, setPad } from './camara.js'

const view = () => $('#app-view')

const app = {
  config: null,
  patient: null,
  today: null,
  samples: [],
  step: null, // last response from POST /api/home/step
  due: null, // { kind: 'tira' | 'tubo', on } or null if nothing is pending
  flow: 'idle', // idle | questions | strip | tube | result
  answers: {},
  qi: 0, // questions already answered in the pre-test chat
  qaTyping: false,
  watch: null, // { brand, state: 'connecting' | 'on' } or null
  sheet: null, // sheet open inside the phone: 'watch'
  toast: null,
  screenKey: '',
  strip: { albumin: 10, creatinine: 100 },
  history: [], // tests done in this session, with the model's response
  tab: 'hoy',
  chat: [],
  chatMode: null,
  chatBusy: false,
  sent: [],
  extras: null, // blood pressure and pulse (synthetic sample readings)
  error: null,
}

const OUTCOME = {
  fin_normal: 'All done',
  tira: 'Repeat tomorrow',
  tubo: 'Send the tube',
  repetir_cronicidad: 'Repeat in 3 months',
  centro: 'Your health center will call you',
  esperar: 'Test postponed',
}

// --- Calls to the model ----------------------------------------------------------------------
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

/** What is still pending after a model response. */
function dueFrom(step, previous) {
  if (step.action === 'tira') return { kind: 'tira', on: step.on }
  if (step.action === 'tubo' || step.action === 'repetir_cronicidad') return { kind: 'tubo', on: step.on }
  if (step.action === 'esperar') return { kind: previous?.kind ?? 'tira', on: step.on }
  if (step.action === 'fin_normal') return { kind: 'tira', on: step.on, yearly: true }
  return null // centro: followed up at the health center
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

// --- Actions -------------------------------------------------------------------------------
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
    qi: 0,
    qaTyping: false,
    sheet: null,
    screenKey: '',
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
  selectTab('hoy')
  await guard(async () => {
    if (app.due.yearly) {
      // A year has passed: the model decides again what is due.
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
  app.qi = 0
  app.flow = 'questions'
  render()
}

/** Answer to a pre-test chat question; the next one arrives after "typing". */
function answerQuestion(yes) {
  const q = app.step.questions[app.qi]
  if (!q || app.qaTyping) return
  app.answers[q.key] = yes
  app.qi += 1
  app.qaTyping = true
  render()
  setTimeout(() => {
    app.qaTyping = false
    if (app.flow === 'questions') render()
  }, 700)
}

function connectWatch(brand) {
  app.sheet = null
  app.watch = { brand, state: 'connecting' }
  render()
  setTimeout(() => {
    if (app.watch?.brand !== brand) return
    app.watch.state = 'on'
    showToast(`${brand} connected`)
    render()
  }, 1500)
}

function showToast(text) {
  app.toast = text
  clearTimeout(showToast.t)
  showToast.t = setTimeout(() => {
    app.toast = null
    renderOverlay()
  }, 2200)
}

async function submitAnswers() {
  await guard(async () => {
    const step = await askStep(app.answers)
    if (step.action === 'esperar') {
      app.step = step
      app.due = dueFrom(step, app.due)
      app.history.unshift({ date: app.today, label: 'Test postponed based on your answers', step })
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
    app.history.unshift({ date: app.today, label: echo?.label ?? 'Test', step })
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
    logCall('<b>POST /api/home/bp</b> → 14 readings over one week', bp.ms)
    logCall('<b>POST /api/home/rhythm</b> → 2 pulse checks', rhythm.ms)
    app.extras = { bp: bp.data, rhythm: rhythm.data, readings, from: day(-9), to: day(-3) }
    if (app.tab === 'registro' || (app.tab === 'hoy' && app.flow === 'idle')) render()
  } catch {
    // The log still works without these two measurements.
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
      messages: app.chat.slice(-19), // odd number: the conversation starts and ends with the patient
    })
    app.chat.push({ role: 'assistant', content: data.reply })
    app.chatMode = data
    logCall(`<b>POST /api/home/chat</b> → ${data.mode === 'ia' ? 'language model' : 'guided mode'}`, ms)
  } catch (error) {
    app.chat.push({ role: 'assistant', content: error.message })
  }
  app.chatBusy = false
  render()
}

// --- UI pieces -------------------------------------------------------------------------------
const firstName = () => esc(app.patient.name.split(' ')[0])
const initials = () => esc(app.patient.name.split(' ').map((w) => w[0]).slice(0, 2).join(''))
const steps = (n) => `<div class="a-steps" aria-hidden="true">${[1, 2, 3].map((i) => `<i class="${i <= n ? 'on' : ''}"></i>`).join('')}</div>`
const PADS = '<span class="a-pads" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
const BOT = '<span class="bot" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'

function ring(p, color, cls = 'a-ring', label = 'urine albumin') {
  const v = Math.round(Math.min(1, Math.max(0, p ?? 0)) * 100)
  return `<div class="ring ${cls}" style="--v:${v}"><svg viewBox="0 0 120 120" aria-hidden="true"><circle class="ring-bg" cx="60" cy="60" r="50"/><circle class="ring-fg" cx="60" cy="60" r="50" style="stroke:${color}"/></svg><p><b>${pct(p)}</b>${label ? `<span>${label}</span>` : ''}</p></div>`
}

/** Home screen widgets: the kit, albumin and, once they arrive, blood pressure and pulse. */
function widgets() {
  const k = app.step.kit
  const bars = (total, used, cls) => Array.from({ length: total }, (_, i) => `<i class="${cls} ${i < used ? 'used' : ''}"></i>`).join('')
  const left = k.strips_total - k.strips_used
  const kit = `<div class="a-wid"><p class="a-kicker">Your kit</p><p class="a-big">${left} ${left === 1 ? 'strip' : 'strips'}</p><p class="a-hint">${k.tubes_total - k.tubes_used} lab tube${k.tubes_total - k.tubes_used === 1 ? '' : 's'}</p>
    <p class="kitline viz" aria-label="Kit: ${k.strips_used} of ${k.strips_total} strips used and ${k.tubes_used} of ${k.tubes_total} tubes used">${bars(k.strips_total, k.strips_used, '')}${bars(k.tubes_total, k.tubes_used, 'tube')}</p></div>`
  const alb = `<div class="a-wid"><p class="a-kicker">Albumin</p><p class="a-hint">Chance it is high</p>${ring(app.step.p_albuminuria, 'var(--teal)', 'ring--mini', '')}</div>`
  const x = app.extras
  let more = ''
  if (x) {
    const hi = (s) => s >= 135
    const minibars = x.readings.map((r, i) => `<i class="${hi(r.sbp) ? 'hi' : ''}" style="--h:${Math.max(12, Math.min(100, ((r.sbp - 100) / 50) * 100))}%;--k:${i}"></i>`).join('')
    const from = app.watch?.state === 'on' ? `from your ${esc(app.watch.brand)}` : 'with the camera'
    more = `<div class="a-wid"><p class="a-kicker">Blood pressure</p><p class="a-big">${Math.round(x.bp.sbp)}/${Math.round(x.bp.dbp)}</p><p class="a-hint">one-week average</p><p class="minibars viz">${minibars}</p></div>
      <div class="a-wid"><p class="a-kicker">Pulse</p><p class="a-big">Regular</p><p class="a-hint">Atrial fibrillation: ${pct(x.rhythm.probability)} · ${from}</p></div>`
  }
  return `<p class="a-sec">Your measurements</p><div class="a-grid">${kit}${alb}${more}</div>${watchCard()}`
}

const WATCH_ICON =
  '<svg class="ai" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="3.3"/><path d="M8.6 6l.8-3.2h5.2l.8 3.2M8.6 18l.8 3.2h5.2l.8-3.2"/><path d="M8.6 12.3h1.7l1-2 1.4 3.6 1-1.6h1.7"/></svg>'
const ECG_PATH =
  'M0 22h14l3-4 3 4h6l2 5 3-24 3 27 2-8h8l4-5 4 5h16l3-4 3 4h6l2 5 3-24 3 27 2-8h8l4-5 4 5h16l3-4 3 4h6l2 5 3-24 3 27 2-8h8l4-5 4 5h12'

/** Watch card: Apple Watch in one tap, the rest in a sheet; once connected, its latest ECG. */
function watchCard() {
  const w = app.watch
  if (w?.state === 'on') {
    return `<div class="a-card a-watch on"><div class="a-watch-top">${WATCH_ICON}<div><b>${esc(w.brand)}</b><span>Connected · daily pulse and 30 s ECG</span></div><i class="live" aria-hidden="true"></i></div>
      <svg class="ecg" viewBox="0 0 200 32" preserveAspectRatio="none" aria-hidden="true"><path d="${ECG_PATH}"/></svg>
      <p class="a-hint">Latest ECG, today at 8:12 AM: regular rhythm, 68 bpm. If it ever comes out irregular, we'll let you know.</p></div>`
  }
  if (w?.state === 'connecting') {
    return `<div class="a-card a-watch"><div class="a-watch-top">${WATCH_ICON}<div><b>Connecting to ${esc(w.brand)}…</b><span>Accept the Health permission on your watch</span></div><i class="spin" aria-hidden="true"></i></div></div>`
  }
  return `<div class="a-card a-watch"><div class="a-watch-top">${WATCH_ICON}<div><b>Connect your watch</b><span>Pulse and a 30 s ECG, nothing else to do</span></div></div>
    <button type="button" class="a-btn" data-act="watch" data-brand="Apple Watch">${WATCH_ICON}Connect Apple Watch</button>
    <button type="button" class="a-btn sec" data-act="watch-more">Other watches</button></div>`
}

const WATCHES = ['Samsung Galaxy Watch', 'Google Pixel Watch', 'Fitbit', 'Garmin', 'Withings ScanWatch', 'Huawei Watch']

/** What sits above the screen: the watch sheet and the short toast. */
function renderOverlay() {
  const host = $('#app-overlay')
  if (!host) return
  let html = ''
  if (app.sheet === 'watch') {
    html += `<div class="a-scrim" data-act="sheet-close"></div><div class="a-bottom" role="dialog" aria-label="Choose your watch">
      <i class="grab" aria-hidden="true"></i><p class="a-kicker">Connect a watch</p><h4>Which one do you have?</h4>
      <ul class="watch-list">
        <li><button type="button" data-act="watch" data-brand="Apple Watch">${WATCH_ICON}<span>Apple Watch</span><small>iPhone Health</small></button></li>
        ${WATCHES.map((name) => `<li><button type="button" data-act="watch" data-brand="${name}">${WATCH_ICON}<span>${name}</span><small>Health Connect</small></button></li>`).join('')}
      </ul>
      <button type="button" class="a-btn sec" data-act="sheet-close">No watch: pulse with the camera</button></div>`
  }
  if (app.toast) html += `<p class="a-toast" role="status">${esc(app.toast)}</p>`
  host.innerHTML = html
}

const RING_COLOR = { fin_normal: 'var(--a80)', esperar: 'var(--ink3)', tira: 'var(--c200)', tubo: 'var(--c200)', repetir_cronicidad: 'var(--c300)', centro: 'var(--c300)' }

// --- Screens -------------------------------------------------------------------------------
function screenHome() {
  const s = app.step
  const head = `<div class="a-head"><div><p class="a-date">${fechaLarga(app.today)}</p><h3>Hi, ${firstName()}</h3></div><span class="avatar" aria-hidden="true">${initials()}</span></div>`
  if (!app.due) {
    return `${head}<div class="a-hero">${PADS}<p class="a-kicker">No home tests pending</p><p class="when">${esc(OUTCOME[s.action] ?? s.action_label)}</p><p>${esc(s.patient_message)}</p>
      <button type="button" class="a-btn light" data-act="tab" data-tab="medico">Message my doctor</button></div>${widgets()}`
  }
  const left = daysBetween(app.today, app.due.on)
  const what = app.due.kind === 'tubo' ? 'Lab tube' : 'Urine strip'
  if (left <= 0) {
    return `${head}<div class="a-hero">${PADS}<p class="a-kicker">Due today</p><p class="when">${what}</p><p>With your first urine of the day. First, a few quick questions.</p>
      <button type="button" class="a-btn light" data-act="begin">Start the test</button></div>${widgets()}`
  }
  const when = left === 1 ? 'Tomorrow' : `In ${left} days`
  return `${head}<div class="a-hero">${PADS}<p class="a-kicker">Next test · ${what.toLowerCase()}</p><p class="when">${when}</p><p>${fechaLarga(app.due.on)}. ${esc(s.patient_message)}</p></div>
    ${widgets()}`
}

const COUNT = ['', 'one quick question', 'two quick questions', 'three quick questions', 'four quick questions', 'five quick questions']

/** Before the test, the assistant asks one thing at a time; answered with "No" or "Yes". */
function screenQuestions() {
  const qs = app.step.questions
  const n = app.qi
  const done = qs.slice(0, n)
  const yes = done.some((q) => app.answers[q.key])
  const finished = n >= qs.length
  // Only new items animate: the answer just given (while "typing") and whatever comes next.
  const fresh = (i) => i === n - 1 && app.qaTyping
  let log = `<p class="msg${n ? ' old' : ''}">Hi, ${firstName()}. Before the strip, ${COUNT[qs.length] ?? `${qs.length} quick questions`}: if any answer is yes, better another day, because the strip would read high for no reason.</p>`
  log += done
    .map((q, i) => `<p class="msg old">${esc(q.text)}</p><p class="msg me${fresh(i) ? '' : ' old'}">${app.answers[q.key] ? 'Yes' : 'No'}</p>`)
    .join('')
  if (app.qaTyping) log += '<p class="msg wait"><span></span></p>'
  else if (!finished) log += `<p class="msg">${esc(qs[n].text)}</p>`
  else
    log += `<p class="msg">${yes ? "Thanks. Then let's do it another day: I'll tell you when and remind you." : "All set. Grab the cup and a pouch: I'll guide you with the camera."}</p>`
  const foot =
    finished && !app.qaTyping
      ? `<button type="button" class="a-btn" data-act="answers">${yes ? 'See when to repeat' : 'Open the camera'}</button>`
      : `<div class="qa-reply"><button type="button" data-act="qa" data-v="no"${app.qaTyping || finished ? ' disabled' : ''}>No</button><button type="button" data-act="qa" data-v="si"${app.qaTyping || finished ? ' disabled' : ''}>Yes</button></div>`
  return `${steps(1)}<div class="a-chathead">${BOT}<div><b>Assistant</b><span>Before the test · ${Math.min(n + (finished ? 0 : 1), qs.length)} of ${qs.length}</span></div></div>
    <div class="chat"><div class="chat-log">${log}</div><div class="chat-foot">${foot}</div></div>`
}

function screenStrip() {
  const a = padColor(ALBUMIN, app.strip.albumin)
  const c = padColor(CREATININE, app.strip.creatinine)
  return `${steps(2)}<h3>Read the strip</h3>
    <div class="cam cam--app" id="app-cam">
      ${camSVG({ id: 'app-cam', a, c, valA: `${app.strip.albumin} mg/l`, valC: `${app.strip.creatinine} mg/dl`, view: 'top' })}
      <i class="cam-scan"></i>
      <p class="cam-pill cam-pill--find"><i></i>Looking for the card…</p>
      <p class="cam-pill cam-pill--cal"><i></i>Adjusting the light</p>
      <p class="cam-pill cam-pill--ok ok"><i></i>Strip read</p>
    </div>
    <div class="a-sheet"><p class="a-kicker">What the camera read</p>
      <div class="picker" id="app-pick-a"></div><div class="picker" id="app-pick-c"></div>
      <p class="a-hint" style="margin-top:.6em">In this demo, tap the color you see on your strip.</p>
    </div>
    <button type="button" class="a-btn" data-act="strip">Send reading</button>`
}

const TUBE_ART = `<div class="tube-art" aria-hidden="true">
  <svg viewBox="0 0 40 110"><rect x="8" y="2" width="24" height="14" rx="3" fill="#6cb99f"/><path d="M11 16v78a9 9 0 0 0 18 0V16Z" fill="#fff" stroke="#0d2226" stroke-width="2"/><path d="M11 52v42a9 9 0 0 0 18 0V52Z" fill="#f3ebc8"/></svg>
  <svg viewBox="0 0 120 84"><rect x="2" y="2" width="116" height="80" rx="6" fill="#fff" stroke="#0d2226" stroke-width="2"/><path d="M2 6l58 40 58-40" fill="none" stroke="#0d2226" stroke-width="2"/><circle cx="60" cy="46" r="9" fill="#a9d3ca"/></svg>
</div>`

function screenTube() {
  return `${steps(2)}<p class="a-date">${fechaLarga(app.today)}</p><h3>Send the tube</h3>
    <div class="a-card">${TUBE_ART}<p>Fill the tube with your first urine of the day, put it in the kit box and drop it in a mailbox: postage is prepaid. The lab measures the exact value.</p></div>
    <h4>Demo · what the lab sends back, in mg/g</h4>
    <div class="chips">${[6, 18, 31, 58, 64, 71, 140, 380].map((v) => `<button type="button" data-act="tube" data-v="${v}">${v}</button>`).join('')}</div>
    <p class="a-hint">Below 30 mg/g is normal.</p>`
}

function screenResult() {
  const s = app.step
  return `${steps(3)}<p class="a-date">Your result · ${fecha(app.today)}</p><h3>${esc(OUTCOME[s.action] ?? s.action_label)}</h3>
    ${ring(s.p_albuminuria, RING_COLOR[s.action] ?? 'var(--teal)')}
    <div class="bubble"><p class="who">LatentHealth</p><p>${esc(s.patient_message)}</p></div>
    <p>${stateChip(s.assessment.status, s.assessment.status_label)}</p>
    <button type="button" class="a-btn" data-act="home">See my reminder</button>
    <button type="button" class="a-btn sec" data-act="tab" data-tab="chat">Ask the assistant</button>`
}

function screenLog() {
  const s = app.step
  const a = s.assessment
  const tests = app.history.length
    ? `<ul class="log">${app.history
        .map(
          (h) =>
            `<li><i style="background:${h.step.action === 'fin_normal' ? 'var(--a80)' : h.step.action === 'esperar' ? 'var(--line)' : 'var(--c100)'}"></i><b>${esc(h.label)}</b><span class="dt">${fecha(h.date)} · ${esc(OUTCOME[h.step.action] ?? h.step.action_label)}</span></li>`,
        )
        .join('')}</ul>`
    : "<p class=\"a-hint\">You haven't done any tests yet. They will show up here.</p>"
  let estimate = '<p class="a-hint">No tests yet.</p>'
  if (s.samples.length) {
    const scale = (v) => Math.min(100, Math.max(0, (Math.log10(Math.max(v, 1)) / Math.log10(300)) * 100))
    estimate = `<p class="v">${mg(a.median)} <small>mg/g</small></p>
      <div class="range"><i class="range-band" style="--a:${scale(a.low)}%;--b:${scale(a.high)}%"></i><i class="range-dot" style="--x:${scale(a.median)}%"></i><i class="range-lim" style="--x:${scale(30)}%"></i></div>
      <p class="a-hint">Between ${mg(a.low)} and ${mg(a.high)} mg/g (80%). The red line is 30: below it is normal.</p>`
  }
  const x = app.extras
  const extras = x
    ? `<h4>Blood pressure · ${fecha(x.from)} to ${fecha(x.to)}</h4><div class="a-card a-est"><p class="v">${Math.round(x.bp.sbp)}/${Math.round(x.bp.dbp)} <small>mmHg</small></p><p>${esc(x.bp.message)}</p><p class="a-hint">${x.bp.n} readings over ${x.bp.days} days, not counting the first.</p></div>
       <h4>Pulse · 2 checks</h4><div class="a-card a-est"><p class="v">${pct(x.rhythm.probability)}</p><p class="a-hint">Chance of atrial fibrillation after two regular pulse checks. Before measuring: ${pct(x.rhythm.prior)}.</p></div>`
    : ''
  return `<h3>My log</h3><div class="a-card a-est"><p class="a-kicker">Urine albumin</p><p>${stateChip(a.status, a.status_label)}</p>${estimate}</div>
    <h4>Home tests</h4>${tests}${extras}`
}

function screenChat() {
  const mode = app.chatMode
    ? app.chatMode.mode === 'ia'
      ? `Answers written by AI (${esc(app.chatMode.model)}) from the clinical model's data.`
      : "Guided mode: fixed answers from the clinical model's data."
    : 'Explains and guides. Does not diagnose or prescribe treatment.'
  const ideas = ['How am I doing?', 'When is my next test?', 'Why do I have to repeat?', 'What is albumin?']
  const last = app.chat.length - 1
  return `<div class="a-chathead">${BOT}<div><b>Assistant</b><span>Explains your tests · does not diagnose</span></div></div>
    <div class="chat"><div class="chat-log" id="chat-log">
      <p class="msg${app.chat.length ? ' old' : ''}">Hi, ${firstName()}. Ask me about your home tests: the results, why to repeat, or when the next one is due.</p>
      ${app.chat.map((m, i) => `<p class="msg ${m.role === 'user' ? 'me' : ''}${i < last - 1 ? ' old' : ''}">${esc(m.content)}</p>`).join('')}
      ${app.chatBusy ? '<p class="msg wait"><span></span>Typing…</p>' : ''}
    </div>
    <div class="chat-foot">
      <div class="chips">${ideas.map((t) => `<button type="button" data-act="idea">${t}</button>`).join('')}</div>
      <form id="chat-form"><input type="text" id="chat-input" placeholder="Type your question" autocomplete="off" maxlength="600" aria-label="Your question" /><button class="send" type="submit" aria-label="Send">↑</button></form>
      <p class="mode">${mode}</p>
    </div></div>`
}

function screenDoctor() {
  const sent = app.sent
    .map((m) => `<div class="sent"><p class="dt">Sent ${fecha(m.date)}${m.attach ? ' · with your home tests' : ''}</p><p>${esc(m.text)}</p></div>`)
    .join('')
  return `<h3>My doctor</h3>
    <div class="a-card a-doc"><span class="avatar">CR</span><div><b>Carmen Ruiz</b><span>Family medicine · your health center</span></div></div>
    <label for="doc-text" class="a-date">Your message</label>
    <textarea id="doc-text" rows="4" placeholder="Tell her what you need"></textarea>
    <div class="toggle-row"><span>Attach my home tests</span><button type="button" class="switch" role="switch" id="doc-attach" data-act="attach" aria-checked="true" aria-label="Attach my home tests"></button></div>
    <button type="button" class="a-btn" data-act="doctor">Send to my doctor</button>
    <button type="button" class="a-btn sec" data-act="callme">Request a call back</button>
    ${sent}
    <div class="a-card"><p class="a-kicker">What goes in your medical record</p><p>${esc(fixPct(app.step.clinician_note))}</p></div>
    <p class="a-hint">Prototype: the message never leaves this browser. In an emergency, call 112.</p>`
}

function render() {
  const el = view()
  const advanceButton = $('#app-advance')
  if (advanceButton) advanceButton.disabled = !app.due || daysBetween(app.today, app.due.on) <= 0 || app.flow !== 'idle'
  if (!app.step) {
    el.innerHTML = app.error ? `<div class="sent"><p>${esc(app.error)}</p></div>` : '<p class="a-hint" style="margin-top:2em">Connecting to the model…</p>'
    return
  }
  let html
  if (app.tab === 'registro') html = screenLog()
  else if (app.tab === 'chat') html = screenChat()
  else if (app.tab === 'medico') html = screenDoctor()
  else html = { idle: screenHome, questions: screenQuestions, strip: screenStrip, tube: screenTube, result: screenResult }[app.flow]()
  // Chats fill the screen with messages at the bottom; if the screen doesn't change, it doesn't re-animate.
  const key = app.tab === 'hoy' ? `hoy:${app.flow}` : app.tab
  const chatty = app.tab === 'chat' || (app.tab === 'hoy' && app.flow === 'questions')
  const still = key === app.screenKey
  app.screenKey = key
  el.innerHTML = `<div class="scr-in${chatty ? ' scr-chat' : ''}${still ? ' still' : ''}">${app.error ? `<div class="sent"><p>${esc(app.error)}</p></div>` : ''}${html}</div>`
  el.scrollTop = chatty ? el.scrollHeight : still ? el.scrollTop : 0
  renderOverlay()

  if (app.tab === 'hoy' && app.flow === 'strip') {
    const show = (key, scale, v, unit) => setPad($('#app-cam'), key, padColor(scale, v), `${v} ${unit}`)
    picker($('#app-pick-a'), { title: 'Albumin', unit: 'mg/l', scale: ALBUMIN, value: app.strip.albumin, onPick: (v) => { app.strip.albumin = v; show('a', ALBUMIN, v, 'mg/l') } })
    picker($('#app-pick-c'), { title: 'Creatinine', unit: 'mg/dl', scale: CREATININE, value: app.strip.creatinine, onPick: (v) => { app.strip.creatinine = v; show('c', CREATININE, v, 'mg/dl') } })
  }
  if (app.tab === 'chat') {
    el.scrollTop = el.scrollHeight
    $('#chat-form').addEventListener('submit', (event) => {
      event.preventDefault()
      sendChat($('#chat-input').value)
    })
  }
}

function selectTab(tab) {
  app.tab = tab
  $$('#app-tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)))
}

function onAct(event) {
  const button = event.target.closest('[data-act]')
  if (!button || !button.closest('#app')) return
  const act = button.dataset.act
  if (act === 'advance') advance()
  else if (act === 'begin') beginTest()
  else if (act === 'toggle') {
    const on = button.getAttribute('aria-checked') !== 'true'
    app.answers[button.dataset.key] = on
    button.setAttribute('aria-checked', String(on))
  } else if (act === 'attach') button.setAttribute('aria-checked', String(button.getAttribute('aria-checked') !== 'true'))
  else if (act === 'answers') submitAnswers()
  else if (act === 'qa') answerQuestion(button.dataset.v === 'si')
  else if (act === 'watch') connectWatch(button.dataset.brand)
  else if (act === 'watch-more') {
    app.sheet = 'watch'
    renderOverlay()
  } else if (act === 'sheet-close') {
    app.sheet = null
    renderOverlay()
  }
  else if (act === 'strip') submitSample({ kind: 'tira', albumin_mg_l: app.strip.albumin, creatinine_mg_dl: app.strip.creatinine })
  else if (act === 'tube') submitSample({ kind: 'tubo', uacr: Number(button.dataset.v), creatinine_mg_dl: 100 })
  else if (act === 'home') {
    app.flow = 'idle'
    render()
  } else if (act === 'tab') {
    selectTab(button.dataset.tab)
    render()
  } else if (act === 'idea') sendChat(button.textContent)
  else if (act === 'doctor' || act === 'callme') {
    const text = act === 'callme' ? 'I would like the health center to call me.' : $('#doc-text').value.trim()
    if (!text) return $('#doc-text').focus()
    app.sent.unshift({ date: app.today, text, attach: $('#doc-attach').getAttribute('aria-checked') === 'true' })
    render()
  }
}

export async function initApp() {
  document.addEventListener('click', onAct)
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
