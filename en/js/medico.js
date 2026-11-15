import { API_BASE } from './config.js'

// Doctor dashboard (section #medico): the LatentHealth clinic as a desktop application.
//
// - Today: the practice list worklist (Act, Measure and Nothing pending), with a one-click action
//   per row, and the patient file: what the model believes (KDIGO grid, albuminuria, eGFR trend),
//   home tests, cardiovascular risk and what comes prepared (lab order, note with ICD-10 code,
//   guideline suggestions and message to the patient).
// - Patients, Messages (Pilar's), Kits and Practice indicators.
//
// The patients are fictional. Their numbers were computed by the real model (src/latenthealth) and
// are copied at the end of this file. Files the API can represent in full are recomputed live with
// POST /api/model/assess (Julián also with /albuminuria and /egfr-trend); if the server does not
// answer, the saved copy stays. Practice list figures (kits, coverage, funnel) are example data and
// labelled as such. This is decision support: nothing here prescribes a treatment.

const NB = ' '
const TODAY = '2026-11-16'
const MEDIR_TOTAL = 41
const SIN_PENDIENTES = 1454

// --- US English formatting ---------------------------------------------------------------------
const formats = new Map()
function num(value, decimals = 0) {
  if (!Number.isFinite(value)) return '—'
  if (!formats.has(decimals)) {
    formats.set(decimals, new Intl.NumberFormat('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: 'always' }))
  }
  return formats.get(decimals).format(value).replace('-', '−')
}
/** Probability 0-1 -> "61%". Never shows 0% or 100% unless it is. */
function pct(p) {
  if (p == null || !Number.isFinite(p)) return '—'
  const v = Math.min(1, Math.max(0, p)) * 100
  if (v > 0 && v < 1) return `<${NB}1%`
  if (v > 99 && v < 100) return `>${NB}99%`
  return `${num(v)}%`
}
const pct1 = (p) => `${num(p * 100, 1)}%`
const range = (a, b, d = 0) => `${num(a, d)}–${num(b, d)}`
/** Model texts: keep "4%" as is, and use a true minus sign. */
const fixPct = (text) => String(text ?? '').replace(/(^|[\s(])-(\d)/g, '$1−$2')
const esc = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const val = (x, m) => (typeof x === 'function' ? x(m) : x)
const MES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MESES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const days = (iso) => Date.parse(`${iso}T00:00:00Z`) / 86_400_000

// --- Icons: 24 grid, 1.75 stroke and currentColor ----------------------------------------------
const PATHS = {
  hoy: '<path d="M9 6.5h11M9 12h11M9 17.5h11"/><path d="m3.6 6.5 1.2 1.2 1.9-2.4M3.6 12l1.2 1.2 1.9-2.4M3.6 17.5l1.2 1.2 1.9-2.4"/>',
  users: '<circle cx="9" cy="8.2" r="3.3"/><path d="M3 19.5c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><path d="M15.6 5.1a3.3 3.3 0 0 1 0 6.2M17.6 14.4c2 .7 3.4 2.6 3.4 5.1"/>',
  msg: '<path d="M4.5 5h15a1 1 0 0 1 1 1v9.5a1 1 0 0 1-1 1h-9l-4.5 3.5v-3.5h-1.5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/>',
  box: '<path d="M3.5 7.6 12 3.3l8.5 4.3v8.8L12 20.7l-8.5-4.3z"/><path d="M3.5 7.6 12 11.9l8.5-4.3M12 11.9v8.8M7.8 5.4l8.4 4.3"/>',
  chart: '<path d="M4 20V11.5M9.3 20V5M14.7 20v-6.5M20 20V8.5"/>',
  search: '<circle cx="10.8" cy="10.8" r="6.3"/><path d="m20 20-4.6-4.6"/>',
  cal: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 9.6h17M8 3v4M16 3v4"/>',
  calplus: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 9.6h17M8 3v4M16 3v4M12 12.6v5M9.5 15.1h5"/>',
  clipcheck: '<path d="M9 3.5h6v3H9z"/><path d="M15 5h3.5v15.5h-13V5H9"/><path d="m9 13.6 2.2 2.2 4.3-4.6"/>',
  flask: '<path d="M9.5 3.5h5M10.5 3.5v5.4L5.6 17.5a2.1 2.1 0 0 0 1.9 3h9a2.1 2.1 0 0 0 1.9-3l-4.9-8.6V3.5"/><path d="M7.7 14.6h8.6"/>',
  tube: '<path d="M8.5 3.5h7M9.8 3.5v13.7a2.2 2.2 0 0 0 4.4 0V3.5"/><path d="M9.8 11.2h4.4"/>',
  send: '<path d="m20.5 3.5-10.4 10.4"/><path d="m20.5 3.5-6.6 17-3.8-6.6-6.6-3.8z"/>',
  copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2"/><path d="M15.5 8.5v-3a2 2 0 0 0-2-2h-8a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3"/>',
  reply: '<path d="M9.5 6.5 4 12l5.5 5.5"/><path d="M4.5 12H14a6 6 0 0 1 6 6v1.5"/>',
  bell: '<path d="M6 16.5v-5a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  cross: '<path d="M9.5 3.5h5v6h6v5h-6v6h-5v-6h-6v-5h6z"/>',
  drop: '<path d="M12 3.5c3.2 4 5.7 7.2 5.7 10.3a5.7 5.7 0 0 1-11.4 0c0-3.1 2.5-6.3 5.7-10.3z"/>',
  gauge: '<path d="M3.8 16.5a8.2 8.2 0 1 1 16.4 0"/><path d="m12 16.5 4.2-4.6"/><circle cx="12" cy="16.5" r="1.3"/><path d="M6.6 9.9l1.2 1M12 6.4v1.5M17.4 9.9l-1.2 1"/>',
  pulse: '<path d="M3 12.5h3.6l2-5.2 3.6 10.2 2.5-6.6 1.6 1.6H21"/>',
  watch: '<rect x="6.8" y="6.5" width="10.4" height="11" rx="2.6"/><path d="m8.8 6.5.7-3.5h5l.7 3.5M8.8 17.5l.7 3.5h5l.7-3.5"/><path d="M9.3 12h1.6l1-2.2 1.2 4.4 1-2.2h.6"/>',
  heart: '<path d="M12 20s-7.5-4.6-7.5-10.1A4.3 4.3 0 0 1 12 7.4a4.3 4.3 0 0 1 7.5 2.5C19.5 15.4 12 20 12 20z"/>',
  glu: '<rect x="7" y="3.5" width="10" height="17" rx="2.5"/><rect x="9.3" y="6.3" width="5.4" height="4.4" rx="1"/><path d="M12 14.2v3.2"/>',
  strip: '<rect x="9" y="2.5" width="6" height="19" rx="1"/><path d="M9 12.6h6M9 16.6h6"/>',
  mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="m4.2 7 7.8 6 7.8-6"/>',
  doc: '<path d="M6 3.5h8.5L19 8v12.5H6z"/><path d="M14 3.5v5h5M9 12.5h7M9 16.5h7"/>',
  book: '<path d="M4.5 5.5a2 2 0 0 1 2-2h13v15h-13a2 2 0 0 0-2 2z"/><path d="M4.5 18.5v2M8.5 8h7M8.5 11.5h5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.9v.2"/>',
  alert: '<path d="M10.3 4.6 2.9 17.5a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4.6a2 2 0 0 0-3.4 0z"/><path d="M12 9.6v4.4M12 17.2v.2"/>',
  auto: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4.5V9h-4.5"/>',
  phone: '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
  call: '<path d="M5 4.5h3.5l1.7 4.3-2.2 1.4a11 11 0 0 0 5.8 5.8l1.4-2.2 4.3 1.7V19a1.5 1.5 0 0 1-1.6 1.5A15.5 15.5 0 0 1 3.5 6.1 1.5 1.5 0 0 1 5 4.5z"/>',
  paperclip: '<path d="m19.5 11.4-7.8 7.8a5 5 0 0 1-7-7l8.3-8.3a3.3 3.3 0 0 1 4.7 4.7l-8.3 8.2a1.7 1.7 0 0 1-2.3-2.3l7.6-7.6"/>',
  shield: '<path d="M12 3.5 19 6v5.5c0 4.3-3 7.7-7 9-4-1.3-7-4.7-7-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
  lungs: '<path d="M12 4v7M12 11c-1.5 1-3 1.5-4.5 1.5M12 11c1.5 1 3 1.5 4.5 1.5"/><path d="M8 7.5C5.5 8 4 11 4 15c0 2.5 1 4 3 4 2.5 0 3-2 3-5V9M16 7.5c2.5.5 4 3.5 4 7.5 0 2.5-1 4-3 4-2.5 0-3-2-3-5V9"/>',
}
const ico = (name, cls = '') => `<svg class="dr-ico${cls ? ` dr-ico-${cls}` : ''}" viewBox="0 0 24 24" aria-hidden="true">${PATHS[name] ?? ''}</svg>`


// --- The strip's color chart -------------------------------------------------------------------
const ALB = { 10: 'var(--a10)', 30: 'var(--a30)', 80: 'var(--a80)', 150: 'var(--a150)' }
const CRE = { 10: 'var(--c10)', 50: 'var(--c50)', 100: 'var(--c100)', 200: 'var(--c200)', 300: 'var(--c300)' }
const swatch = (a, c) =>
  `<span class="dr-swatch" role="img" aria-label="Strip: albumin ${a} mg/L, creatinine ${c} mg/dL" title="Albumin ${a} mg/L · creatinine ${c} mg/dL"><i style="background:${ALB[a]}"></i><i style="background:${CRE[c]}"></i></span>`

// Albuminuria states: color, shape and text (those of the "Strip" style sheet).
const STATE_ICON = {
  sin_medir: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2"/>',
  descartada: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2"/>',
  dudosa: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M13 1v12H1z" fill="currentColor"/>',
  pendiente_cronicidad: '<path d="M0 0h14v14H0z" fill="currentColor"/>',
  confirmada: '<path d="M0 0h14v14H0z" fill="currentColor"/><path d="M3 7.4l2.8 2.8L11 4.2" fill="none" stroke="#0b7774" stroke-width="2"/>',
}
const stateChip = (status, label) =>
  `<span class="dr-state dr-st-${status}"><svg viewBox="0 0 14 14" aria-hidden="true">${STATE_ICON[status] ?? ''}</svg>${esc(label)}</span>`

// --- What each one-click action does -----------------------------------------------------------
const ACTIONS = {
  registrar: { label: 'Record diagnosis', icon: 'clipcheck', done: 'Diagnosis recorded' },
  analitica: { label: 'Order labs', icon: 'flask', done: 'Labs ordered' },
  kit: { label: 'Send kit', icon: 'box', done: 'Kit sent' },
  citar: { label: 'Book visit', icon: 'calplus', done: 'Visit booked' },
  farmacia: { label: 'Notify pharmacy', icon: 'cross', done: 'Pharmacy notified' },
  recordar: { label: 'Remind', icon: 'bell', done: 'Reminder sent' },
  responder: { label: 'Reply', icon: 'reply', done: 'Replied' },
}
const GROUPS = {
  act: ['Act', 'Clear findings not yet in the record', 'alert'],
  med: ['Measure', 'Probability of a new finding and the most informative test', 'flask'],
  ok: ['Nothing pending', 'Well worked up: they take no space', 'check'],
}
const AREAS = [
  ['rinon', 'Kidney', 'drop'],
  ['tension', 'Blood pressure', 'gauge'],
  ['corazon', 'Rhythm and heart', 'pulse'],
  ['glucosa', 'Glucose', 'glu'],
  ['msg', 'With message', 'msg'],
]
const TEST_NAMES = {
  orina: 'Urine (albumin-to-creatinine ratio)',
  creatinina: 'Creatinine (eGFR)',
  glucosa: 'Glucose at the pharmacy',
  HbA1c: 'HbA1c',
  'lípidos': 'Total and HDL cholesterol',
  ecocardiograma: 'Echocardiogram',
}

// --- The patients on the list (fictional) ------------------------------------------------------
// Texts that carry numbers are functions of the model result (m): that way they match whatever the
// live API returns.
const PATIENTS = [
  {
    id: 'julian',
    group: 'act',
    name: 'Julián Herrero Sanz',
    short: 'Julián Herrero',
    first: 'Julián',
    ini: 'JH',
    age: 62,
    sex: 'M',
    cip: '4821',
    areas: ['rinon', 'tension'],
    channel: 'Kit via the app · watch',
    consta: ['Hypertension', 'Dyslipidemia', 'Former smoker'],
    meds: 'antihypertensive and statin',
    why: 'Repeated albuminuria at home, no kidney disease on record',
    chips: [
      ['kid', 'drop', 'Repeated albuminuria at home'],
      ['bp', 'gauge', (m) => `Home BP ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)}`],
      ['watch', 'watch', 'Watch: regular rhythm'],
    ],
    action: 'registrar',
    doneLabel: 'Recorded · I12.9 + N18.9',
    toast: 'Kidney disease recorded in Julián’s chart: I12.9 and N18.9.',
    last: 'High strip on 11/02',
    bpAlert: true,
    ctx: [
      'Four high strips: three in July and one on November 2, more than three months later. Meets the chronicity criterion.',
      'High cardiovascular risk, already on record. What is new is the kidney.',
    ],
    quote: true,
    samples: [
      ['tira', 80, '2026-07-14'],
      ['tira', 80, '2026-07-15'],
      ['tira', 80, '2026-07-16'],
      ['tira', 80, '2026-11-02'],
    ],
    albNote: 'What the filter believes about his true ratio after the 4 strips. Squares: strips.',
    trendNote: 'No creatinine since May 2024: the band widens because the data point is ageing.',
    tl: [
      { d: 'Nov 9', icon: 'watch', t: '30 s ECG with the watch', meta: 'sinus rhythm', ecg: 'regular', sub: (m) => `Plus 14 pulse checks from November 1 to 14, all regular: P(atrial fibrillation) ${pct(m.pAf)}.` },
      { d: 'Nov 2–8', icon: 'gauge', t: 'Blood pressure week', meta: 'loaned cuff', bp: true, sub: (m) => `${fixPct(m.bp.msg)} ${m.bp.n} readings over ${m.bp.days} days; the first day does not count.` },
      { d: 'Nov 2', icon: 'strip', t: 'Repeat strip', meta: 'read with the phone', hot: true, swatches: [[80, 100]], sub: 'More than three months after the July ones: meets the chronicity criterion.', said: 'Your health center will call you to book a visit.' },
      { d: 'Oct 12', icon: 'box', t: 'Repeat kit sent', sub: 'Sent by the system once the three months were up.' },
      { d: 'Jul 14–16', icon: 'strip', t: 'Three strips with the phone', swatches: [[80, 100], [80, 100], [80, 100]], pseq: [0.04, 0.62, 0.92, 0.98], sub: 'P(albuminuria) before and after each strip:', said: 'We found albumin in your urine. We will repeat the test in three months.' },
      { d: 'Jul 10', icon: 'box', t: 'Kit sent', sub: 'Hypertensive with no albumin-to-creatinine ratio in the record.' },
      { d: 'May 2024', icon: 'flask', t: 'Last labs: eGFR 90', meta: 'laboratory', sub: 'With creatinine but no albumin-to-creatinine ratio, like the three before.' },
    ],
    cvExtra: 'Albuminuria does not raise it: SCORE2 already put him at high risk.',
    req: [
      { on: true, t: 'Urine albumin-to-creatinine ratio', d: 'First morning urine. Quantifies the A2 the strips have seen.' },
      { on: true, t: 'Serum creatinine and eGFR (CKD-EPI)', d: (m) => `For the G stage: P(eGFR < 60) ${pct(m.pG60)}. Last eGFR: 90, in May 2024.` },
      { on: true, t: 'Potassium', d: 'Before starting or uptitrating an ACE inhibitor, an ARB or finerenone.' },
      { on: true, t: 'NT-proBNP', d: (m) => `Estimated P(≥ 125 pg/mL) ${pct(m.pBnp)}; if high, echocardiogram.` },
      { on: false, t: 'HbA1c', d: (m) => `P(undiagnosed diabetes) ${pct(m.pDm)}: first, a glucose check at the pharmacy.` },
    ],
    note: (m) =>
      `Home albuminuria screening (LatentHealth kit): 4 strips read with the phone, high in July (3) and on 11/02/2026, more than 3 months apart. Estimated ratio ${num(m.alb.median)} mg/g (${range(m.alb.low, m.alb.high)}), category A2 (P ${pct(m.alb.p[1])}). Last eGFR: 90 (05/2024); estimated today ${m.trend ? `${num(m.trend.level)} (${range(m.trend.low, m.trend.high)})` : 'not measured'}. Home BP ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)} mmHg (threshold 135/85). Regular rhythm on 14 watch checks.\n` +
      `Assessment: persistent A2 albuminuria in a hypertensive patient, no CKD on record.\n` +
      `Plan: lab UACR and creatinine, potassium and NT-proBNP. Review BP control and kidney protection per guideline.`,
    codesWhen: 'Suggested codes (ICD-10)',
    codes: [
      ['I12.9', 'Hypertensive chronic kidney disease, stage 1 to 4 or unspecified'],
      ['N18.9', 'Chronic kidney disease, unspecified (G stage pending eGFR)'],
    ],
    guide: [
      ['Consider', 'If his antihypertensive is neither an ACE inhibitor nor an ARB, consider switching: CKD with A2 albuminuria and hypertension, without diabetes.', 'KDIGO 2024 · rec. 3.6.2 (2C)'],
      ['Consider', 'Uncontrolled home blood pressure. Office target: systolic 120 to 129 mmHg if tolerated.', 'ESC 2024 · hypertension'],
      ['Later', 'SGLT2 inhibitors: the guideline recommends them with UACR of 200 mg/g or more, eGFR 20 to 45 or heart failure. Not met today; review with the labs and NT-proBNP.', 'KDIGO 2024 · rec. 3.7.2 and 3.7.3'],
    ],
    msg: 'Hi Julián. Your home strips found albumin in your urine in July and in November. I have ordered a blood and urine test to confirm it and check on your kidneys: pick the day in the app. Then we will go over it calmly at the clinic.',
  },
  {
    id: 'manuel',
    group: 'act',
    name: 'Manuel Castro Vidal',
    short: 'Manuel Castro',
    first: 'Manuel',
    ini: 'MC',
    age: 77,
    sex: 'M',
    cip: '1907',
    areas: ['corazon'],
    channel: 'App · watch with ECG',
    consta: ['Hypertension'],
    meds: 'antihypertensive',
    why: (m) => `Irregular pulse two days in a row: P(atrial fibrillation) ${pct(m.pAf)}`,
    chips: [
      ['ecg', 'pulse', 'Irregular pulse 2 days'],
      ['watch', 'watch', 'Watch ECG'],
    ],
    action: 'citar',
    doneLabel: 'Booked · tomorrow 9:40',
    toast: 'Visit for Manuel: tomorrow at 9:40, ECG with the nurse.',
    last: 'Irregular pulse on 11/13',
    ctx: [(m) => `Before measuring, given his age and sex, the probability was ${pct(m.pAfPrior)} (OFRECE study).`, 'No atrial fibrillation on record.'],
    samples: [['lab', 12, '2026-09-17']],
    albNote: 'A normal lab ratio in September. Circle: laboratory.',
    fgNote: 'Measured in the last labs.',
    tl: [
      { d: 'Nov 13', icon: 'watch', t: 'Irregular pulse', meta: 'watch', hot: true, ecg: 'af', sub: 'The watch alerted and recorded a 30 s single-lead ECG: irregular intervals and no clear P waves.' },
      { d: 'Nov 12', icon: 'pulse', t: 'Irregular pulse', meta: 'watch', sub: 'First irregular check.' },
      { d: 'Sep 17', icon: 'tube', t: 'Albumin-to-creatinine ratio: 12 mg/g', meta: 'laboratory', sub: 'Normal.' },
    ],
    reqTitle: 'Test order',
    req: [
      { on: true, t: '12-lead ECG', d: 'With the nurse, first thing tomorrow.' },
      { on: true, t: 'NT-proBNP', d: (m) => `Estimated P(≥ 125 pg/mL) ${pct(m.pBnp)}; if high, echocardiogram.` },
      { on: false, t: 'CBC, TSH, electrolytes and liver function', d: 'Initial workup, if fibrillation is confirmed.' },
    ],
    note: (m) =>
      `Two irregular pulse checks with the watch (11/12 and 11/13/2026) and a 30 s single-lead ECG with irregular intervals. P(atrial fibrillation) ${pct(m.pAf)} (before measuring, ${pct(m.pAfPrior)} for age and sex). No atrial fibrillation on record. Hypertensive on treatment.\n` +
      `Plan: 12-lead ECG and NT-proBNP. If confirmed, CHA2DS2-VA = 3.`,
    codesWhen: 'If the ECG confirms it (ICD-10)',
    codes: [['I48.91', 'Unspecified atrial fibrillation']],
    guide: [
      ['Consider', 'Diagnosis requires an ECG: 12-lead, or single-lead for 30 s or more. Review the watch tracing.', 'ESC 2024 · atrial fibrillation'],
      ['If confirmed', 'CHA₂DS₂-VA = 3 (age 75 or over: 2; hypertension: 1). With 2 or more, the guideline recommends anticoagulation.', 'ESC 2024 · atrial fibrillation'],
    ],
    msg: 'Hi Manuel. Your watch noticed an irregular pulse on two days. It is not urgent, but an electrocardiogram is a good idea: you have a visit tomorrow at 9:40 with the nurse. If you feel dizzy, have chest pain or are short of breath, call 112.',
  },
  {
    id: 'carmen',
    group: 'act',
    name: 'Lucía Prieto Gómez',
    short: 'Lucía Prieto',
    first: 'Lucía',
    ini: 'LP',
    age: 59,
    sex: 'F',
    cip: '3346',
    areas: ['tension', 'msg'],
    channel: 'App · loaned cuff',
    consta: ['No chronic conditions on record'],
    why: (m) => `Home blood pressure ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)}, no hypertension on record`,
    chips: [
      ['bp', 'gauge', (m) => `Home BP ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)} · 7 days`],
      ['msg', 'msg', () => (replied('carmen') ? null : 'New message')],
    ],
    action: 'registrar',
    doneLabel: 'Recorded · I10',
    toast: 'Hypertension recorded in Lucía’s chart: I10.',
    last: 'Blood pressure week 11/05–11/11',
    ctx: ['Office blood pressure: 138/86. At home, above 135/85 every day.'],
    samples: [['lab', 7, '2026-10-07']],
    albNote: 'Normal lab ratio in October.',
    fgNote: 'Measured in the last labs.',
    tl: [
      { d: 'Nov 5–11', icon: 'gauge', t: 'Blood pressure week', meta: 'loaned cuff', hot: true, bp: true, sub: (m) => `${fixPct(m.bp.msg)} ${m.bp.n} readings over ${m.bp.days} days; the first day does not count.` },
      { d: 'Oct 7', icon: 'tube', t: 'Albumin-to-creatinine ratio: 7 mg/g', meta: 'laboratory', sub: 'Normal.' },
    ],
    reqTitle: 'Test order',
    req: [
      { on: true, t: 'Sodium and potassium', d: 'Basic hypertension workup: UACR, eGFR and lipids are already on record.' },
      { on: true, t: '12-lead ECG', d: 'Basic hypertension workup.' },
      { on: false, t: 'HbA1c', d: (m) => `P(undiagnosed diabetes) ${pct(m.pDm)}: a glucose check at the pharmacy is enough.` },
    ],
    note: (m) =>
      `7-day home monitoring with a validated cuff (11/05–11/11/2026): mean ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)} mmHg, ${m.bp.n} readings over ${m.bp.days} days (threshold 135/85). Office BP 138/86. UACR 7 mg/g (10/2026), eGFR 88. SCORE2 ${pct1(m.cv.score)}: low to moderate risk.\n` +
      `Assessment: hypertension confirmed by home monitoring.\n` +
      `Plan: basic workup (electrolytes, ECG) and a visit to decide on treatment.`,
    codesWhen: 'Suggested code (ICD-10)',
    codes: [['I10', 'Essential (primary) hypertension']],
    guide: [
      ['Consider', 'A home mean of 135/85 or more confirms hypertension.', 'ESC 2024 · hypertension'],
      ['Consider', 'With hypertension confirmed, the guideline recommends medication in addition to lifestyle changes.', 'ESC 2024 · hypertension'],
    ],
    msg: 'Hi Lucía. Your blood pressure week came out high: 149/91 on average. We will call you to book a visit and talk about how to bring it down. You can return the cuff at the health center or at your pharmacy.',
  },
  {
    id: 'rosa',
    group: 'act',
    name: 'Rosa Méndez Ibáñez',
    short: 'Rosa Méndez',
    first: 'Rosa',
    ini: 'RM',
    age: 68,
    sex: 'F',
    cip: '5560',
    areas: ['rinon', 'corazon'],
    channel: 'App',
    consta: ['Type 2 diabetes', 'Hypertension'],
    meds: 'oral antidiabetic and antihypertensive',
    why: 'eGFR falling year after year: from 88 to 49 in four years',
    chips: [
      ['kid', 'drop', (m) => `eGFR ${num(m.trend.slope, 1)} per year`],
      ['kid', 'tube', 'Urine never measured'],
      ['ecg', 'lungs', 'Short of breath on stairs'],
    ],
    action: 'citar',
    doneLabel: 'Booked · Thursday 10:20',
    toast: 'Visit for Rosa: Thursday 11/19 at 10:20. Her urine kit arrives tomorrow.',
    last: 'Home questionnaire on 11/14',
    ctx: [
      (m) => `Slope of ${num(m.trend.slope, 1)} mL/min/1.73 m² per year (between ${num(m.trend.slopeLow, 1)} and ${num(m.trend.slopeHigh, 1)}): rapid decline.`,
      (m) => `Urine has never been measured: P(albuminuria) ${pct(m.alb.p2)}. The KDIGO stage is incomplete.`,
      'In the home questionnaire she reports shortness of breath climbing stairs.',
    ],
    samples: [],
    albNote: 'No samples at all: what is expected for someone with her history.',
    trendNote: 'Five sets of labs, one a year. October’s: 49.',
    tl: [
      { d: 'Nov 14', icon: 'doc', t: 'Home questionnaire', meta: 'app', hot: true, sub: 'Short of breath climbing stairs; fair health; some difficulty walking.' },
      { d: 'Oct 27', icon: 'flask', t: 'Annual labs: eGFR 49', meta: 'laboratory', sub: 'No albumin-to-creatinine ratio, as in the four before.' },
    ],
    req: [
      { on: true, t: 'Urine albumin-to-creatinine ratio', d: (m) => `P(albuminuria) ${pct(m.alb.p2)}. Completes the KDIGO stage.` },
      { on: true, t: 'Serum creatinine and eGFR', d: 'Confirm October’s 49.' },
      { on: true, t: 'Potassium', d: 'Before starting or uptitrating an ACE inhibitor, an ARB or finerenone.' },
      { on: true, t: 'NT-proBNP', d: (m) => `Estimated P(≥ 125 pg/mL) ${pct(m.pBnp)}, with dyspnea on stairs.` },
    ],
    note: (m) =>
      `eGFR from 88 to 49 in four years (5 lab sets, 2022–2026). Trend ${num(m.trend.slope, 1)} mL/min/1.73 m² per year (${num(m.trend.slopeLow, 1)} to ${num(m.trend.slopeHigh, 1)}): rapid decline. Estimated eGFR today ${num(m.trend.level)} (${range(m.trend.low, m.trend.high)}). Albuminuria never measured (P ≥ 30 mg/g: ${pct(m.alb.p2)}). Type 2 diabetes and hypertension. Dyspnea climbing stairs (home questionnaire); P(NT-proBNP ≥ 125) ${pct(m.pBnp)}.\n` +
      `Plan: UACR, kidney function, potassium and NT-proBNP; consider nephrology referral.`,
    codesWhen: 'To confirm with the next labs (ICD-10)',
    codes: [
      ['E11.22', 'Type 2 diabetes mellitus with diabetic chronic kidney disease'],
      ['I12.9', 'Hypertensive chronic kidney disease, stage 1 to 4'],
      ['N18.31', 'Chronic kidney disease, stage 3a'],
    ],
    guide: [
      ['Consider', 'Losing more than 5 mL/min/1.73 m² per year: rapid progression. Consider nephrology referral.', 'KDIGO 2024 · referral'],
      ['Consider', 'Type 2 diabetes with CKD and eGFR 20 or more: SGLT2 inhibitor.', 'KDIGO 2024 · rec. 3.7.1 (1A)'],
    ],
    msg: 'Hi Rosa. Your tests show your kidneys are filtering a little less each year. I would like to see you this week: you have a visit on Thursday at 10:20. Before that, do the urine test from the kit arriving tomorrow.',
  },
  {
    id: 'ramon',
    group: 'act',
    name: 'Ramón Iglesias Soto',
    short: 'Ramón Iglesias',
    first: 'Ramón',
    ini: 'RI',
    age: 56,
    sex: 'M',
    cip: '7718',
    areas: ['glucosa', 'tension'],
    channel: 'App · pharmacy',
    consta: ['Hypertension', 'Prediabetes', 'Smoker'],
    meds: 'no treatment',
    why: 'Fasting glucose of 126 or more on two days at the pharmacy, no diabetes on record',
    chips: [['glu', 'glu', 'Pharmacy glucose 134 · 141']],
    action: 'analitica',
    toast: 'Order sent: HbA1c, fasting glucose, UACR and creatinine. Ramón picks the day in the app.',
    last: 'Pharmacy glucose on 11/12',
    ctx: [(m) => `With both glucose readings, P(undiagnosed diabetes) ${pct(m.pDm)}.`, 'Prediabetes on record, BMI 34, smokes and has a family history of diabetes.'],
    samples: [],
    albNote: 'No urine samples: what is expected for someone with his history.',
    fgNote: 'Estimated from the history: no creatinine.',
    tl: [
      { d: 'Nov 12', icon: 'glu', t: 'Glucose at the pharmacy: 141 mg/dL', meta: 'fasting', hot: true, sub: 'Second day above 126.' },
      { d: 'Nov 10', icon: 'glu', t: 'Glucose at the pharmacy: 134 mg/dL', meta: 'fasting' },
      { d: 'Nov 6', icon: 'cross', t: 'Glucose voucher for his pharmacy', sub: 'Screening step 1: P(hidden diabetes) of 2% or more.' },
    ],
    req: [
      { on: true, t: 'HbA1c', d: (m) => `P(undiagnosed diabetes) ${pct(m.pDm)}: confirm with labs.` },
      { on: true, t: 'Fasting venous glucose', d: 'Same blood draw.' },
      { on: true, t: 'Urine albumin-to-creatinine ratio', d: 'Never measured.' },
      { on: true, t: 'Serum creatinine and eGFR', d: 'Never measured.' },
    ],
    note: (m) =>
      `Fasting capillary glucose at the pharmacy: 134 (11/10) and 141 mg/dL (11/12/2026). Prediabetes on record; BMI 34, smoker, family history of diabetes. P(undiagnosed diabetes) ${pct(m.pDm)}.\n` +
      `Plan: confirm with HbA1c and fasting venous glucose; UACR and creatinine in the same draw.`,
    codesWhen: 'If HbA1c is 6.5% or more (ICD-10)',
    codes: [['E11.9', 'Type 2 diabetes mellitus without complications']],
    guide: [
      ['Consider', 'Diagnosis with HbA1c of 6.5% or more, or fasting venous glucose of 126 mg/dL or more, confirmed.', 'ADA 2025 · Standards of Care'],
      ['Consider', 'Untreated office blood pressure of 142/90: a week of home monitoring before deciding.', 'ESC 2024 · hypertension'],
    ],
    msg: 'Hi Ramón. Both glucose readings at the pharmacy came out somewhat high. I have ordered a blood test to confirm it: pick the day in the app and come fasting.',
  },
  {
    id: 'elena',
    group: 'med',
    name: 'Elena Navarro Pascual',
    short: 'Elena Navarro',
    first: 'Elena',
    ini: 'EN',
    age: 74,
    sex: 'F',
    cip: '2284',
    areas: ['rinon'],
    channel: 'Kit by mail',
    consta: ['Hypertension'],
    meds: 'antihypertensive',
    why: 'eGFR of 51 on the home blood drop: needs confirming',
    chips: [
      ['kid', 'drop', 'Capillary eGFR 51'],
      ['kid', 'tube', 'Urine not measured'],
    ],
    test: 'Creatinine',
    testIcon: 'flask',
    how: 'labs (blood drop already done)',
    action: 'analitica',
    toast: 'Order sent: creatinine, UACR, potassium and NT-proBNP. Elena picks the day in the app.',
    last: 'Blood drop on 11/11',
    samples: [],
    albNote: 'No urine samples: what is expected for someone with her history.',
    fgNote: 'The blood drop has more error than standard labs: the model combines it with the history.',
    tl: [
      { d: 'Nov 11', icon: 'drop', t: 'Blood drop by mail: eGFR 51', meta: 'laboratory', hot: true, sub: (m) => `With the history, the model puts it at ${num(m.blood.egfr[0])} (${range(m.blood.egfr[1], m.blood.egfr[2])}).` },
      { d: 'Nov 4', icon: 'box', t: 'Kit sent: blood drop', sub: 'The list said creatinine was the most informative test.' },
    ],
    req: [
      { on: true, t: 'Serum creatinine and eGFR', d: (m) => `P(eGFR < 60) ${pct(m.pG60)}. Confirms the blood drop.` },
      { on: true, t: 'Urine albumin-to-creatinine ratio', d: (m) => `P(albuminuria) ${pct(m.alb.p2)}. Completes the stage.` },
      { on: true, t: 'Potassium', d: 'If confirmed, before starting or uptitrating an ACE inhibitor or an ARB.' },
      { on: true, t: 'NT-proBNP', d: (m) => `Estimated P(≥ 125 pg/mL) ${pct(m.pBnp)}.` },
    ],
    note: (m) =>
      `Home blood drop (11/11/2026): eGFR 51. With the clinical history, estimated eGFR ${num(m.blood.egfr[0])} (${range(m.blood.egfr[1], m.blood.egfr[2])}); P(eGFR < 60) ${pct(m.pG60)}. Albuminuria not measured. Hypertensive on treatment.\n` +
      `Plan: confirm in the lab with UACR; NT-proBNP in the same draw.`,
    codesWhen: 'If an eGFR < 60 is confirmed after 3 months (ICD-10)',
    codes: [
      ['I12.9', 'Hypertensive chronic kidney disease, stage 1 to 4'],
      ['N18.31', 'Chronic kidney disease, stage 3a'],
    ],
    guide: [['Consider', 'A single eGFR below 60 is not enough: it must be confirmed after three months.', 'KDIGO 2024 · CKD definition']],
    msg: 'Hi Elena. The blood drop you mailed needs to be confirmed with a regular blood test. Pick the day in the app; no need to fast.',
  },
  {
    id: 'marta',
    group: 'med',
    name: 'Marta Romero Gil',
    short: 'Marta Romero',
    first: 'Marta',
    ini: 'MR',
    age: 47,
    sex: 'F',
    cip: '6093',
    areas: ['rinon'],
    channel: 'Kit via the app',
    consta: ['Type 2 diabetes'],
    meds: 'oral antidiabetic',
    why: 'Diabetic: two doubtful strips; the app has already asked for the tube',
    chips: [
      ['kid', 'strip', '2 doubtful strips'],
      ['auto', 'auto', 'In progress at home'],
    ],
    test: 'Urine',
    testIcon: 'tube',
    how: 'kit tube, already requested',
    action: 'recordar',
    toast: 'Reminder in Marta’s app: tomorrow, the tube with first morning urine.',
    last: 'Doubtful strip on 11/14',
    samples: [
      ['tira', 30, '2026-11-13'],
      ['tira', 60, '2026-11-14'],
    ],
    albNote: 'Two doubtful strips: the filter can neither rule out nor confirm. Squares: strips.',
    fgNote: 'Estimated from the history.',
    tl: [
      { d: 'Nov 15', icon: 'tube', t: 'The app asked for the tube', hot: true, sub: (m) => `P(albuminuria) ${pct(m.alb.p2)}; another strip would settle it only ${pct(m.alb.resolve)} of the time.`, said: 'To clear up the doubt, it needs to be measured in the lab.' },
      { d: 'Nov 13–14', icon: 'strip', t: 'Two strips with the phone', swatches: [[30, 100], [30, 50]], pseq: [0.065, 0.12, 0.34], sub: 'P(albuminuria) before and after each strip:' },
      { d: 'Nov 10', icon: 'clock', t: 'Test postponed', sub: 'She answered she had her period: the app moved it a few days.' },
      { d: 'Nov 6', icon: 'box', t: 'Kit sent', sub: 'Annual diabetes screening.' },
    ],
    req: [],
    reqEmpty: 'Nothing to order: the tube goes to the lab in the kit envelope.',
    note: (m) =>
      `Annual home albuminuria screening: two doubtful strips (11/13 and 11/14/2026). P(albuminuria) ${pct(m.alb.p2)}; estimated ratio ${num(m.alb.median)} mg/g (${range(m.alb.low, m.alb.high)}). The app has requested a sample for the lab (11/15).`,
    guide: [['Reminder', 'Type 2 diabetes: albumin-to-creatinine ratio and eGFR at least once a year.', 'KDIGO 2024 · ADA 2025']],
    msg: 'Hi Marta. Reminder: tomorrow, fill the tube with your first urine of the day and drop it in the mailbox in the kit envelope.',
  },
  {
    id: 'antonio',
    group: 'med',
    name: 'Antonio Delgado Ferrer',
    short: 'Antonio Delgado',
    first: 'Antonio',
    ini: 'AD',
    age: 81,
    sex: 'M',
    cip: '0475',
    areas: ['rinon', 'corazon'],
    channel: 'No smartphone: by phone call',
    consta: ['Hypertension'],
    meds: 'antihypertensive',
    why: 'No labs since 2019 and no smartphone',
    chips: [
      ['kid', 'flask', 'No creatinine since 2019'],
      ['auto', 'call', 'Notified by phone'],
    ],
    test: 'Creatinine',
    testIcon: 'flask',
    how: 'labs at the health center',
    action: 'analitica',
    toast: 'Order sent: creatinine, NT-proBNP, UACR and glucose. The nurse will call Antonio to book.',
    last: 'Office blood pressure, 2025',
    samples: [],
    albNote: 'No urine samples: what is expected for someone with his history.',
    fgNote: 'Estimated from the history: the last creatinine is from 2019.',
    tl: [{ d: '2019', icon: 'flask', t: 'Last labs', sub: 'Since then, only office blood pressure (150/72). Does not use a smartphone: the urine kit would go by mail.' }],
    req: [
      { on: true, t: 'Serum creatinine and eGFR', d: (m) => `P(eGFR < 60) ${pct(m.pG60)}.` },
      { on: true, t: 'NT-proBNP', d: (m) => `Estimated P(≥ 125 pg/mL) ${pct(m.pBnp)}; if high, echocardiogram.` },
      { on: true, t: 'Urine albumin-to-creatinine ratio', d: (m) => `P(albuminuria) ${pct(m.alb.p2)}.` },
      { on: true, t: 'Glucose', d: (m) => `P(hidden diabetes) ${pct(m.pDm)}. Same blood draw.` },
      { on: false, t: 'Total and HDL cholesterol', d: 'SCORE2-OP was computed with typical lipids.' },
    ],
    note: (m) =>
      `No labs since 2019. Hypertensive on treatment; office BP 150/72. Estimated from the history: eGFR ${num(m.blood.egfr[0])} (${range(m.blood.egfr[1], m.blood.egfr[2])}), P(eGFR < 60) ${pct(m.pG60)}; P(NT-proBNP ≥ 125) ${pct(m.pBnp)}. Does not use a smartphone: contact by phone.\n` +
      `Plan: labs with creatinine, NT-proBNP, UACR and glucose.`,
    guide: [['Consider', 'NT-proBNP of 125 pg/mL or more outside an acute decompensation: echocardiogram.', 'ESC 2021 · heart failure']],
    msg: null,
    msgVia: 'Notify the nurse',
    msgToast: 'Nurse notified: call Antonio for the blood draw.',
  },
  {
    id: 'dolores',
    group: 'med',
    name: 'Dolores Sánchez Ortiz',
    short: 'Dolores Sánchez',
    first: 'Dolores',
    ini: 'DS',
    age: 69,
    sex: 'F',
    cip: '5132',
    areas: ['rinon'],
    channel: 'App',
    consta: ['Type 2 diabetes', 'Hypertension'],
    meds: 'oral antidiabetic and antihypertensive',
    why: 'Diabetic and hypertensive: urine has never been measured',
    chips: [['kid', 'tube', 'Ratio never measured']],
    test: 'Urine',
    testIcon: 'box',
    how: 'home kit (app)',
    action: 'kit',
    toast: 'Urine kit on its way: 3 strips and 2 tubes. The app will remind Dolores on test day.',
    last: 'Annual labs on 10/20',
    samples: [],
    albNote: 'No samples: what is expected for a diabetic, hypertensive woman her age.',
    fgNote: 'Measured in the annual labs.',
    tl: [{ d: 'Oct 20', icon: 'flask', t: 'Annual labs: eGFR 66, HbA1c 7.6%', meta: 'laboratory', sub: 'No albumin-to-creatinine ratio, as in the three before.' }],
    req: [],
    reqEmpty: 'The kit is enough: if the strips are unsure, the app asks for the tube.',
    note: (m) =>
      `Type 2 diabetes and hypertension. eGFR 66, HbA1c 7.6% (10/2026). Albumin-to-creatinine ratio never measured: P(albuminuria) ${pct(m.alb.p2)}.\n` + `Plan: home urine kit (strips and, if unsure, a tube for the lab).`,
    guide: [['Consider', 'Type 2 diabetes: albumin-to-creatinine ratio and eGFR at least once a year.', 'KDIGO 2024 · ADA 2025']],
    msg: 'Hi Dolores. A kit for a urine test is on its way to your home. The app will tell you which day to do it: it takes three minutes.',
  },
  {
    id: 'pilar',
    group: 'med',
    name: 'Pilar Garrido Lozano',
    short: 'Pilar Garrido',
    first: 'Pilar',
    ini: 'PG',
    age: 58,
    sex: 'F',
    cip: '8152',
    areas: ['rinon', 'msg'],
    channel: 'Kit via the app',
    consta: ['No chronic conditions on record'],
    why: 'Doubtful strip on her first screening; the tube is on its way to the lab',
    chips: [
      ['kid', 'strip', '2 doubtful strips'],
      ['kid', 'tube', 'Tube sent'],
      ['msg', 'msg', () => (replied('pilar') ? null : 'New message')],
    ],
    test: 'Urine',
    testIcon: 'tube',
    how: 'tube at the lab',
    action: 'responder',
    toast: 'Reply sent to Pilar.',
    last: 'Tube sent on 11/14',
    samples: [
      ['tira', 30, '2026-11-12'],
      ['tira', 30, '2026-11-13'],
    ],
    albNote: 'Two strips with albumin 30 mg/L: doubtful. The tube will settle it.',
    fgNote: 'Measured in her last labs.',
    tl: [
      { d: 'Nov 15', icon: 'msg', t: 'Message to her doctor', meta: 'with the tests attached', hot: true, sub: '“Do I need to book a visit?”' },
      { d: 'Nov 14', icon: 'tube', t: 'Tube sent', sub: 'Reaches the lab on Tuesday the 17th.' },
      { d: 'Nov 12–13', icon: 'strip', t: 'Two strips with the phone', swatches: [[30, 100], [30, 100]], pseq: [0.02, 0.07, 0.12], sub: 'P(albuminuria) before and after each strip:', said: 'To clear up the doubt, it needs to be measured in the lab.' },
      { d: 'Nov 10', icon: 'box', t: 'Kit sent', sub: 'First screening.' },
    ],
    req: [],
    reqEmpty: 'The tube is already on its way to the lab: nothing to order.',
    note: (m) =>
      `First home albuminuria screening: two strips with albumin 30 mg/L (11/12 and 11/13/2026), doubtful. P(albuminuria) ${pct(m.alb.p2)}; estimated ratio ${num(m.alb.median)} mg/g (${range(m.alb.low, m.alb.high)}). Tube sent to the lab on 11/14.`,
    guide: [['What to expect', 'If the tube is normal, screening ends until next year; if it is high, the app asks to repeat in three months.', 'Kit protocol']],
    msg: null,
    msgVia: 'Reply',
  },
  {
    id: 'andres',
    group: 'med',
    name: 'Andrés Molina Rey',
    short: 'Andrés Molina',
    first: 'Andrés',
    ini: 'AM',
    age: 70,
    sex: 'M',
    cip: '3901',
    areas: ['corazon'],
    channel: 'App · watch with ECG',
    consta: ['Hypertension', 'Dyslipidemia'],
    meds: 'antihypertensive and statin',
    why: 'His watch’s 30 s ECG points to a heart that pumps weakly',
    chips: [
      ['watch', 'watch', 'Watch ECG (30 s)'],
      ['ecg', 'heart', (m) => `P(low EF) ${pct(m.pEf)}`],
    ],
    test: 'NT-proBNP',
    testIcon: 'flask',
    how: 'labs; if high, echocardiogram',
    action: 'analitica',
    toast: 'Order sent: NT-proBNP. If high, the echocardiogram will go as priority.',
    last: 'Watch ECG on 11/09',
    samples: [['lab', 15, '2026-10-01']],
    albNote: 'Normal lab ratio in October.',
    fgNote: 'Measured in the last labs.',
    tl: [
      { d: 'Nov 9', icon: 'watch', t: '30 s ECG with the watch', meta: 'single lead', hot: true, ecg: 'lowef', sub: (m) => `Pattern associated with low ejection fraction: P(EF ≤ 40%) ${pct(m.pEf)}; before recording, 0.9%.` },
      { d: 'Oct 1', icon: 'tube', t: 'Albumin-to-creatinine ratio: 15 mg/g', meta: 'laboratory', sub: 'Normal.' },
    ],
    req: [
      { on: true, t: 'NT-proBNP', d: 'If 125 pg/mL or more, priority echocardiogram.' },
      { on: false, t: 'Echocardiogram', d: 'Directly, if there is no waiting list.' },
    ],
    note: (m) =>
      `30 s single-lead ECG with the watch (11/09/2026): pattern associated with low ejection fraction. P(EF ≤ 40%) ${pct(m.pEf)} (before recording, 0.9%). No heart failure on record. The model was validated with the device on the chest; on a watch it is unvalidated.\n` +
      `Plan: NT-proBNP; if 125 pg/mL or more, priority echocardiogram.`,
    guide: [['Consider', 'NT-proBNP of 125 pg/mL or more outside an acute decompensation: echocardiogram.', 'ESC 2021 · heart failure']],
    msg: 'Hi Andrés. The electrocardiogram from your watch should be completed with a blood test. Pick the day in the app. If you get short of breath or your ankles swell, book a visit sooner.',
  },
  {
    id: 'francisco',
    group: 'med',
    name: 'Francisco Vega Martín',
    short: 'Francisco Vega',
    first: 'Francisco',
    ini: 'FV',
    age: 66,
    sex: 'M',
    cip: '6627',
    areas: ['glucosa'],
    channel: 'App · pharmacy',
    consta: ['Hypertension', 'Dyslipidemia', 'Former smoker'],
    meds: 'antihypertensive and statin',
    why: 'Glucose has never been measured',
    chips: [['glu', 'glu', 'Glucose never measured']],
    test: 'Glucose',
    testIcon: 'cross',
    how: 'one check at the pharmacy',
    action: 'farmacia',
    toast: 'Voucher sent to his pharmacy: fasting capillary glucose. The app will notify Francisco.',
    last: 'Normal ratio on 09/22',
    samples: [['lab', 9, '2026-09-22']],
    albNote: 'Normal lab ratio in September.',
    fgNote: 'Measured in the last labs.',
    tl: [{ d: 'Sep 22', icon: 'tube', t: 'Albumin-to-creatinine ratio: 9 mg/g', meta: 'laboratory', sub: 'Normal. Glucose and HbA1c have never been measured.' }],
    req: [
      { on: true, t: 'Fasting capillary glucose, at the pharmacy', d: (m) => `Step 1: P(hidden diabetes) ${pct(m.pDm)}, 2% or more.` },
      { on: false, t: 'HbA1c', d: 'Step 2: only if, with the glucose, the probability stays at 2% or more.' },
    ],
    reqTitle: 'Glucose in two steps',
    reqBtn: 'Send the voucher',
    note: (m) => `Hypertensive and dyslipidemic, BMI 31, former smoker. No glucose or HbA1c in the record: P(undiagnosed diabetes) ${pct(m.pDm)}.\nPlan: fasting capillary glucose at the pharmacy; HbA1c only if the probability stays at 2% or more.`,
    guide: [['Consider', 'Diabetes screening in overweight adults with another risk factor, such as hypertension.', 'ADA 2025 · Standards of Care']],
    msg: 'Hi Francisco. Whenever suits you, stop by your pharmacy while fasting: they will check your glucose with a finger prick. They already have your voucher.',
  },
]
const P = Object.fromEntries(PATIENTS.map((p) => [p.id, p]))

// More patients from the practice list, with nothing pending (for the Patients view).
const QUIET = [
  ['Lucía Ferrer Campos', 'LF', 45, 'F', '2219', 'Normal labs and urine in 2026', 'low to moderate'],
  ['Luis Ortega Blanco', 'LO', 66, 'M', '7390', 'Diabetic on SGLT2 inhibitor: stable eGFR', 'high'],
  ['Vicente Lara Pons', 'VL', 73, 'M', '1182', 'CKD G3a A2 on record; follow-up up to date', 'very high'],
]

// --- Messages ----------------------------------------------------------------------------------
const MESSAGES = [
  {
    id: 'pilar',
    when: 'Yesterday, 7:42 PM',
    unread: true,
    text: 'Hi Carmen. The app asked me for the tube and I have already sent it. Do I need to book a visit?',
    sugg: [
      'No need for a visit for now, Pilar. When the lab result comes in, the app will tell you what to do and I will see it too. If needed, we will call you.',
      'Thanks, Pilar. Book a visit for two weeks from now and we will go over the result together.',
      'Got it. I will write to you as soon as the lab result arrives.',
    ],
  },
  {
    id: 'carmen',
    when: 'Yesterday, 12:05 PM',
    unread: true,
    text: 'I have finished the blood pressure week. Do I return the cuff at the health center or at the pharmacy?',
    sugg: [
      'You can return it at the health center or at your pharmacy, whichever suits you best. I have already looked at your week: we will call you to book a visit and talk about your blood pressure.',
      'Thanks, Lucía. Return it at the pharmacy. We will call you this week to see you.',
    ],
  },
  {
    id: 'marta',
    when: 'Sunday, 9:10 PM',
    unread: false,
    text: 'Do I need to be fasting to fill the tube?',
    bot: 'No need to fast: what matters is that it is the first urine of the day. Fill the tube up to the mark and drop it in the mailbox in the kit envelope.',
  },
]

// --- Kits (those of today's patients; the weekly figures are example data) ---------------------
const KIT_STEPS = ['Sent', 'Delivered', 'In use', 'Done']
const KITS = [
  ['pilar', '3 strips and 2 tubes', 'App', 3, 'Tube on its way', '11/14 · reaches the lab on 11/17'],
  ['marta', '3 strips and 2 tubes', 'App', 2, 'Tube requested', '11/15 · the app asked for the tube'],
  ['carmen', 'Cuff, 7 days', 'App', 3, 'Cuff to be returned', '11/11 · week complete'],
  ['julian', 'Repeat strips and cuff', 'App', 4, 'Finished', '11/10 · cuff returned'],
  ['ramon', 'Glucose at the pharmacy', 'Pharmacy', 4, 'Done', '11/12 · 141 mg/dL fasting'],
  ['elena', 'Blood drop by mail', 'Mail', 4, 'Result received', '11/11 · capillary eGFR 51'],
  ['andres', '30 s ECG with his watch', 'Watch', 4, 'Done', '11/09 · recording reviewed'],
  ['dolores', '3 strips and 2 tubes', 'App', 0, 'Proposed today', 'Needs your approval'],
  ['francisco', 'Glucose voucher', 'Pharmacy', 0, 'Proposed today', 'Needs your approval'],
]

// --- State -------------------------------------------------------------------------------------
const S = {
  view: 'hoy',
  sel: 'julian',
  group: 'todo',
  area: null,
  q: '',
  done: {}, // id -> label of the completed action
  sent: {}, // 'id:req' | 'id:note' | 'id:msg' -> true
  req: {}, // id -> [checked]
  notes: {}, // id -> edited text
  live: {}, // id -> { m, ms }
  liveState: {}, // id -> 'wait' | 'ok' | 'off'
  conn: 'wait',
  msgSel: 'pilar',
  msgs: {}, // id -> { read, replies: [] }
  draft: {}, // id -> reply text
  sugg: {}, // id -> index of the chosen suggestion
}
let root = null
let toastTimer = 0
let toastUndo = null

const M = (id) => {
  const base = MODEL[id] ?? {}
  const live = S.live[id]?.m
  return live ? { ...base, ...live } : base
}
const isMobile = () => matchMedia('(max-width: 900px)').matches
const narrow = () => matchMedia('(max-width: 560px)').matches
const $ = (sel) => root.querySelector(sel)
const $$ = (sel) => [...root.querySelectorAll(sel)]
const replied = (id) => Boolean(S.msgs[id]?.replies?.length)
const unread = () => MESSAGES.filter((x) => x.unread && !S.msgs[x.id]?.read).length
const pending = (group) => PATIENTS.filter((p) => p.group === group && !S.done[p.id]).length

// --- Charts ------------------------------------------------------------------------------------
const KR = [
  [0, 1, 2],
  [0, 1, 2],
  [1, 2, 3],
  [2, 3, 3],
  [3, 3, 3],
  [3, 3, 3],
]
const KR_LABEL = ['low', 'moderate', 'high', 'very high']
const KR_COLOR = ['#e9f1ee', 'var(--c10)', 'var(--c50)', '#ec9c87']
const G_ROWS = [
  ['G1', '≥ 90'],
  ['G2', '60–89'],
  ['G3a', '45–59'],
  ['G3b', '30–44'],
  ['G4', '15–29'],
  ['G5', '< 15'],
]
const A_COLS = [
  ['A1', '< 30'],
  ['A2', '30–300'],
  ['A3', '> 300'],
]
const cellPct = (p) => (p < 0.005 ? '·' : p < 0.01 ? '<1%' : `${Math.round(p * 100)}%`)

function kdigoHTML(m) {
  const joint = m.joint ?? []
  let best = -1
  let top = [0, 0]
  joint.forEach((row, g) => row.forEach((p, a) => p > best && ((best = p), (top = [g, a]))))
  let k = 0
  const body = G_ROWS.map(([g, r], gi) => {
    const cells = (joint[gi] ?? [0, 0, 0])
      .map((p, ai) => {
        const isTop = gi === top[0] && ai === top[1]
        return `<td class="kr${KR[gi][ai]}${p < 0.005 ? ' is-zero' : ''}${isTop ? ' is-top' : ''}" style="--p:${Math.max(0.02, p).toFixed(3)};--k:${k++}" title="${g} · ${A_COLS[ai][0]}: ${pct(p)} (${KR_LABEL[KR[gi][ai]]} risk)">${cellPct(p)}${p >= 0.005 ? '<i></i>' : ''}</td>`
      })
      .join('')
    return `<tr><th scope="row">${g}<small>${r}</small></th>${cells}</tr>`
  }).join('')
  return `<div class="dr-card">
    <div class="dr-ch"><p>KDIGO stage</p><small>probability per cell</small></div>
    <table class="dr-kdigo"><caption class="dr-sr">Probability of each combination of glomerular filtration (G) and albuminuria (A). Color: KDIGO risk.</caption>
      <thead><tr><th scope="col"><span class="dr-sr">eGFR</span></th>${A_COLS.map(([a, r]) => `<th scope="col">${a}<small>${r}</small></th>`).join('')}</tr></thead>
      <tbody>${body}</tbody></table>
    <p class="dr-ktop">Most likely: <b>${G_ROWS[top[0]][0]} · ${A_COLS[top[1]][0]}</b> (${pct(best)})</p>
    <p class="dr-klegend" aria-hidden="true">Risk:${KR_LABEL.map((l, i) => `<span><i style="background:${KR_COLOR[i]}"></i>${l}</span>`).join('')}</p>
  </div>`
}

function beliefSVG(b, samples, median) {
  const W = 300
  const H = 116
  const L = 6
  const R = 6
  const T = 18
  const B = 24
  const lo = Math.log10(2)
  const hi = Math.log10(1500)
  const x = (u) => L + ((Math.log10(Math.min(Math.max(u, 2), 1500)) - lo) / (hi - lo)) * (W - L - R)
  const pts = (b.pts ?? []).filter(([u]) => u >= 2 && u <= 1500)
  if (!pts.length) return ''
  const peak = Math.max(...pts.map((p) => p[1])) || 1
  const base = H - B
  const y = (m) => base - (m / peak) * (base - T - 4)
  const line = pts.map(([u, m]) => `${x(u).toFixed(1)},${y(m).toFixed(1)}`).join('L')
  const area = `M${x(pts[0][0]).toFixed(1)},${base}L${line}L${x(pts[pts.length - 1][0]).toFixed(1)},${base}Z`
  const ticks = [3, 10, 30, 100, 300, 1000]
    .map((v) => `<line class="dr-s-ax" x1="${x(v)}" x2="${x(v)}" y1="${base}" y2="${base + 4}"/><text x="${x(v)}" y="${base + 15}" text-anchor="middle">${num(v)}</text>`)
    .join('')
  const refs = [30, 300].map((v) => `<line class="dr-s-ref" x1="${x(v)}" x2="${x(v)}" y1="${T - 4}" y2="${base}"/>`).join('')
  const zones = [
    ['A1', 7.5],
    ['A2', 95],
    ['A3', 700],
  ]
    .map(([n, v]) => `<text class="dr-s-lbl" x="${x(v)}" y="${T - 7}" text-anchor="middle">${n}</text>`)
    .join('')
  const marks = samples
    .map(([kind, u, date], i) => {
      const cx = x(u).toFixed(1)
      const cy = base - 1 - (i % 2) * 7
      const title = `<title>${kind === 'tira' ? 'Strip' : 'Lab'} on ${date.slice(5, 7)}/${date.slice(8, 10)}: ${num(u)} mg/g</title>`
      return kind === 'tira'
        ? `<rect x="${(cx - 4.5).toFixed(1)}" y="${(cy - 4.5).toFixed(1)}" width="9" height="9" fill="#fff" stroke="#0d2226" stroke-width="1.6">${title}</rect>`
        : `<circle cx="${cx}" cy="${cy}" r="4.6" fill="#0d2226" stroke="#fff" stroke-width="1.4">${title}</circle>`
    })
    .join('')
  const mx = x(median).toFixed(1)
  return `<svg class="dr-svg dr-fade" viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribution of the true albumin-to-creatinine ratio, on a log scale">
    <defs><linearGradient id="dr-bg-alb" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#5fbe8c" stop-opacity=".9"/><stop offset="1" stop-color="#0b7774" stop-opacity=".55"/></linearGradient></defs>
    ${zones}${refs}
    <path d="${area}" fill="url(#dr-bg-alb)"/><path d="M${line}" fill="none" stroke="#0b7774" stroke-width="1.6"/>
    <line x1="${mx}" x2="${mx}" y1="${T + 2}" y2="${base}" stroke="#0d2226" stroke-width="1.6"/>
    <line class="dr-s-ax" x1="${L}" x2="${W - R}" y1="${base}" y2="${base}"/>${ticks}${marks}
    <text x="${W - R}" y="${H - 1}" text-anchor="end">mg/g</text>
  </svg>`
}

function trendSVG(t) {
  // On mobile, a narrower drawing width: that way the text does not shrink when scaled.
  const W = narrow() ? 340 : 540
  const H = narrow() ? 170 : 156
  const L = 8
  const R = narrow() ? 36 : 82
  const T = 10
  const B = 22
  const meas = t.meas ?? []
  const traj = t.traj ?? []
  const proj = t.proj?.[0]
  const allDates = [...meas.map((x) => x[0]), TODAY, ...(proj ? [proj[0]] : [])]
  const d0 = Math.min(...allDates.map(days)) - 70
  const d1 = Math.max(...allDates.map(days)) + 20
  const vals = [...meas.map((x) => x[1]), ...traj.flatMap((x) => [x[2], x[3]]), t.low, t.high, ...(proj ? [proj[2], proj[3]] : [])]
  const y0 = Math.max(0, Math.min(45, Math.floor((Math.min(...vals) - 8) / 5) * 5))
  const y1 = Math.max(100, Math.ceil((Math.max(...vals) + 4) / 5) * 5)
  const x = (iso) => L + ((days(iso) - d0) / (d1 - d0)) * (W - L - R)
  const y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B)
  const bands = [
    [90, y1, 'G1'],
    [60, 90, 'G2'],
    [45, 60, 'G3a'],
    [30, 45, 'G3b'],
    [15, 30, 'G4'],
  ]
    .filter(([a, b]) => b > y0 && a < y1)
    .map(([a, b, g], i) => {
      const top = y(Math.min(b, y1))
      const bot = y(Math.max(a, y0))
      return `<rect x="${L}" y="${top.toFixed(1)}" width="${W - L - R}" height="${(bot - top).toFixed(1)}" fill="${i % 2 ? '#f6f8f7' : '#fbfcfc'}"/><text x="${W - R + 6}" y="${((top + bot) / 2 + 3).toFixed(1)}">${g}</text>`
    })
    .join('')
  const refs = [60, 90]
    .filter((v) => v > y0 && v < y1)
    .map((v) => `<line class="${v === 60 ? 'dr-s-ref' : 'dr-s-grid'}" x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/>`)
    .join('')
  const pts = [...traj.map(([d, l, lo, hi]) => [d, l, lo, hi]), [TODAY, t.level, t.low, t.high]]
  const solid = traj.map(([d, l]) => `${x(d).toFixed(1)},${y(l).toFixed(1)}`).join('L')
  const lastT = traj[traj.length - 1]
  const dash = lastT ? `M${x(lastT[0]).toFixed(1)},${y(lastT[1]).toFixed(1)}L${x(TODAY).toFixed(1)},${y(t.level).toFixed(1)}${proj ? `L${x(proj[0]).toFixed(1)},${y(proj[1]).toFixed(1)}` : ''}` : ''
  const band = [...pts, ...(proj ? [proj] : [])]
  const bandPath = `M${band.map(([d, , , hi]) => `${x(d).toFixed(1)},${y(hi).toFixed(1)}`).join('L')}L${band
    .slice()
    .reverse()
    .map(([d, , lo]) => `${x(d).toFixed(1)},${y(lo).toFixed(1)}`)
    .join('L')}Z`
  const dots = meas.map(([d, v]) => `<circle cx="${x(d).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3.6" fill="#0d2226" stroke="#fff" stroke-width="1.3"><title>${d.slice(5, 7)}/${d.slice(8, 10)}/${d.slice(0, 4)}: eGFR ${num(v)}</title></circle>`).join('')
  const years = []
  const ya = new Date(d0 * 86_400_000).getUTCFullYear() + 1
  const yb = new Date(d1 * 86_400_000).getUTCFullYear()
  for (let yr = ya; yr <= yb; yr++) years.push(yr)
  const yTicks = years.map((yr) => `<line class="dr-s-ax" x1="${x(`${yr}-01-01`).toFixed(1)}" x2="${x(`${yr}-01-01`).toFixed(1)}" y1="${H - B}" y2="${H - B + 4}"/><text x="${x(`${yr}-01-01`).toFixed(1)}" y="${H - 6}" text-anchor="middle">${yr}</text>`).join('')
  const tx = x(TODAY)
  return `<svg class="dr-svg dr-fade" viewBox="0 0 ${W} ${H}" role="img" aria-label="Glomerular filtration: lab results, model trend and its uncertainty up to today">
    ${bands}${refs}
    <path d="${bandPath}" fill="#0b7774" fill-opacity=".14"/>
    ${solid ? `<path d="M${solid}" fill="none" stroke="#0b7774" stroke-width="2"/>` : ''}
    ${dash ? `<path d="${dash}" fill="none" stroke="#0b7774" stroke-width="2" stroke-dasharray="4 4"/>` : ''}
    <line x1="${tx.toFixed(1)}" x2="${tx.toFixed(1)}" y1="${T}" y2="${H - B}" stroke="#0d2226" stroke-width="1" opacity=".35"/>
    <circle cx="${tx.toFixed(1)}" cy="${y(t.level).toFixed(1)}" r="4.2" fill="#fff" stroke="#0b7774" stroke-width="2"/>
    <text class="dr-s-lbl" x="${(tx - 6).toFixed(1)}" y="${(y(t.high) - 5).toFixed(1)}" text-anchor="end">today ${num(t.level)}</text>
    ${dots}
    <line class="dr-s-ax" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>${yTicks}
  </svg>`
}

function bpSVG(byDay) {
  const W = narrow() ? 250 : 300
  const H = 82
  const L = 26
  const R = 8
  const T = 8
  const B = 16
  const y0 = 70
  const y1 = 165
  const x = (i) => L + (i / Math.max(1, byDay.length - 1)) * (W - L - R)
  const y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B)
  const line = (k) => byDay.map((d, i) => `${x(i).toFixed(1)},${y(d[k]).toFixed(1)}`).join('L')
  const dots = (k, c) => byDay.map((d, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(d[k]).toFixed(1)}" r="2.6" fill="${i === 0 ? '#fff' : c}" stroke="${c}" stroke-width="1.4"><title>${d[0].slice(5, 7)}/${d[0].slice(8, 10)}: ${d[1]}/${d[2]}${i === 0 ? ' (does not count)' : ''}</title></circle>`).join('')
  return `<svg class="dr-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mean blood pressure for each day against the 135/85 thresholds">
    <line x1="${L}" x2="${W - R}" y1="${y(135)}" y2="${y(135)}" stroke="#d9766e" stroke-dasharray="4 3"/><text x="${L - 4}" y="${y(135) + 3}" text-anchor="end">135</text>
    <line x1="${L}" x2="${W - R}" y1="${y(85)}" y2="${y(85)}" stroke="#0b7774" stroke-dasharray="4 3"/><text x="${L - 4}" y="${y(85) + 3}" text-anchor="end">85</text>
    <path d="M${line(1)}" fill="none" stroke="#d9766e" stroke-width="1.8"/>${dots(1, '#d9766e')}
    <path d="M${line(2)}" fill="none" stroke="#0b7774" stroke-width="1.8"/>${dots(2, '#0b7774')}
    <text x="${L}" y="${H - 3}">${byDay[0][0].slice(5, 7)}/${byDay[0][0].slice(8, 10)}</text><text x="${W - R}" y="${H - 3}" text-anchor="end">${byDay[byDay.length - 1][0].slice(5, 7)}/${byDay[byDay.length - 1][0].slice(8, 10)}</text>
  </svg>`
}

/** A short single-lead ECG snippet (3 s of the 30), drawn with Gaussian waves. */
function ecgPath(kind, W = 360, H = 46) {
  const perSecond = W / 3
  const beats = []
  if (kind === 'af') {
    const rr = [0.52, 0.81, 0.43, 0.68, 0.95, 0.5, 0.74]
    let t = 0.22
    for (const r of rr) {
      beats.push(t)
      t += r
      if (t > 3.1) break
    }
  } else {
    const rr = kind === 'lowef' ? 0.74 : 0.84
    for (let t = 0.3; t < 3.1; t += rr) beats.push(t)
  }
  const g = (t, c, w) => Math.exp(-((t - c) ** 2) / (2 * w * w))
  const v = (t) => {
    let s = 0
    for (const b of beats) {
      if (kind !== 'af') s += 0.11 * g(t, b - 0.17, 0.022)
      s += -0.09 * g(t, b - 0.03, 0.009)
      s += (kind === 'lowef' ? 0.58 : 1) * g(t, b, kind === 'lowef' ? 0.019 : 0.011)
      s += -0.2 * g(t, b + 0.034, kind === 'lowef' ? 0.014 : 0.01)
      s += (kind === 'lowef' ? -0.08 : 0.26) * g(t, b + 0.27, 0.05)
    }
    if (kind === 'af') s += 0.035 * Math.sin(t * 2 * Math.PI * 6.2) + 0.02 * Math.sin(t * 2 * Math.PI * 9.3 + 1.2)
    return s
  }
  let d = ''
  for (let px = 0; px <= W; px += 1.5) d += `${px ? 'L' : 'M'}${px.toFixed(1)},${(H * 0.68 - v(px / perSecond) * H * 0.58).toFixed(1)}`
  return d
}

// --- Pieces of the patient file ----------------------------------------------------------------
function albHTML(p, m) {
  const a = m.alb
  if (!a) return ''
  return `<div class="dr-card">
    <div class="dr-ch"><p>Albuminuria</p>${stateChip(a.status, a.label)}</div>
    <p class="dr-big"><b>${num(a.median)}<small> mg/g</small></b><small>${range(a.low, a.high)} · P(30 or more) ${pct(a.p2)}</small></p>
    ${m.belief ? beliefSVG(m.belief, p.samples ?? [], a.median) : ''}
    <p class="dr-note-s">${esc(p.albNote ?? '')}</p>
  </div>`
}

const TREND_LABEL = { estable: 'stable', descenso: 'declining', descenso_rapido: 'rapid decline', incierto: 'uncertain', insuficiente: 'little data', sin_datos: 'no data' }
function fgHTML(p, m) {
  const t = m.trend
  if (t) {
    const n = (t.meas ?? []).length
    return `<div class="dr-card">
      <div class="dr-ch"><p>eGFR trend</p><small>${n} ${n === 1 ? 'lab set' : 'lab sets'} · ${TREND_LABEL[t.status] ?? t.status}</small></div>
      <p class="dr-big"><b>${num(t.slope, 1)}<small> mL/min/1.73 m² per year</small></b><small>between ${num(t.slopeLow, 1)} and ${num(t.slopeHigh, 1)} · today, ${num(t.level)} (${range(t.low, t.high)})</small></p>
      ${trendSVG(t)}
      <p class="dr-note-s">${esc(p.trendNote ?? '')}</p>
    </div>`
  }
  const e = m.blood?.egfr
  if (!e) return ''
  const measured = e[3]
  return `<div class="dr-card">
    <div class="dr-ch"><p>Glomerular filtration</p><small>${measured ? 'measured' : esc(e[4])}</small></div>
    <p class="dr-big"><b>${num(e[0])}<small> mL/min/1.73 m²</small></b><small>${measured ? 'no series for a trend' : `between ${range(e[1], e[2])} · P(eGFR < 60) ${pct(m.pG60)}`}</small></p>
    <p class="dr-note-s">${esc(p.fgNote ?? '')}</p>
  </div>`
}

function probsHTML(m) {
  const rows = [['Kidney disease (eGFR < 60 or ratio ≥ 30)', m.pCkd]]
  rows.push(m.pDm == null ? ['Diabetes', 'on record'] : ['Undiagnosed diabetes', m.pDm])
  if (m.pBnp != null) rows.push(['NT-proBNP ≥ 125 pg/mL', m.pBnp])
  if (m.pAf != null) rows.push(['Atrial fibrillation', m.pAf])
  if (m.pEf != null) rows.push(['Ejection fraction ≤ 40%', m.pEf])
  return `<ul class="dr-probs" aria-label="Other probabilities">${rows
    .map(([label, p]) =>
      typeof p === 'string'
        ? `<li><span>${label}</span><b>${p}</b></li>`
        : `<li><span>${label}</span><b>${pct(p)}</b><span class="dr-bar is-ink" aria-hidden="true"><i style="--p:${Math.max(0.004, p).toFixed(3)}"></i></span></li>`,
    )
    .join('')}</ul>`
}

function byTestHTML(m) {
  const rows = Object.entries(m.byTest ?? {})
    .filter(([, p]) => p >= 0.005)
    .sort((a, b) => b[1] - a[1])
  if (!rows.length) return ''
  return `<ul class="dr-probs" aria-label="New finding if only each test were done">${rows
    .map(([t, p], i) => `<li><span>${i === 0 ? '<em class="dr-best">most informative</em>' : ''}${esc(TEST_NAMES[t] ?? t)}</span><b>${pct(p)}</b><span class="dr-bar" aria-hidden="true"><i style="--p:${p.toFixed(3)}"></i></span></li>`)
    .join('')}</ul>`
}

function srcHTML(p) {
  const st = S.liveState[p.id]
  const live = S.live[p.id]
  if (LIVE[p.id] && st === 'wait') return '<span class="dr-src is-wait"><i></i>asking the model…</span>'
  if (live) {
    const calls = ['assess', ...(LIVE[p.id].albuminuria ? ['albuminuria'] : []), ...(LIVE[p.id].trend ? ['egfr-trend'] : [])]
    return `<span class="dr-src is-live" title="Recomputed just now: ${calls.map((c) => `POST /api/model/${c}`).join(', ')}"><i></i>computed by the model · ${num(live.ms)} ms</span>`
  }
  return '<span class="dr-src" title="Computed with the same model on 11/16/2026 and saved in the page"><i></i>computed by the model · saved copy</span>'
}

function cvHTML(p, m) {
  const cv = m.cv
  if (!cv) return ''
  const names = ['Low to moderate', 'High', 'Very high']
  const head = `<em aria-hidden="true"></em>${names.map((n) => `<em>${n}</em>`).join('')}`
  const rec = `<span>On record</span>${names
    .map((n, i) => `<div class="dr-cv-c${i === cv.rec ? ' is-on' : ''}">${i === cv.rec ? `<b>${cv.approx ? 'SCORE2-OP' : 'SCORE2'} ${pct1(cv.score)}</b><small>${cv.approx ? 'with assumed data' : 'with what is on record'}</small>` : ''}</div>`)
    .join('')}`
  const home = `<span>With home measurements</span>${cv.probs
    .map((q, i) => `<div class="dr-cv-c${i === cv.cat ? ' is-on' : ''}" style="--p:${q.toFixed(3)}"><i></i><b>${pct(q)}</b></div>`)
    .join('')}`
  const more = []
  if (cv.rec === cv.cat && cv.probs[cv.cat] > 0.9) more.push(`Same category: ${names[cv.cat].toLowerCase()}. ${esc(p.cvExtra ?? '')}`)
  else if (cv.probs[2] > 0.05 && cv.rec < 2) more.push(`Probability that it is very high: <b>${pct(cv.probs[2])}</b>. What is still unmeasured will settle it.`)
  if (m.hr) more.push(`With home measurements, the risk of cardiovascular death is <b>${num(m.hr, 1)}</b> times that of the same age and sex (outcomes model).`)
  return `<div class="dr-cv" role="table" aria-label="Cardiovascular risk category: the one on record and the likely one with home measurements">${head}${rec}${home}</div>
    ${more.length ? `<p class="dr-cv-more">${more.map((t) => `<span>${t}</span>`).join('')}</p>` : ''}`
}

function reqHTML(p, m) {
  const items = p.req ?? []
  if (!items.length) return `<div class="dr-box"><div class="dr-box-h">${ico('flask')}<p>Order</p><small>nothing to order</small></div><div class="dr-box-b"><p class="dr-note-s">${esc(p.reqEmpty ?? '')}</p></div></div>`
  const checked = S.req[p.id] ?? items.map((x) => x.on)
  const sent = S.sent[`${p.id}:req`]
  const n = checked.filter(Boolean).length
  return `<div class="dr-box">
    <div class="dr-box-h">${ico('flask')}<p>${esc(p.reqTitle ?? 'Lab order')}</p><small>prefilled · review and send</small></div>
    <div class="dr-box-b"><div class="dr-req">${items
      .map(
        (x, i) =>
          `<label><input type="checkbox" data-req="${p.id}" data-i="${i}"${checked[i] ? ' checked' : ''}${sent ? ' disabled' : ''}><span><b>${esc(x.t)}</b><span>${esc(fixPct(val(x.d, m)))}</span></span></label>`,
      )
      .join('')}</div></div>
    <div class="dr-box-f"><p>${p.action === 'farmacia' ? 'The pharmacy gets the voucher and the app notifies the patient.' : 'The patient picks the day of the blood draw in the app.'}</p>${
      sent
        ? `<span class="dr-done">${ico('check')}${p.action === 'farmacia' ? 'Voucher sent' : 'Order sent'}</span>`
        : `<button type="button" class="dr-btn is-sm" data-do="req" data-id="${p.id}"${n ? '' : ' disabled'}>${ico('send')}${esc(p.reqBtn ?? `Send order (${n})`)}</button>`
    }</div>
  </div>`
}

function noteHTML(p, m) {
  const text = S.notes[p.id] ?? val(p.note, m)
  const copied = S.sent[`${p.id}:note`]
  const codes = p.codes?.length
    ? `<p class="dr-codes-h">${esc(p.codesWhen)}</p><div class="dr-codes">${p.codes.map(([c, t]) => `<span class="dr-code"><b>${c}</b>${esc(t)}</span>`).join('')}</div>`
    : ''
  return `<div class="dr-box">
    <div class="dr-box-h">${ico('doc')}<p>Clinical note</p><small>prewritten · editable</small></div>
    <div class="dr-box-b"><label class="dr-sr" for="dr-note-${p.id}">Clinical note for ${esc(p.first)}</label><textarea class="dr-notetext" id="dr-note-${p.id}" data-note="${p.id}" rows="7" spellcheck="false">${esc(text)}</textarea>${codes}</div>
    <div class="dr-box-f"><p>Pasted into the progress notes with the codes.</p>${
      copied ? `<span class="dr-done">${ico('check')}Copied to record</span>` : `<button type="button" class="dr-btn is-sm" data-do="copy" data-id="${p.id}">${ico('copy')}Copy to record</button>`
    }</div>
  </div>`
}

function guideHTML(p) {
  if (!p.guide?.length) return ''
  return `<div class="dr-box">
    <div class="dr-box-h">${ico('book')}<p>Guideline suggestions</p><small>to consider</small></div>
    <div class="dr-box-b"><ul class="dr-guide">${p.guide
      .map(([tag, text, src]) => `<li><span class="dr-tag${tag === 'Consider' || tag === 'If confirmed' ? '' : ' is-later'}">${esc(tag)}</span><p>${esc(text)}</p><cite>${esc(src)}</cite></li>`)
      .join('')}</ul>
    <p class="dr-disc">${ico('shield')}Decision support: LatentHealth does not prescribe treatment. You decide.</p></div>
  </div>`
}

function msgHTML(p) {
  if (!p.msg) return ''
  const sent = S.sent[`${p.id}:msg`]
  return `<div class="dr-box">
    <div class="dr-box-h">${ico('send')}<p>Message to the patient</p><small>draft · shown in the app</small></div>
    <div class="dr-box-b"><p class="dr-msgprev">${esc(p.msg)}</p></div>
    <div class="dr-box-f"><p>With their home tests linked.</p>${
      sent ? `<span class="dr-done">${ico('check')}Sent</span>` : `<button type="button" class="dr-btn is-sm" data-do="msg" data-id="${p.id}">${ico('send')}Send to patient</button>`
    }</div>
  </div>`
}

function timelineHTML(p, m) {
  const items = (p.tl ?? []).map((e) => {
    let extra = ''
    if (e.swatches) extra += `<p class="dr-sub">${e.swatches.map(([a, c]) => swatch(a, c)).join(' ')}</p>`
    if (e.pseq) {
      extra += `<div class="dr-pseq" aria-label="Probability of albuminuria after each strip">${e.pseq
        .map((q, i) => `${i ? ico('chev') : ''}<span class="${q >= 0.95 ? 'is-top' : q >= 0.5 ? 'is-hi' : ''}">${pct(q)}</span>`)
        .join('')}</div>`
    }
    if (e.bp && m.bp?.byDay) extra += `<div class="dr-mini">${bpSVG(m.bp.byDay)}</div>`
    if (e.ecg) {
      const label = { regular: 'regular rhythm', af: 'irregular rhythm, no clear P waves', lowef: 'low-voltage, slightly wide QRS' }[e.ecg]
      extra += `<div class="dr-ecg" role="img" aria-label="Snippet of the watch ECG: ${label}" title="3 s of the 30 recorded (illustrative tracing)"><svg viewBox="0 0 360 46" preserveAspectRatio="none" aria-hidden="true"><path d="${ecgPath(e.ecg)}"/></svg></div>`
    }
    if (e.said) extra += `<p class="dr-app-said">${ico('phone')}The app told them: “${esc(e.said)}”</p>`
    const sub = e.sub ? `<p class="dr-sub">${esc(val(e.sub, m))}</p>` : ''
    const meta = e.meta ? ` <span>· ${esc(val(e.meta, m))}</span>` : ''
    return `<li class="${e.hot ? 'is-hot' : ''}"><time>${e.d}</time><span class="dr-tl-dot">${ico(e.icon)}</span><div class="dr-tl-c"><p>${esc(val(e.t, m))}${meta}</p>${sub}${extra}</div></li>`
  })
  return `<ol class="dr-tl">${items.join('')}</ol>`
}

function whyHTML(p, m) {
  const items = []
  if (p.group === 'act') {
    for (const alert of m.alerts ?? []) items.push(`<li>${ico('alert', 'sm')}<span><q>${esc(fixPct(alert))}</q></span></li>`)
    if (p.bpAlert && m.bp?.valid && m.bp.p >= 0.9) items.push(`<li>${ico('alert', 'sm')}<span><q>${esc(fixPct(m.bp.msg))}</q></span></li>`)
  } else {
    items.push(`<li class="is-ctx">${ico('flask', 'sm')}<span>Probability of a new finding if the tests are completed: <b>${pct(m.row?.p)}</b>.</span></li>`)
  }
  for (const c of p.ctx ?? []) items.push(`<li class="is-ctx">${ico('info', 'sm')}<span>${esc(val(c, m))}</span></li>`)
  const quote = p.quote && m.alb?.action ? `<p class="dr-quote"><b>What the albuminuria filter says</b><br>${esc(fixPct(m.alb.action))}</p>` : ''
  return `<ul class="dr-reasons">${items.join('')}</ul>${p.group === 'med' ? byTestHTML(m) : ''}${quote}`
}

function fileHTML(p) {
  const m = M(p.id)
  const a = ACTIONS[p.action]
  const done = S.done[p.id]
  const sex = p.sex === 'M' ? 'Male' : 'Female'
  const meds = p.meds ? `<span>Takes</span>${esc(p.meds)}` : ''
  const primary = done
    ? `<span class="dr-done">${ico('check')}${esc(done)}</span>`
    : `<button type="button" class="dr-btn is-pri" data-do="row" data-id="${p.id}">${ico(a.icon)}${a.label}</button>`
  const second = p.msg
    ? S.sent[`${p.id}:msg`]
      ? `<span class="dr-done">${ico('check')}Message sent</span>`
      : `<button type="button" class="dr-btn" data-do="msg" data-id="${p.id}">${ico('send')}Send to patient</button>`
    : p.msgToast
      ? `<button type="button" class="dr-btn" data-do="msg" data-id="${p.id}">${ico('call')}${esc(p.msgVia)}</button>`
      : ''
  const copy = S.sent[`${p.id}:note`] ? `<span class="dr-done">${ico('check')}Note copied</span>` : `<button type="button" class="dr-btn" data-do="copy" data-id="${p.id}">${ico('copy')}Copy to record</button>`
  return `<header class="dr-fhead">
      <span class="dr-av is-lg" aria-hidden="true">${p.ini}</span>
      <div><h3 id="dr-file-h">${esc(p.name)}</h3><p>${p.age} years · ${sex} · ID •••• ${p.cip} · ${esc(p.channel)}</p></div>
      <div class="dr-fhead-r"><span class="dr-pill g-${p.group}">${GROUPS[p.group][0]}</span><span id="dr-src">${srcHTML(p)}</span></div>
    </header>
    <p class="dr-consta"><span>On record</span>${p.consta.map((c) => `<em>${esc(c)}</em>`).join('')}${meds}</p>
    <div class="dr-fbody">
      <section class="dr-sec" aria-labelledby="dr-s1"><div class="dr-sh"><h4 id="dr-s1">Why they are on the list</h4><small>${p.group === 'act' ? 'finding not on record' : 'what measuring would add'}</small></div>${whyHTML(p, m)}</section>
      <section class="dr-sec" aria-labelledby="dr-s2"><div class="dr-sh"><h4 id="dr-s2">What the model believes</h4><small>as of ${TODAY.slice(5, 7)}/${TODAY.slice(8, 10)}/${TODAY.slice(0, 4)}</small></div>
        <div class="dr-m2">${kdigoHTML(m)}${albHTML(p, m)}</div>${fgHTML(p, m)}${probsHTML(m)}</section>
      <section class="dr-sec" aria-labelledby="dr-s3"><div class="dr-sh"><h4 id="dr-s3">Home and lab tests</h4><small>most recent first</small></div>${timelineHTML(p, m)}</section>
      <section class="dr-sec" aria-labelledby="dr-s4"><div class="dr-sh"><h4 id="dr-s4">Cardiovascular risk</h4><small>SCORE2 and European guideline</small></div>${cvHTML(p, m)}</section>
      <section class="dr-sec" aria-labelledby="dr-s5"><div class="dr-sh"><h4 id="dr-s5">Prepared for you</h4><small>review, change anything you like and send</small></div>
        <div class="dr-prep">${reqHTML(p, m)}${noteHTML(p, m)}${guideHTML(p)}${msgHTML(p)}</div></section>
    </div>
    <div class="dr-fbar">${primary}<span class="dr-sp"></span>${copy}${second}</div>`
}

// --- The list ----------------------------------------------------------------------------------
function rowHTML(p, i) {
  const m = M(p.id)
  const sel = p.id === S.sel
  const done = S.done[p.id]
  const chips = p.chips
    .map(([k, icon, t]) => [k, icon, val(t, m)])
    .filter(([, , t]) => t)
    .map(([k, icon, t]) => `<span class="dr-chip dr-k-${k}">${ico(icon)}${esc(t)}</span>`)
    .join('')
  // What has already been done from the file also shows on the row.
  const marks = []
  if (S.sent[`${p.id}:req`] && p.action !== 'analitica' && p.action !== 'farmacia') marks.push('Order sent')
  if (S.sent[`${p.id}:note`]) marks.push('Note in record')
  if (S.sent[`${p.id}:msg`]) marks.push(p.msg ? 'Message sent' : 'Nurse notified')
  const marked = marks.map((t) => `<span class="dr-chip dr-k-done">${ico('check')}${t}</span>`).join('')
  const prob =
    p.group === 'med' && m.row
      ? `<div class="dr-prob"><span class="dr-bar" role="img" aria-label="Probability of a new finding: ${pct(m.row.p)}"><i style="--p:${m.row.p.toFixed(3)};--i:${i}"></i></span><b aria-hidden="true">${pct(m.row.p)}</b><span>${ico(p.testIcon ?? 'flask', 'xs')}<em>${esc(p.test)}</em>· ${esc(p.how)}</span></div>`
      : ''
  const act = done
    ? `<span class="dr-done">${ico('check')}${esc(done)}<button type="button" data-do="undo" data-id="${p.id}" aria-label="Undo: ${esc(done)}">Undo</button></span>`
    : `<button type="button" class="dr-btn is-sm" data-do="row" data-id="${p.id}">${ico(ACTIONS[p.action].icon)}${ACTIONS[p.action].label}</button>`
  return `<li class="dr-row${sel ? ' is-sel' : ''}${done ? ' is-done' : ''}" data-id="${p.id}" style="--i:${i}">
    <span class="dr-av" aria-hidden="true">${p.ini}</span>
    <button type="button" class="dr-open" data-open="${p.id}" tabindex="${sel ? 0 : -1}" aria-current="${sel}" aria-describedby="dr-why-${p.id}">${esc(p.short)} <small>${p.age} · ${p.sex}</small></button>
    <p class="dr-why" id="dr-why-${p.id}">${esc(val(p.why, m))}</p>
    ${prob}
    <div class="dr-chips">${chips}${marked}</div>
    <div class="dr-row-act">${act}</div>
  </li>`
}

// What happens at home (kit, pharmacy voucher, reminder) can be approved in one go.
const HOME_ACTIONS = { kit: 'a kit', farmacia: 'a pharmacy voucher', recordar: 'a reminder' }
const batchable = () => PATIENTS.filter((p) => p.action in HOME_ACTIONS && !S.done[p.id])
const listText = (items) => (items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}` : items[0] ?? '')

function batchHTML() {
  const items = batchable()
  if (!items.length) return ''
  const n = items.length
  return `<div class="dr-batch">${ico('auto')}<p><b>${n === 1 ? 'One home proposal' : `${n} home proposals`}</b>, ready to approve: ${listText(items.map((p) => `${HOME_ACTIONS[p.action]} (${p.first})`))}.</p>
    <button type="button" class="dr-btn is-sm" data-do="batch">${ico('check')}Approve ${n === 1 ? 'it' : `all ${n}`}</button></div>`
}

function doBatch() {
  const items = batchable()
  if (!items.length) return
  for (const p of items) {
    S.done[p.id] = p.doneLabel ?? ACTIONS[p.action].done
    if (p.action === 'farmacia') S.sent[`${p.id}:req`] = true
  }
  const refresh = () => {
    if (S.view === 'hoy') {
      renderGroups()
      renderFile({ keepScroll: true })
    } else renderView()
    renderNav()
  }
  refresh()
  toast(`Approved in one go: ${listText(items.map((p) => HOME_ACTIONS[p.action]))}. Each patient will see it in the app.`, () => {
    for (const p of items) {
      delete S.done[p.id]
      delete S.sent[`${p.id}:req`]
    }
    refresh()
  })
}

function groupsHTML() {
  const visible = (p) => (S.group === 'todo' || p.group === S.group) && (!S.area || p.areas.includes(S.area))
  let i = 0
  const out = []
  for (const g of ['act', 'med']) {
    if (S.group !== 'todo' && S.group !== g) continue
    const rows = PATIENTS.filter((p) => p.group === g && visible(p))
    const [label, desc, icon] = GROUPS[g]
    const count = g === 'med' ? MEDIR_TOTAL - PATIENTS.filter((p) => p.group === 'med' && S.done[p.id]).length : pending('act')
    out.push(`<section class="dr-group g-${g}" aria-label="${label}">
      <div class="dr-gh"><span class="dr-gtag">${ico(icon)}${label}<b>${num(count)}</b></span><small>${desc}</small></div>
      ${g === 'med' ? batchHTML() : ''}
      ${rows.length ? `<ul class="dr-rows">${rows.map((p) => rowHTML(p, i++)).join('')}</ul>` : '<p class="dr-empty">No one in this group with this filter.</p>'}
      ${g === 'med' && !S.area ? `<p class="dr-more">${ico('chev', 'xs')}And ${MEDIR_TOTAL - 7} more, with probability below 7%.</p>` : ''}
    </section>`)
  }
  if (S.group === 'todo' && !S.area) {
    out.push(`<section class="dr-group g-ok" aria-label="Nothing pending">
      <div class="dr-gh"><span class="dr-gtag">${ico('check')}Nothing pending<b>${num(SIN_PENDIENTES)}</b></span><small>${GROUPS.ok[1]}</small></div>
      <button type="button" class="dr-more" data-do="view" data-view="pacientes">${ico('users', 'xs')}See the whole practice list</button>
    </section>`)
  }
  return out.join('')
}

function filtersHTML() {
  const all = PATIENTS.length
  const segs = [
    ['todo', 'All', all],
    ['act', 'Act', PATIENTS.filter((p) => p.group === 'act').length],
    ['med', 'Measure', PATIENTS.filter((p) => p.group === 'med').length],
  ]
    .map(([k, l, n]) => `<button type="button" data-seg="${k}" aria-pressed="${S.group === k}">${l}<b>${n}</b></button>`)
    .join('')
  const chips = AREAS.map(([k, l, icon]) => `<button type="button" class="dr-fchip" data-area="${k}" aria-pressed="${S.area === k}">${ico(icon, 'xs')}${l}</button>`).join('')
  return `<div class="dr-seg" role="group" aria-label="Group">${segs}</div><div class="dr-fchips" role="group" aria-label="Filter by signal">${chips}</div>`
}

function hoyHTML() {
  const p = P[S.sel] ?? PATIENTS[0]
  return `<div class="dr-view dr-hoy">
    <section class="dr-listpane dr-scroll" id="dr-listpane" aria-label="Today's worklist">
      <header class="dr-lhead">
        <h3>Today <small>practice list of 1,500 · example</small></h3>
        <p class="dr-lsum">Sorted by what would change, not by who is worse off.</p>
        <div class="dr-filters" id="dr-filters">${filtersHTML()}</div>
      </header>
      <div id="dr-groups">${groupsHTML()}</div>
    </section>
    <article class="dr-file dr-scroll" id="dr-file" tabindex="-1" aria-labelledby="dr-file-h">${fileHTML(p)}</article>
  </div>`
}

// --- Other views -------------------------------------------------------------------------------
function attachHTML(id) {
  const p = P[id]
  const m = M(id)
  if (id === 'pilar') {
    return `<div class="dr-attach"><p class="dr-attach-h">${ico('paperclip', 'xs')}Her home tests, attached</p><ul>
      <li><time>11/12</time>${swatch(30, 100)} Strip: albumin 30 mg/L, creatinine 100 mg/dL ${stateChip('dudosa', 'Doubtful')} <span>→ “Repeat tomorrow”</span></li>
      <li><time>11/13</time>${swatch(30, 100)} Strip: same ${stateChip('dudosa', 'Doubtful')} <span>→ “Send the tube”</span></li>
      <li><time>11/14</time>${ico('tube', 'xs')} Tube sent: reaches the lab on Tuesday the 17th</li></ul>
      <p class="dr-model-says">The model: P(albuminuria) <b>${pct(m.alb.p2)}</b>, estimated ratio ${num(m.alb.median)} mg/g (${range(m.alb.low, m.alb.high)}). If the tube is normal, screening ends; if it is high, the app asks to repeat in three months. While the result is pending, the protocol does not call for a visit.</p></div>`
  }
  if (id === 'carmen') {
    return `<div class="dr-attach"><p class="dr-attach-h">${ico('paperclip', 'xs')}Her blood pressure week, attached</p><div class="dr-mini">${bpSVG(m.bp.byDay)}</div>
      <p class="dr-model-says">${esc(fixPct(m.bp.msg))} No hypertension on record: she is on your list today, under Act.</p></div>`
  }
  return ''
}

function inboxHTML() {
  const sel = MESSAGES.find((x) => x.id === S.msgSel) ?? MESSAGES[0]
  const p = P[sel.id]
  const list = MESSAGES.map((x) => {
    const q = P[x.id]
    const isUnread = x.unread && !S.msgs[x.id]?.read
    const tag = x.bot ? `<span class="dr-chip dr-k-auto">${ico('auto')}Answered by the assistant</span>` : isUnread ? `<span class="dr-chip dr-k-msg">${ico('msg')}Unanswered</span>` : `<span class="dr-chip">${ico('check')}Replied</span>`
    return `<button type="button" class="dr-mitem${isUnread ? ' is-unread' : ''}" data-msg="${x.id}" aria-current="${x.id === sel.id}"><span class="dr-av" aria-hidden="true">${q.ini}</span><b>${esc(q.short)}<small>${esc(x.when)}</small></b><span class="dr-mtext">${esc(x.text)}</span>${tag}</button>`
  }).join('')
  const replies = (S.msgs[sel.id]?.replies ?? []).map((r) => `<p class="dr-bub is-me"><small>You · now</small>${esc(r)}</p>`).join('')
  const thread = `<p class="dr-bub"><small>${esc(p.first)} · ${esc(sel.when)}</small>${esc(sel.text)}</p>${attachHTML(sel.id)}${
    sel.bot ? `<p class="dr-bub is-bot"><small>App assistant · instantly</small>${esc(sel.bot)}</p><p class="dr-note-s">${ico('info', 'xs')} A frequently asked question: the assistant answered it with what the kit protocol says. You get it for your information.</p>` : ''
  }${replies}`
  let reply = ''
  if (!sel.bot && !replied(sel.id)) {
    const chosen = S.sugg[sel.id]
    const sugg = `<div class="dr-sugg"><p>Suggested replies</p>${sel.sugg
      .map((s, i) => `<button type="button" data-sugg="${i}" aria-pressed="${chosen === i}">${ico('reply')}<span>${esc(s)}</span></button>`)
      .join('')}</div>`
    reply = `${sugg}`
  }
  const box = sel.bot
    ? ''
    : `<div class="dr-reply"><label class="dr-sr" for="dr-reply-t">Your reply to ${esc(p.first)}</label><textarea id="dr-reply-t" data-draft="${sel.id}" placeholder="Write or pick a suggested reply">${esc(S.draft[sel.id] ?? '')}</textarea>
        <div><p>It reaches the app. If needed, the visit is booked from here.</p><button type="button" class="dr-btn" data-open-file="${sel.id}">${ico('doc')}View file</button><button type="button" class="dr-btn is-pri" data-do="reply" data-id="${sel.id}">${ico('send')}Send reply</button></div></div>`
  return `<div class="dr-view dr-inbox">
    <section class="dr-mlist dr-scroll" aria-label="Patient messages"><header><h3>Messages</h3><p>${unread()} unanswered · ${MESSAGES.length} this week</p></header>${list}</section>
    <section class="dr-conv dr-scroll" aria-label="Conversation with ${esc(p.first)}">
      <div class="dr-conv-h"><span class="dr-av" aria-hidden="true">${p.ini}</span><div><h4>${esc(p.name)}</h4><p>${p.age} years · ${esc(p.channel)}</p></div></div>
      <div class="dr-thread">${thread}${reply}</div>${box}
    </section>
  </div>`
}

function kitsHTML() {
  const rows = KITS.map(([id, what, ch, step0, state0, last0]) => {
    const p = P[id]
    const sentNow = S.done[id] && (p.action === 'kit' || p.action === 'farmacia')
    const step = sentNow ? 1 : step0
    const state = sentNow ? (p.action === 'farmacia' ? 'Pharmacy notified' : 'Sent today') : state0
    const last = sentNow ? 'Today · with your approval' : last0
    const steps = KIT_STEPS.map((s, i) => `<i class="${i < step ? 'is-on' : ''}${i === step - 1 && step < 4 ? ' is-now' : ''}" title="${s}"></i>`).join('')
    const pill = step === 0 ? 'med' : step >= 4 ? 'ok' : 'teal'
    const action = step === 0 ? `<button type="button" class="dr-btn is-sm" data-do="row" data-id="${id}">${ico(ACTIONS[p.action].icon)}${ACTIONS[p.action].label}</button>` : ''
    return `<tr class="is-click" data-pid="${id}" tabindex="0"><td><b>${esc(p.short)}</b><small>${p.age} · ${p.sex}</small></td><td>${esc(what)}</td><td>${esc(ch)}</td><td><span class="dr-steps" aria-label="${KIT_STEPS[Math.max(0, step - 1)]}">${steps}</span> <span class="dr-pill g-${pill}">${esc(state)}</span></td><td>${esc(last)}${action ? `<br>${action}` : ''}</td></tr>`
  }).join('')
  return `<div class="dr-view dr-page dr-scroll">
    <div class="dr-pagehead"><div><h3>Kits</h3><p>What each kit contains is decided by the patient’s file: only what is missing. Strips are sent; devices are loaned.</p></div><span class="dr-egb">${ico('info', 'xs')}Weekly figures: example</span></div>
    <div class="dr-kpis">
      <div class="dr-kpi"><b>48</b><span>kits sent this week</span><small>to those missing the test</small></div>
      <div class="dr-kpi"><b>41</b><span>strips read with the phone</span><small>without going to the center</small></div>
      <div class="dr-kpi"><b>9</b><span>doubts settled at home</span><small>by repeating the strip</small></div>
      <div class="dr-kpi"><b>4</b><span>cuffs on loan now</span><small>2 to be returned</small></div>
    </div>
    <div class="dr-tablewrap"><table class="dr-table is-resp"><caption class="dr-sr">Kits for patients on today's list</caption>
      <thead><tr><th scope="col">Patient</th><th scope="col">Contents</th><th scope="col">Channel</th><th scope="col">Status</th><th scope="col">Last step</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
  </div>`
}

function indicadoresHTML() {
  const cov = [
    ['Hypertensive', 412, 0.06, 0.58, 0.041, '4.1'],
    ['Diabetic', 167, 0.38, 0.84, 0.351, '35.1'],
  ]
    .map(
      ([name, n, before, now, ref, refText]) => `<div class="dr-cov-r"><p>${name}<small>${num(n)} on the list</small></p>
      <div class="dr-cov-bars">
        <span>Before</span><span class="dr-bar is-was" style="position:relative"><i style="--p:${before}"></i><span class="dr-ref" style="--x:${ref}" data-l="Shin 2021: ${refText}%"></span></span><b>${pct(before)}</b>
        <span>Now</span><span class="dr-bar is-teal"><i style="--p:${now}"></i></span><b>${pct(now)}</b>
      </div></div>`,
    )
    .join('')
  const funnel = [
    ['Kits sent', 186],
    ['Tests done at home', 152],
    ['Doubtful strips', 24],
    ['Tubes to the lab', 19],
    ['New diagnoses', 11],
  ]
    .map(([l, n], i) => `<li><span class="dr-fbarw"><i style="--p:${(n / 186).toFixed(3)};--i:${i}"></i><span>${l}</span></span><b>${n}</b></li>`)
    .join('')
  const auto = [
    ['box', 48, 'Kits sent', 'to those whose file said the test was missing'],
    ['strip', 41, 'Strips read with the phone', 'each one updates the Bayesian filter'],
    ['auto', 9, 'Doubts settled at home', 'by repeating the strip, no visit or lab'],
    ['tube', 6, 'Tubes to the lab', 'only when another strip would not settle it'],
    ['doc', 12, 'Clinical notes prepared', 'with the suggested ICD-10 code'],
    ['flask', 7, 'Prefilled orders', 'with the reason for each test'],
    ['bell', 57, 'Reminders', 'on test day, in the app or by text'],
    ['msg', 14, 'Questions answered by the assistant', 'the usual ones: fasting, periods, how to read the strip'],
  ]
    .map(([icon, n, t, s]) => `<li>${ico(icon)}<span>${t}<small>${s}</small></span><b>${n}</b></li>`)
    .join('')
  return `<div class="dr-view dr-page dr-scroll">
    <div class="dr-pagehead"><div><h3>Practice indicators</h3><p>What has changed since the kit started reaching homes.</p></div><span class="dr-egb">${ico('info', 'xs')}Example data</span></div>
    <div class="dr-ind">
      <section class="dr-panel"><h4>Urine test in the last 12 months</h4><p>Albumin-to-creatinine ratio measured, by group.</p>
        <div class="dr-cov">${cov}</div>
        <p class="dr-src-n">“Before”: the year before the kit. The tick is the published figure: Shin et al., <i>Hypertension</i> 2021, 3.7 million US adults.</p></section>
      <section class="dr-panel"><h4>From kit to diagnosis</h4><p>Last 90 days.</p><ol class="dr-funnel">${funnel}</ol>
        <p class="dr-funnel-n">The 11 new diagnoses: 6 kidney disease, 3 hypertension, 1 atrial fibrillation and 1 diabetes.</p></section>
    </div>
    <section class="dr-panel" style="margin-top:14px"><h4>What got done on its own this week</h4><p>Work that used to go through the clinic.</p><ul class="dr-autot">${auto}</ul></section>
  </div>`
}

function pacientesHTML() {
  const q = S.q.trim().toLowerCase()
  const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  const hit = (name, cip) => !q || norm(name).includes(norm(q)) || cip.includes(q.replace(/\D/g, '') || '\u0000')
  const rows = PATIENTS.filter((p) => hit(p.name, p.cip))
    .map((p) => {
      const m = M(p.id)
      const cv = m.cv ? ['low to moderate', 'high', 'very high'][m.cv.rec] : '—'
      return `<tr class="is-click" data-pid="${p.id}" tabindex="0"><td><b>${esc(p.name)}</b><small>ID •••• ${p.cip}</small></td><td>${p.age} · ${p.sex}</td><td><span class="dr-pill g-${p.group}">${GROUPS[p.group][0]}</span></td><td>${esc(p.last)}</td><td>${cv}</td></tr>`
    })
    .join('')
  const quiet = QUIET.filter(([name, , , , cip]) => hit(name, cip))
    .map(([name, , age, sex, cip, last, cv]) => `<tr><td><b>${esc(name)}</b><small>ID •••• ${cip}</small></td><td>${age} · ${sex}</td><td><span class="dr-pill g-ok">Nothing pending</span></td><td>${esc(last)}</td><td>${cv}</td></tr>`)
    .join('')
  const empty = !rows && !quiet ? `<p class="dr-empty">No one matching “${esc(S.q)}” in this sample of the practice list.</p>` : ''
  return `<div class="dr-view dr-page dr-scroll">
    <div class="dr-pagehead"><div><h3>Patients</h3><p>${q ? `Results for “${esc(S.q)}”. Enter opens the first one’s file.` : 'A sample of the practice list of 1,500: those on today’s list and some with nothing pending.'}</p></div><span class="dr-egb">${ico('info', 'xs')}Fictional patients</span></div>
    ${empty}${rows || quiet ? `<div class="dr-tablewrap"><table class="dr-table is-resp"><caption class="dr-sr">Patients on the practice list</caption><thead><tr><th scope="col">Patient</th><th scope="col">Age</th><th scope="col">Today</th><th scope="col">Latest</th><th scope="col">CV risk on record</th></tr></thead><tbody>${rows}${quiet}</tbody></table></div>` : ''}
  </div>`
}

// --- Rendering ---------------------------------------------------------------------------------
const NAV = [
  ['hoy', 'Today', 'hoy'],
  ['pacientes', 'Patients', 'users'],
  ['mensajes', 'Messages', 'msg'],
  ['kits', 'Kits', 'box'],
  ['indicadores', 'Practice indicators', 'chart'],
]

function navHTML() {
  return NAV.map(([k, l, icon]) => {
    const n = k === 'hoy' ? pending('act') + pending('med') : k === 'mensajes' ? unread() : ''
    return `<li><button type="button" data-nav="${k}" aria-current="${S.view === k ? 'page' : 'false'}" title="${l}">${ico(icon)}<span>${l}</span><span class="dr-n${k === 'mensajes' && n ? ' is-hot' : ''}">${n || ''}</span></button></li>`
  }).join('')
}

function shellHTML() {
  const auto = [
    [48, 'kits sent'],
    [41, 'strips read'],
    [9, 'doubts settled at home'],
    [6, 'tubes to the lab'],
    [12, 'notes prepared'],
    [57, 'reminders'],
  ]
    .map(([n, l]) => `<li><b>${n}</b><span>${l}</span></li>`)
    .join('')
  return `<div class="dr-win" role="region" aria-label="LatentHealth clinic: demo with fictional patients">
    <header class="dr-top">
      <div class="dr-dots" aria-hidden="true"><i></i><i></i><i></i></div>
      <p class="dr-brand"><span class="dr-pads" aria-hidden="true"><i></i><i></i><i></i><i></i></span>LatentHealth<span>Clinic</span></p>
      <label class="dr-search">${ico('search', 'sm')}<span class="dr-sr">Search patient or ID</span><input type="search" id="dr-q" placeholder="Search patient or ID" autocomplete="off" spellcheck="false" /><kbd aria-hidden="true">/</kbd></label>
      <p class="dr-date">${ico('cal', 'sm')}<span>Monday, November 16</span></p>
      <div class="dr-user"><span class="dr-av is-me" aria-hidden="true">CR</span><span><b>Carmen Ruiz</b><small>Family medicine</small></span></div>
    </header>
    <div class="dr-body">
      <nav class="dr-side" aria-label="Clinic sections">
        <ul class="dr-nav" id="dr-nav">${navHTML()}</ul>
        <section class="dr-auto" aria-label="Automated this week">
          <p class="dr-side-h">Automated this week</p>
          <p class="dr-side-sub">example figures</p>
          <ul>${auto}</ul>
          <button type="button" class="dr-auto-more" data-nav="indicadores">${ico('chart', 'xs')}See indicators</button>
        </section>
        <p class="dr-conn" id="dr-conn" title="Patient files are recomputed with the model running on this computer"><i></i><span>Connecting to the model…</span></p>
      </nav>
      <div class="dr-main" id="dr-main"></div>
    </div>
    <div class="dr-toast" id="dr-toast" role="status" aria-live="polite"></div>
  </div>`
}

function renderNav() {
  $('#dr-nav').innerHTML = navHTML()
}

function renderView({ focus } = {}) {
  const html = { hoy: hoyHTML, mensajes: inboxHTML, kits: kitsHTML, indicadores: indicadoresHTML, pacientes: pacientesHTML }[S.view]()
  $('#dr-main').innerHTML = html
  renderNav()
  if (S.view === 'hoy') fixRoving()
  if (focus) $(focus)?.focus()
}

function renderGroups() {
  $('#dr-filters').innerHTML = filtersHTML()
  $('#dr-groups').innerHTML = groupsHTML()
  fixRoving()
}

function renderFile({ keepScroll = false } = {}) {
  const file = $('#dr-file')
  if (!file) return
  const top = file.scrollTop
  file.innerHTML = fileHTML(P[S.sel])
  file.scrollTop = keepScroll ? top : 0
}

function refreshRow(id) {
  const li = $(`.dr-row[data-id="${id}"]`)
  if (!li) return
  const i = Number(li.style.getPropertyValue('--i')) || 0
  li.outerHTML = rowHTML(P[id], i)
  fixRoving()
}

function fixRoving() {
  const opens = $$('.dr-open')
  if (opens.length && !opens.some((b) => b.tabIndex === 0)) opens[0].tabIndex = 0
}

function setConn(state) {
  if (S.conn === 'on' && state !== 'on') return
  S.conn = state
  const el = $('#dr-conn')
  if (!el) return
  el.className = `dr-conn is-${state}`
  el.lastElementChild.textContent = state === 'on' ? 'Live model, on this computer' : 'Offline: saved copy'
}

// --- Actions -----------------------------------------------------------------------------------
function toast(text, undo) {
  const el = $('#dr-toast')
  clearTimeout(toastTimer)
  toastUndo = undo ?? null
  el.innerHTML = `${ico('check')}<span>${esc(text)}</span>${undo ? '<button type="button" data-do="toast-undo">Undo</button>' : ''}`
  el.classList.add('is-on')
  toastTimer = setTimeout(() => el.classList.remove('is-on'), 5200)
}

function afterChange(id) {
  if (S.view === 'hoy') {
    refreshRow(id)
    renderGroupCounts()
    if (S.sel === id) renderFile({ keepScroll: true })
  } else renderView()
  renderNav()
}

function renderGroupCounts() {
  const act = $('#dr-groups .dr-group.g-act .dr-gtag b')
  if (act) act.textContent = num(pending('act'))
  const med = $('#dr-groups .dr-group.g-med .dr-gtag b')
  if (med) med.textContent = num(MEDIR_TOTAL - PATIENTS.filter((p) => p.group === 'med' && S.done[p.id]).length)
}

function doRow(id) {
  const p = P[id]
  if (p.action === 'responder') {
    S.msgSel = id
    setView('mensajes', { focus: '#dr-reply-t' })
    return
  }
  S.done[id] = p.doneLabel ?? ACTIONS[p.action].done
  if (p.action === 'analitica' || p.action === 'farmacia') S.sent[`${id}:req`] = true
  afterChange(id)
  toast(val(p.toast, M(id)), () => undo(id))
  const focusTarget = $(`.dr-row[data-id="${id}"] .dr-done button`)
  if (focusTarget && document.activeElement === document.body) focusTarget.focus()
}

function undo(id) {
  const p = P[id]
  delete S.done[id]
  if (p.action === 'analitica' || p.action === 'farmacia') delete S.sent[`${id}:req`]
  afterChange(id)
  toast(`Undone: ${p.first} is pending again.`)
}

function sendRequest(id) {
  const p = P[id]
  const checked = S.req[id] ?? p.req.map((x) => x.on)
  const names = p.req.filter((_, i) => checked[i]).map((x) => x.t)
  if (!names.length) return
  S.sent[`${id}:req`] = true
  if (p.action === 'analitica' || p.action === 'farmacia') S.done[id] = p.doneLabel ?? ACTIONS[p.action].done
  afterChange(id)
  toast(
    p.action === 'farmacia'
      ? `Voucher sent to ${p.first}’s pharmacy: ${names[0].toLowerCase()}.`
      : `Order sent to the lab with ${names.length} ${names.length === 1 ? 'test' : 'tests'}. ${p.first} picks the day in the app.`,
    () => {
      delete S.sent[`${id}:req`]
      if (p.action === 'analitica' || p.action === 'farmacia') delete S.done[id]
      afterChange(id)
    },
  )
}

async function copyNote(id) {
  const p = P[id]
  const area = $(`#dr-note-${id}`)
  const text = area ? area.value : val(p.note, M(id))
  const codes = p.codes?.length ? `\n${p.codesWhen}: ${p.codes.map(([c, t]) => `${c} ${t}`).join('; ')}` : ''
  try {
    await navigator.clipboard?.writeText(text + codes)
  } catch {
    // Without clipboard permission, the demo carries on as is.
  }
  S.sent[`${id}:note`] = true
  afterChange(id)
  toast(`Note copied to ${p.first}’s record${p.codes?.length ? ` with ${p.codes.map(([c]) => c).join(' and ')}` : ''}.`, () => {
    delete S.sent[`${id}:note`]
    afterChange(id)
  })
}

function sendMessage(id) {
  const p = P[id]
  if (!p.msg && !p.msgToast) {
    S.msgSel = id
    setView('mensajes', { focus: '#dr-reply-t' })
    return
  }
  S.sent[`${id}:msg`] = true
  afterChange(id)
  toast(p.msgToast ?? `Message sent to ${p.first}’s app.`, () => {
    delete S.sent[`${id}:msg`]
    afterChange(id)
  })
}

function sendReply(id) {
  const area = $('#dr-reply-t')
  const text = (area?.value ?? '').trim()
  if (!text) {
    area?.focus()
    return
  }
  const st = (S.msgs[id] ??= { read: false, replies: [] })
  st.replies.push(text)
  st.read = true
  S.draft[id] = ''
  delete S.sugg[id]
  if (P[id].action === 'responder') S.done[id] = 'Replied'
  renderView()
  toast(`Reply sent to ${P[id].first}. They will see it in the app.`)
}

function setView(view, { focus } = {}) {
  S.view = view
  if (view === 'mensajes') {
    const st = (S.msgs[S.msgSel] ??= { read: false, replies: [] })
    if (MESSAGES.find((x) => x.id === S.msgSel)?.bot) st.read = true
  }
  renderView({ focus })
  if (view === 'hoy') ensureLive(S.sel)
}

function select(id, { focusRow = false } = {}) {
  if (!P[id]) return
  S.sel = id
  if (S.view !== 'hoy') {
    S.view = 'hoy'
    renderView()
  } else {
    $$('.dr-row').forEach((li) => {
      const on = li.dataset.id === id
      li.classList.toggle('is-sel', on)
      const b = li.querySelector('.dr-open')
      b.tabIndex = on ? 0 : -1
      b.setAttribute('aria-current', String(on))
    })
    renderFile()
  }
  fixRoving()
  if (focusRow) $(`.dr-open[data-open="${id}"]`)?.focus()
  else if (isMobile()) $('#dr-file')?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  ensureLive(id)
}

// --- Live model --------------------------------------------------------------------------------
async function post(path, body, signal) {
  const response = await fetch(`${API_BASE}/api${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Lang': document.documentElement.lang || 'en' }, body: JSON.stringify(body), signal })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

/** API response -> the same shape as the saved copy. */
function fromApi(a, b, t) {
  const al = a.albuminuria
  const keep = ['egfr', 'hba1c', 'potassium', 'nt_probnp', 'non_hdl']
  const m = {
    alb: {
      status: al.status,
      label: al.status_label,
      cat: al.category,
      p: [al.p_a1, al.p_a2, al.p_a3],
      p2: al.p_a2_plus,
      median: al.median,
      low: al.low,
      high: al.high,
      action: al.action,
      chronic: al.chronicity_met,
      resolve: al.next_sample_resolves?.first_morning ?? null,
    },
    blood: Object.fromEntries(a.blood.filter((x) => keep.includes(x.key)).map((x) => [x.key, [x.median, x.low, x.high, x.measured, x.source]])),
    pG60: a.p_egfr_below_60,
    joint: a.kdigo_joint.map((row) => row.cells.map((c) => c.p)),
    pCkd: a.p_ckd,
    dm: a.diabetes,
    pDm: a.p_diabetes,
    hf: a.heart_failure,
    pBnp: a.p_nt_probnp_high,
    pNew: a.p_new_finding,
    byTest: a.finding_by_test,
    recs: a.recommendations.map((r) => [r.test, r.reason]),
    alerts: a.alerts,
  }
  if (a.cv) m.cv = { score: a.cv.score, probs: a.cv.probs, rec: a.cv.recorded, cat: a.cv.category, approx: a.cv.approximate }
  if (b) m.belief = { pts: b.belief.uacr.map((u, i) => [u, b.belief.mass[i]]), median: b.median, low: b.low, high: b.high, p2: b.p_a2_plus }
  if (t) {
    m.trend = {
      level: t.level,
      low: t.level_low,
      high: t.level_high,
      slope: t.slope,
      slopeLow: t.slope_low,
      slopeHigh: t.slope_high,
      status: t.status,
      traj: t.trajectory.map((x) => [x.date, x.level, x.low, x.high]),
      meas: t.measurements.map((x) => [x.date, x.egfr]),
      proj: t.projection.map((x) => [x.date, x.level, x.low, x.high]),
    }
  }
  return m
}

async function ensureLive(id) {
  const body = LIVE[id]
  if (!body || S.live[id] || S.liveState[id] === 'wait') return
  S.liveState[id] = 'wait'
  if (S.sel === id) updateSrc()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 9000)
  const started = performance.now()
  try {
    const [a, b, t] = await Promise.all([
      post('/model/assess', body.assess, controller.signal),
      body.albuminuria ? post('/model/albuminuria', body.albuminuria, controller.signal) : null,
      body.trend ? post('/model/egfr-trend', body.trend, controller.signal) : null,
    ])
    S.live[id] = { m: fromApi(a, b, t), ms: Math.round(performance.now() - started) }
    S.liveState[id] = 'ok'
    setConn('on')
  } catch {
    S.liveState[id] = 'off'
    setConn('off')
  } finally {
    clearTimeout(timer)
  }
  if (S.view === 'hoy' && S.sel === id) {
    // If the doctor is typing in the file (the note), it is not repainted underneath: only the label changes.
    const typing = document.activeElement?.closest?.('#dr-file') && document.activeElement.matches('textarea, input')
    if (S.live[id] && !typing) renderFile({ keepScroll: true })
    else updateSrc()
  }
}

function updateSrc() {
  const el = $('#dr-src')
  if (el) el.innerHTML = srcHTML(P[S.sel])
}

// --- Events ------------------------------------------------------------------------------------
function onClick(event) {
  const t = event.target.closest('button, tr[data-pid], [data-open-file]')
  if (!t || !root.contains(t)) return
  const d = t.dataset
  if (d.open) return select(d.open)
  if (d.nav) return setView(d.nav)
  if (d.seg) {
    S.group = d.seg
    return renderGroups()
  }
  if (d.area) {
    S.area = S.area === d.area ? null : d.area
    return renderGroups()
  }
  if (d.msg) {
    S.msgSel = d.msg
    if (MESSAGES.find((x) => x.id === d.msg)?.bot) (S.msgs[d.msg] ??= { read: true, replies: [] }).read = true
    return renderView({ focus: '#dr-reply-t' })
  }
  if (d.sugg !== undefined) {
    const msg = MESSAGES.find((x) => x.id === S.msgSel)
    S.sugg[msg.id] = Number(d.sugg)
    S.draft[msg.id] = msg.sugg[Number(d.sugg)]
    $$('.dr-sugg button').forEach((b) => b.setAttribute('aria-pressed', String(b === t)))
    const area = $('#dr-reply-t')
    if (area) area.value = S.draft[msg.id]
    return
  }
  if (d.openFile) return select(d.openFile)
  if (d.pid && !event.target.closest('button')) return select(d.pid)
  switch (d.do) {
    case 'row':
      return doRow(d.id)
    case 'undo':
      return undo(d.id)
    case 'req':
      return sendRequest(d.id)
    case 'copy':
      return copyNote(d.id)
    case 'msg':
      return sendMessage(d.id)
    case 'reply':
      return sendReply(d.id)
    case 'batch':
      return doBatch()
    case 'view':
      return setView(d.view)
    case 'toast-undo': {
      const fn = toastUndo
      $('#dr-toast').classList.remove('is-on')
      toastUndo = null
      return fn?.()
    }
  }
}

function onKey(event) {
  const t = event.target
  const typing = t.matches('input, textarea')
  if (event.key === '/' && !typing) {
    event.preventDefault()
    $('#dr-q').focus()
    return
  }
  if (t.id === 'dr-q') {
    if (event.key === 'Escape') {
      t.value = ''
      S.q = ''
      if (S.view === 'pacientes') renderView()
    } else if (event.key === 'Enter') {
      const first = $('#dr-main tr[data-pid]')
      if (first) {
        event.preventDefault()
        select(first.dataset.pid, { focusRow: true })
      }
    }
    return
  }
  if (t.matches('.dr-open')) {
    const keys = { ArrowDown: 1, j: 1, ArrowUp: -1, k: -1, Home: -99, End: 99 }
    if (!(event.key in keys)) return
    event.preventDefault()
    const opens = $$('.dr-open')
    const i = opens.indexOf(t)
    const step = keys[event.key]
    const next = step === -99 ? 0 : step === 99 ? opens.length - 1 : Math.max(0, Math.min(opens.length - 1, i + step))
    if (next !== i) select(opens[next].dataset.open, { focusRow: true })
  }
  if (t.matches('tr[data-pid]') && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault()
    select(t.dataset.pid, { focusRow: true })
  }
}

function onInput(event) {
  const t = event.target
  if (t.id === 'dr-q') {
    S.q = t.value
    if (S.view !== 'pacientes') {
      S.view = 'pacientes'
      renderView()
      t.focus()
    } else {
      $('#dr-main').innerHTML = pacientesHTML()
    }
    renderNav()
    return
  }
  if (t.dataset.note) S.notes[t.dataset.note] = t.value
  if (t.dataset.draft) {
    S.draft[t.dataset.draft] = t.value
    delete S.sugg[t.dataset.draft]
    $$('.dr-sugg button').forEach((b) => b.setAttribute('aria-pressed', 'false'))
  }
}

function onChange(event) {
  const t = event.target
  if (t.dataset.req) {
    const p = P[t.dataset.req]
    const checked = (S.req[p.id] ??= p.req.map((x) => x.on))
    checked[Number(t.dataset.i)] = t.checked
    const n = checked.filter(Boolean).length
    const button = $(`[data-do="req"][data-id="${p.id}"]`)
    if (button) {
      button.disabled = !n
      if (!p.reqBtn) button.lastChild.textContent = `Send order (${n})`
    }
  }
}

// --- Startup -----------------------------------------------------------------------------------
export function initDoctor() {
  const host = document.getElementById('dr-app')
  if (!host || host.dataset.ready) return
  host.dataset.ready = '1'
  root = host
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
  const still = reduced || document.documentElement.classList.contains('static') || !('IntersectionObserver' in window)
  if (!still) host.classList.add('dr-anim')
  host.innerHTML = shellHTML()
  renderView()
  host.addEventListener('click', onClick)
  host.addEventListener('keydown', onKey)
  host.addEventListener('input', onInput)
  host.addEventListener('change', onChange)

  const enter = () => {
    host.classList.add('is-in')
    setTimeout(() => host.classList.add('is-settled'), 1600)
    ensureLive(S.sel)
  }
  if (still) {
    host.classList.add('is-in', 'is-settled')
    ensureLive(S.sel)
    return
  }
  // Enters when its top edge passes 85% of the screen (on mobile the window is very tall and a
  // proportional threshold would never be met).
  const seen = new IntersectionObserver(
    (entries) => {
      if (!entries[0].isIntersecting) return
      seen.disconnect()
      enter()
    },
    { threshold: 0, rootMargin: '0px 0px -15% 0px' },
  )
  seen.observe(host)
  // The model is queried a little before arriving, so the file is already computed.
  const near = new IntersectionObserver(
    (entries) => {
      if (!entries[0].isIntersecting) return
      near.disconnect()
      ensureLive(S.sel)
    },
    { rootMargin: '900px 0px' },
  )
  near.observe(host)
}

// --- Saved copy of the model (computed on 11/16/2026 with src/latenthealth; see the header) -----
// Model output per patient (compact form; see fromApi for the meaning of each field).
const MODEL = {
  julian: {"alb":{"status":"confirmada","label":"Confirmed","cat":"A2","p":[0.0136,0.9864,0.0001],"p2":0.9864,"median":63.3,"low":40.5,"high":98.1,"action":"Persistent A2 albuminuria: record CKD (category A2) and review kidney-protective treatment per guideline.","chronic":true,"resolve":null},"blood":{"egfr":[91.5,63.4,104.7,false,"estimated"],"hba1c":[5.8,5.3,6.5,false,"estimated"],"potassium":[4.0,3.4,4.5,false,"estimated"],"non_hdl":[137.9,92.7,204.1,false,"estimated"],"nt_probnp":[136.6,34.2,318.7,false,"estimated"]},"pG60":0.0519,"joint":[[0.0092,0.5082,0.0001],[0.004,0.4267,0.0001],[0.0004,0.0456,0.0001],[0.0001,0.0059,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.9868,"dm":"unlikely","pDm":0.0916,"hf":"to rule out","pBnp":0.5143,"pAf":0.0001,"pEf":null,"pNew":0.1387,"byTest":{"creatinina":0.0519,"glucosa":0.0916},"recs":[["Creatinine (eGFR)","Estimated P(eGFR < 60): 5%; it must be measured to stage CKD."],["Fasting capillary glucose (at the pharmacy or at home)","Estimated P(undiagnosed diabetes): 9%. A single glucose check almost always settles it without labs."],["NT-proBNP","Estimated P(NT-proBNP ≥ 125): 51%; if high, echocardiogram."],["Potasio","Before starting or uptitrating an ACE inhibitor/ARB or finerenone."],["Home blood pressure","Office blood pressure of 146 mmHg. A week of home monitoring with a validated cuff."],["Symptom questions","Shortness of breath on slopes and difficulty walking, answered from home: they sharpen the suspicion of heart failure before ordering NT-proBNP."]],"alerts":["Persistent albuminuria with no chronic kidney disease on record."],"hr":1.65,"cv":{"score":0.0697,"probs":[0.0,0.9941,0.0059],"rec":1,"cat":1,"pUp":0.0059,"approx":false},"row":{"group":"actuar","p":0.1387,"test":"glucosa","how":"one check at the pharmacy, or with their glucometer"},"belief":{"pts":[[1.02,0.0],[1.25,0.0],[1.53,0.0],[1.86,0.0],[2.28,0.0],[2.78,0.0],[3.4,0.0],[4.15,0.0],[5.07,0.0],[6.19,0.0],[7.56,0.0],[9.23,0.0],[11.28,0.0],[13.78,1e-05],[16.83,7e-05],[20.55,0.0004],[25.11,0.00201],[30.67,0.00767],[37.46,0.02175],[45.76,0.04551],[55.89,0.06961],[68.27,0.07679],[83.39,0.06011],[101.86,0.03293],[124.42,0.01251],[151.98,0.00329],[185.64,0.0006],[226.76,8e-05],[276.99,1e-05],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":63.9,"low":40.8,"high":98.7,"p2":0.9869},"trend":{"level":88.2,"low":79.2,"high":97.0,"slope":-1.13,"slopeLow":-3.17,"slopeHigh":0.85,"status":"estable","traj":[["2021-03-15",94.7,89.6,99.8],["2022-04-20",93.5,89.2,97.7],["2023-05-08",92.3,88.0,96.5],["2024-05-06",91.1,86.0,96.1]],"meas":[["2021-03-15",96.0],["2022-04-20",94.0],["2023-05-08",93.0],["2024-05-06",90.0]],"proj":[["2027-11-16",87.1,76.2,97.7],["2028-11-16",85.9,73.2,98.4],["2029-11-16",84.8,70.1,99.2],["2031-11-16",82.5,63.7,100.9]]},"bp":{"sbp":140.8,"dbp":86.6,"p":0.9999,"valid":true,"msg":"High home blood pressure: mean 141/87 mmHg (threshold 135/85).","n":24,"days":6,"byDay":[["2026-11-02",143,86],["2026-11-03",140,85],["2026-11-04",141,87],["2026-11-05",143,86],["2026-11-06",140,88],["2026-11-07",140,86],["2026-11-08",141,87]]},"pAfPrior":0.0056},
  manuel: {"alb":{"status":"descartada","label":"Ruled out","cat":"A1","p":[0.9979,0.0021,0.0001],"p2":0.0021,"median":10.2,"low":4.5,"high":15.9,"action":"No albuminuria. Repeat screening per guideline (yearly in diabetes).","chronic":false,"resolve":null},"blood":{"egfr":[71.0,71.0,71.0,true,"measured"],"hba1c":[5.7,5.2,6.4,false,"estimated"],"potassium":[4.1,3.7,4.7,false,"estimated"],"non_hdl":[133.0,93.4,181.7,false,"estimated"],"nt_probnp":[143.1,49.0,290.1,false,"estimated"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.9979,0.0021,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0021,"dm":"unlikely","pDm":0.0658,"hf":"to rule out","pBnp":0.6296,"pAf":0.729,"pEf":null,"pNew":0.0658,"byTest":{"glucosa":0.0658},"recs":[["Fasting capillary glucose (at the pharmacy or at home)","Estimated P(undiagnosed diabetes): 7%. A single glucose check almost always settles it without labs."],["NT-proBNP","Estimated P(NT-proBNP ≥ 125): 63%; if high, echocardiogram."],["ECG","P(atrial fibrillation) after home checks: 73%."],["Symptom questions","Shortness of breath on slopes and difficulty walking, answered from home: they sharpen the suspicion of heart failure before ordering NT-proBNP."]],"alerts":["Repeated irregular pulse at home (P(atrial fibrillation) = 73%)."],"hr":0.93,"cv":{"score":0.1362,"probs":[0.0,1.0,0.0],"rec":1,"cat":1,"pUp":0.0,"approx":false},"row":{"group":"actuar","p":0.0658,"test":"glucosa","how":"one check at the pharmacy, or with their glucometer"},"pAfPrior":0.0133,"belief":{"pts":[[1.02,0.0],[1.25,1e-05],[1.53,6e-05],[1.86,0.00036],[2.28,0.00163],[2.78,0.00511],[3.4,0.01069],[4.15,0.01544],[5.07,0.01741],[6.19,0.02074],[7.56,0.03341],[9.23,0.05638],[11.28,0.07074],[13.78,0.05736],[16.83,0.0297],[20.55,0.01047],[25.11,0.00283],[30.67,0.00069],[37.46,0.00018],[45.76,6e-05],[55.89,2e-05],[68.27,1e-05],[83.39,1e-05],[101.86,1e-05],[124.42,0.0],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":10.2,"low":4.5,"high":15.9,"p2":0.0021}},
  carmen: {"alb":{"status":"descartada","label":"Ruled out","cat":"A1","p":[0.9999,0.0001,0.0001],"p2":0.0001,"median":5.6,"low":3.9,"high":8.0,"action":"No albuminuria. Repeat screening per guideline (yearly in diabetes).","chronic":false,"resolve":null},"blood":{"egfr":[88.0,88.0,88.0,true,"measured"],"hba1c":[5.6,5.2,6.1,false,"estimated"],"potassium":[3.9,3.5,4.4,false,"estimated"],"non_hdl":[145.3,100.6,195.4,false,"estimated"],"nt_probnp":[63.2,29.1,189.5,false,"estimated"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.9999,0.0001,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0001,"dm":"unlikely","pDm":0.0261,"hf":"unlikely","pBnp":0.1645,"pAf":null,"pEf":null,"pNew":0.0261,"byTest":{"glucosa":0.0261},"recs":[["Fasting capillary glucose (at the pharmacy or at home)","Estimated P(undiagnosed diabetes): 3%. A single glucose check almost always settles it without labs."]],"alerts":["High home blood pressure: mean 149/91 mmHg (threshold 135/85). No hypertension on record."],"hr":0.66,"cv":{"score":0.0411,"probs":[1.0,0.0001,0.0],"rec":0,"cat":0,"pUp":0.0001,"approx":false},"bp":{"sbp":148.5,"dbp":91.3,"p":1.0,"valid":true,"msg":"High home blood pressure: mean 149/91 mmHg (threshold 135/85).","n":24,"days":6,"byDay":[["2026-11-05",154,91],["2026-11-06",147,92],["2026-11-07",150,92],["2026-11-08",148,90],["2026-11-09",148,92],["2026-11-10",150,91],["2026-11-11",149,90]]},"row":{"group":"actuar","p":0.0261,"test":"glucosa","how":"one check at the pharmacy, or with their glucometer"},"belief":{"pts":[[1.02,0.0],[1.25,0.0],[1.53,2e-05],[1.86,0.00017],[2.28,0.00114],[2.78,0.00525],[3.4,0.01768],[4.15,0.04697],[5.07,0.08769],[6.19,0.0937],[7.56,0.05342],[9.23,0.01922],[11.28,0.0058],[13.78,0.00163],[16.83,0.00044],[20.55,0.00013],[25.11,4e-05],[30.67,2e-05],[37.46,1e-05],[45.76,0.0],[55.89,0.0],[68.27,0.0],[83.39,0.0],[101.86,0.0],[124.42,0.0],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":5.6,"low":3.9,"high":8.0,"p2":0.0001}},
  rosa: {"alb":{"status":"sin_medir","label":"Not measured","cat":"A1","p":[0.7069,0.2197,0.0734],"p2":0.2931,"median":10.1,"low":3.2,"high":203.5,"action":"Order UACR on first morning urine. Probability of albuminuria before measuring: 29%.","chronic":false,"resolve":0.7596},"blood":{"egfr":[50.7,46.9,54.5,false,"trend from 5 lab sets"],"hba1c":[7.1,7.1,7.1,true,"measured"],"potassium":[4.0,3.5,4.7,false,"estimated"],"non_hdl":[130.3,83.7,180.9,false,"estimated"],"nt_probnp":[107.9,40.4,502.2,false,"estimated"]},"pG60":1.0,"joint":[[0.0,0.0,0.0],[0.0,0.0,0.0],[0.6899,0.213,0.0712],[0.017,0.0068,0.0022],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":1.0,"dm":"diagnosed","pDm":null,"hf":"to rule out","pBnp":0.4587,"pAf":null,"pEf":null,"pNew":0.3101,"byTest":{"orina":0.2931},"recs":[["UACR (first morning urine)","Order UACR on first morning urine. Probability of albuminuria before measuring: 29%."],["NT-proBNP","Estimated P(NT-proBNP ≥ 125): 46%; if high, echocardiogram."],["Potasio","Before starting or uptitrating an ACE inhibitor/ARB or finerenone."]],"alerts":["Rapid eGFR decline: -8.2 mL/min/1.73 m² per year."],"hr":1.41,"cv":{"score":0.088,"probs":[0.0,0.6899,0.3101],"rec":1,"cat":1,"pUp":0.3101,"approx":false},"trend":{"level":50.7,"low":46.9,"high":54.5,"slope":-8.18,"slopeLow":-10.08,"slopeHigh":-6.29,"status":"descenso_rapido","traj":[["2022-10-28",84.9,80.0,89.8],["2023-10-28",76.7,73.0,80.3],["2024-10-27",68.2,65.2,71.2],["2025-10-27",59.7,56.8,62.6],["2026-10-27",51.2,47.5,54.8]],"meas":[["2022-10-28",88],["2023-10-28",79],["2024-10-27",68],["2025-10-27",60],["2026-10-27",49]]},"row":{"group":"actuar","p":0.3101,"test":"orina","how":"home urine kit (app)"},"belief":{"pts":[[1.02,0.00023],[1.25,0.00039],[1.53,0.00077],[1.86,0.00201],[2.28,0.0062],[2.78,0.01572],[3.4,0.02675],[4.15,0.02973],[5.07,0.02429],[6.19,0.01931],[7.56,0.01815],[9.23,0.01818],[11.28,0.01738],[13.78,0.01555],[16.83,0.01322],[20.55,0.01097],[25.11,0.00921],[30.67,0.00807],[37.46,0.00747],[45.76,0.00723],[55.89,0.00716],[68.27,0.00713],[83.39,0.00706],[101.86,0.0069],[124.42,0.00665],[151.98,0.00631],[185.64,0.00589],[226.76,0.0054],[276.99,0.00488],[338.34,0.00434],[413.27,0.0038],[504.81,0.00327],[616.62,0.00276],[753.19,0.0023],[920.02,0.00189],[1123.79,0.00152],[1372.7,0.00121],[1676.73,0.00094],[2048.11,0.00072]],"median":10.6,"low":3.2,"high":214.1,"p2":0.3063}},
  ramon: {"alb":{"status":"sin_medir","label":"Not measured","cat":"A1","p":[0.9654,0.0273,0.0073],"p2":0.0346,"median":4.0,"low":2.6,"high":11.1,"action":"Order UACR on first morning urine. Probability of albuminuria before measuring: 3%.","chronic":false,"resolve":0.9528},"blood":{"egfr":[92.5,68.3,106.1,false,"estimated"],"hba1c":[6.2,5.7,7.6,false,"estimated with home glucose"],"potassium":[4.1,3.6,4.5,false,"estimated"],"non_hdl":[150.7,105.5,212.0,false,"estimated"],"nt_probnp":[41.9,16.0,119.6,false,"estimated"]},"pG60":0.0102,"joint":[[0.543,0.0085,0.0019],[0.4137,0.0175,0.0051],[0.0087,0.0012,0.0003],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0433,"dm":"possible","pDm":0.3743,"hf":"unlikely","pBnp":0.0932,"pAf":null,"pEf":null,"pNew":0.4014,"byTest":{"orina":0.0346,"creatinina":0.0102,"HbA1c":0.3743},"recs":[["UACR (first morning urine)","Order UACR on first morning urine. Probability of albuminuria before measuring: 3%."],["HbA1c","P(undiagnosed diabetes) with capillary glucose: 37%. Confirm with labs."],["Home blood pressure","Office blood pressure of 142 mmHg. A week of home monitoring with a validated cuff."]],"alerts":["Fasting glucose of 126 mg/dL or more on two different days, measured at home, no diabetes on record: confirm with HbA1c."],"hr":0.91,"cv":{"score":0.0968,"probs":[0.0,0.9997,0.0003],"rec":1,"cat":1,"pUp":0.0003,"approx":false},"row":{"group":"actuar","p":0.4014,"test":"HbA1c","how":"labs"},"belief":{"pts":[[1.02,4e-05],[1.25,0.00013],[1.53,0.0006],[1.86,0.00366],[2.28,0.01652],[2.78,0.04588],[3.4,0.07539],[4.15,0.0733],[5.07,0.04394],[6.19,0.01955],[7.56,0.01059],[9.23,0.0087],[11.28,0.00777],[13.78,0.00647],[16.83,0.00493],[20.55,0.00347],[25.11,0.00231],[30.67,0.00151],[37.46,0.00103],[45.76,0.00078],[55.89,0.00066],[68.27,0.00061],[83.39,0.00058],[101.86,0.00056],[124.42,0.00054],[151.98,0.00051],[185.64,0.00048],[226.76,0.00044],[276.99,0.00039],[338.34,0.00035],[413.27,0.0003],[504.81,0.00026],[616.62,0.00022],[753.19,0.00018],[920.02,0.00015],[1123.79,0.00012],[1372.7,0.0001],[1676.73,7e-05],[2048.11,6e-05]],"median":3.9,"low":2.6,"high":10.5,"p2":0.0285}},
  elena: {"alb":{"status":"sin_medir","label":"Not measured","cat":"A1","p":[0.9438,0.0439,0.0123],"p2":0.0562,"median":4.6,"low":2.9,"high":17.1,"action":"Order UACR on first morning urine. Probability of albuminuria before measuring: 6%.","chronic":false,"resolve":0.8977},"blood":{"egfr":[58.9,50.5,67.5,false,"capillary, at home"],"hba1c":[5.8,5.3,6.3,false,"estimated"],"potassium":[4.0,3.2,4.5,false,"estimated"],"non_hdl":[141.9,99.1,188.5,false,"estimated"],"nt_probnp":[170.5,48.4,427.0,false,"estimated"]},"pG60":0.5501,"joint":[[0.0,0.0,0.0],[0.4311,0.015,0.0038],[0.4844,0.0256,0.0075],[0.0283,0.0033,0.001],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.5689,"dm":"unlikely","pDm":0.0511,"hf":"to rule out","pBnp":0.6344,"pAf":null,"pEf":null,"pNew":0.5909,"byTest":{"orina":0.0562,"creatinina":0.5501,"glucosa":0.0511},"recs":[["UACR (first morning urine)","Order UACR on first morning urine. Probability of albuminuria before measuring: 6%."],["Creatinine (eGFR)","Estimated P(eGFR < 60): 55%; it must be measured to stage CKD. There is already a finger-prick result; it should be confirmed in the lab."],["Fasting capillary glucose (at the pharmacy or at home)","Estimated P(undiagnosed diabetes): 5%. A single glucose check almost always settles it without labs."],["NT-proBNP","Estimated P(NT-proBNP ≥ 125): 63%; if high, echocardiogram."],["Potasio","Before starting or uptitrating an ACE inhibitor/ARB or finerenone."],["Home blood pressure","Office blood pressure of 142 mmHg. A week of home monitoring with a validated cuff."],["Symptom questions","Shortness of breath on slopes and difficulty walking, answered from home: they sharpen the suspicion of heart failure before ordering NT-proBNP."]],"alerts":[],"hr":1.01,"cv":{"score":0.0881,"probs":[0.0,0.9882,0.0118],"rec":1,"cat":1,"pUp":0.0118,"approx":false},"row":{"group":"medir","p":0.5909,"test":"creatinina","how":"home finger prick or labs"},"belief":{"pts":[[1.02,5e-05],[1.25,0.00013],[1.53,0.0004],[1.86,0.00187],[2.28,0.00885],[2.78,0.0287],[3.4,0.05684],[4.15,0.06746],[5.07,0.04979],[6.19,0.02703],[7.56,0.01639],[9.23,0.01389],[11.28,0.01279],[13.78,0.01102],[16.83,0.00869],[20.55,0.00632],[25.11,0.00431],[30.67,0.00286],[37.46,0.00195],[45.76,0.00145],[55.89,0.00121],[68.27,0.0011],[83.39,0.00105],[101.86,0.00102],[124.42,0.00098],[151.98,0.00093],[185.64,0.00087],[226.76,0.00081],[276.99,0.00073],[338.34,0.00065],[413.27,0.00057],[504.81,0.0005],[616.62,0.00042],[753.19,0.00035],[920.02,0.00029],[1123.79,0.00023],[1372.7,0.00019],[1676.73,0.00015],[2048.11,0.00011]],"median":4.6,"low":2.9,"high":16.6,"p2":0.0531}},
  marta: {"alb":{"status":"dudosa","label":"Doubtful","cat":"A1","p":[0.6612,0.3388,0.0001],"p2":0.3388,"median":24.4,"low":13.6,"high":43.0,"action":"Repeat on first morning urine, avoiding intense exercise, fever or urinary infection. Probability that it settles the doubt: 27% (with a random sample, 22%).","chronic":false,"resolve":0.2655},"blood":{"egfr":[108.5,82.0,117.3,false,"estimated"],"hba1c":[7.4,7.4,7.4,true,"measured"],"potassium":[4.0,3.6,4.4,false,"estimated"],"non_hdl":[135.0,84.7,191.9,false,"estimated"],"nt_probnp":[36.7,8.4,114.6,false,"estimated"]},"pG60":0.0026,"joint":[[0.5529,0.2648,0.0001],[0.1072,0.0725,0.0001],[0.0011,0.0015,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.3399,"dm":"diagnosed","pDm":null,"hf":"unlikely","pBnp":0.0782,"pAf":null,"pEf":null,"pNew":0.3399,"byTest":{"orina":0.3388,"creatinina":0.0026},"recs":[["UACR (first morning urine)","Repeat on first morning urine, avoiding intense exercise, fever or urinary infection. Probability that it settles the doubt: 27% (with a random sample, 22%)."]],"alerts":[],"hr":0.81,"cv":{"score":0.0302,"probs":[0.0,0.9985,0.0015],"rec":1,"cat":1,"pUp":0.0015,"approx":false},"row":{"group":"medir","p":0.3399,"test":"orina","how":"home urine kit (app)"},"belief":{"pts":[[1.02,0.0],[1.25,0.0],[1.53,0.0],[1.86,0.0],[2.28,0.0],[2.78,4e-05],[3.4,0.0002],[4.15,0.00065],[5.07,0.00134],[6.19,0.00197],[7.56,0.00279],[9.23,0.00532],[11.28,0.01176],[13.78,0.02373],[16.83,0.03987],[20.55,0.05387],[25.11,0.05785],[30.67,0.0499],[37.46,0.03583],[45.76,0.02262],[55.89,0.01315],[68.27,0.00705],[83.39,0.00336],[101.86,0.00138],[124.42,0.00048],[151.98,0.00014],[185.64,4e-05],[226.76,1e-05],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":24.4,"low":13.4,"high":46.1,"p2":0.3492}},
  pilar: {"alb":{"status":"dudosa","label":"Doubtful","cat":"A1","p":[0.8768,0.1232,0.0001],"p2":0.1232,"median":18.5,"low":9.6,"high":30.6,"action":"Repeat on first morning urine, avoiding intense exercise, fever or urinary infection. Probability that it settles the doubt: 57% (with a random sample, 52%).","chronic":false,"resolve":0.5747},"blood":{"egfr":[88.0,88.0,88.0,true,"measured"],"hba1c":[5.6,5.1,6.4,false,"estimated"],"potassium":[4.0,3.5,4.4,false,"estimated"],"non_hdl":[135.2,90.2,188.2,false,"estimated"],"nt_probnp":[62.7,25.1,155.0,false,"estimated"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.8768,0.1232,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.1232,"dm":"unlikely","pDm":0.0308,"hf":"unlikely","pBnp":0.1716,"pAf":null,"pEf":null,"pNew":0.1502,"byTest":{"orina":0.1232,"glucosa":0.0308},"recs":[["UACR (first morning urine)","Repeat on first morning urine, avoiding intense exercise, fever or urinary infection. Probability that it settles the doubt: 57% (with a random sample, 52%)."],["Fasting capillary glucose (at the pharmacy or at home)","Estimated P(undiagnosed diabetes): 3%. A single glucose check almost always settles it without labs."]],"alerts":[],"hr":0.53,"cv":{"score":0.0273,"probs":[1.0,0.0001,0.0],"rec":0,"cat":0,"pUp":0.0001,"approx":false},"row":{"group":"medir","p":0.1502,"test":"orina","how":"home urine kit (app)"},"belief":{"pts":[[1.02,0.0],[1.25,0.0],[1.53,0.0],[1.86,0.0],[2.28,2e-05],[2.78,0.00017],[3.4,0.00088],[4.15,0.00278],[5.07,0.00546],[6.19,0.00721],[7.56,0.00797],[9.23,0.01161],[11.28,0.02323],[13.78,0.04276],[16.83,0.06099],[20.55,0.0652],[25.11,0.05205],[30.67,0.03123],[37.46,0.01432],[45.76,0.00522],[55.89,0.00162],[68.27,0.00046],[83.39,0.00012],[101.86,3e-05],[124.42,1e-05],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":18.5,"low":9.6,"high":30.6,"p2":0.1232}},
  antonio: {"alb":{"status":"sin_medir","label":"Not measured","cat":"A1","p":[0.9133,0.0675,0.0192],"p2":0.0867,"median":4.9,"low":2.9,"high":24.2,"action":"Order UACR on first morning urine. Probability of albuminuria before measuring: 9%.","chronic":false,"resolve":0.8994},"blood":{"egfr":[75.0,51.3,89.5,false,"estimated"],"hba1c":[5.8,5.2,6.3,false,"estimated"],"potassium":[4.2,3.7,4.7,false,"estimated"],"non_hdl":[133.9,92.4,180.2,false,"estimated"],"nt_probnp":[199.9,88.3,3035.6,false,"estimated"]},"pG60":0.1557,"joint":[[0.0806,0.0026,0.0005],[0.7106,0.0388,0.0112],[0.0922,0.0151,0.0046],[0.023,0.0072,0.002],[0.0069,0.0038,0.001],[0.0,0.0,0.0]],"pCkd":0.2088,"dm":"unlikely","pDm":0.0341,"hf":"to rule out","pBnp":0.8258,"pAf":null,"pEf":null,"pNew":0.2358,"byTest":{"orina":0.0867,"creatinina":0.1557,"lípidos":0.0,"glucosa":0.0341},"recs":[["UACR (first morning urine)","Order UACR on first morning urine. Probability of albuminuria before measuring: 9%."],["Creatinine (eGFR)","Estimated P(eGFR < 60): 16%; it must be measured to stage CKD."],["Fasting capillary glucose (at the pharmacy or at home)","Estimated P(undiagnosed diabetes): 3%. A single glucose check almost always settles it without labs."],["NT-proBNP","Estimated P(NT-proBNP ≥ 125): 83%; if high, echocardiogram."],["Home blood pressure","Office blood pressure of 150 mmHg. A week of home monitoring with a validated cuff."],["Symptom questions","Shortness of breath on slopes and difficulty walking, answered from home: they sharpen the suspicion of heart failure before ordering NT-proBNP."]],"alerts":[],"hr":0.94,"cv":{"score":0.192,"probs":[0.0,0.0195,0.9805],"rec":2,"cat":2,"pUp":0.0,"approx":true},"row":{"group":"medir","p":0.2358,"test":"creatinina","how":"home finger prick or labs"},"belief":{"pts":[[1.02,3e-05],[1.25,6e-05],[1.53,0.00018],[1.86,0.00066],[2.28,0.00335],[2.78,0.01417],[3.4,0.03884],[4.15,0.06424],[5.07,0.06418],[6.19,0.0416],[7.56,0.02267],[9.23,0.01595],[11.28,0.01443],[13.78,0.01304],[16.83,0.01081],[20.55,0.00816],[25.11,0.00565],[30.67,0.00364],[37.46,0.00224],[45.76,0.0014],[55.89,0.00095],[68.27,0.00074],[83.39,0.00065],[101.86,0.00061],[124.42,0.00058],[151.98,0.00056],[185.64,0.00053],[226.76,0.00049],[276.99,0.00045],[338.34,0.00041],[413.27,0.00036],[504.81,0.00032],[616.62,0.00027],[753.19,0.00023],[920.02,0.00019],[1123.79,0.00016],[1372.7,0.00013],[1676.73,0.0001],[2048.11,8e-05]],"median":5.2,"low":3.3,"high":16.8,"p2":0.0419}},
  francisco: {"alb":{"status":"descartada","label":"Ruled out","cat":"A1","p":[0.9997,0.0003,0.0001],"p2":0.0003,"median":7.2,"low":3.7,"high":11.8,"action":"No albuminuria. Repeat screening per guideline (yearly in diabetes).","chronic":false,"resolve":null},"blood":{"egfr":[78.0,78.0,78.0,true,"measured"],"hba1c":[5.8,5.3,6.4,false,"estimated"],"potassium":[4.1,3.5,4.5,false,"estimated"],"non_hdl":[135.3,90.3,188.4,false,"estimated"],"nt_probnp":[56.2,18.4,229.5,false,"estimated"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.9997,0.0003,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0003,"dm":"unlikely","pDm":0.0704,"hf":"unlikely","pBnp":0.1712,"pAf":null,"pEf":null,"pNew":0.0704,"byTest":{"glucosa":0.0704},"recs":[["Fasting capillary glucose (at the pharmacy or at home)","Estimated P(undiagnosed diabetes): 7%. A single glucose check almost always settles it without labs."]],"alerts":[],"hr":0.37,"cv":{"score":0.0784,"probs":[0.0,1.0,0.0],"rec":1,"cat":1,"pUp":0.0,"approx":false},"row":{"group":"medir","p":0.0704,"test":"glucosa","how":"one check at the pharmacy, or with their glucometer"},"belief":{"pts":[[1.02,0.0],[1.25,1e-05],[1.53,0.00011],[1.86,0.00067],[2.28,0.00297],[2.78,0.00894],[3.4,0.01863],[4.15,0.02929],[5.07,0.03874],[6.19,0.04816],[7.56,0.05881],[9.23,0.05955],[11.28,0.04108],[13.78,0.01851],[16.83,0.00587],[20.55,0.00149],[25.11,0.00035],[30.67,9e-05],[37.46,3e-05],[45.76,1e-05],[55.89,1e-05],[68.27,0.0],[83.39,0.0],[101.86,0.0],[124.42,0.0],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":7.2,"low":3.7,"high":11.8,"p2":0.0003}},
  dolores: {"alb":{"status":"sin_medir","label":"Not measured","cat":"A1","p":[0.8217,0.1336,0.0447],"p2":0.1783,"median":7.9,"low":3.5,"high":93.0,"action":"Order UACR on first morning urine. Probability of albuminuria before measuring: 18%.","chronic":false,"resolve":0.7957},"blood":{"egfr":[66.0,66.0,66.0,true,"measured"],"hba1c":[7.6,7.6,7.6,true,"measured"],"potassium":[4.0,3.4,4.5,false,"estimated"],"non_hdl":[131.6,83.2,185.2,false,"estimated"],"nt_probnp":[103.1,29.6,428.7,false,"estimated"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.8217,0.1336,0.0447],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.1783,"dm":"diagnosed","pDm":null,"hf":"to rule out","pBnp":0.4277,"pAf":null,"pEf":null,"pNew":0.1783,"byTest":{"orina":0.1783},"recs":[["UACR (first morning urine)","Order UACR on first morning urine. Probability of albuminuria before measuring: 18%."],["NT-proBNP","Estimated P(NT-proBNP ≥ 125): 43%; if high, echocardiogram."],["Symptom questions","Shortness of breath on slopes and difficulty walking, answered from home: they sharpen the suspicion of heart failure before ordering NT-proBNP."]],"alerts":[],"hr":0.71,"cv":{"score":0.0956,"probs":[0.0,0.9553,0.0447],"rec":1,"cat":1,"pUp":0.0447,"approx":false},"row":{"group":"medir","p":0.1783,"test":"orina","how":"home urine kit (app)"},"belief":{"pts":[[1.02,0.0001],[1.25,0.00019],[1.53,0.00039],[1.86,0.00099],[2.28,0.00334],[2.78,0.011],[3.4,0.02594],[4.15,0.03915],[5.07,0.03854],[6.19,0.02902],[7.56,0.02287],[9.23,0.02158],[11.28,0.02102],[13.78,0.01915],[16.83,0.01608],[20.55,0.01257],[25.11,0.00938],[30.67,0.00693],[37.46,0.00532],[45.76,0.00441],[55.89,0.00397],[68.27,0.00378],[83.39,0.00369],[101.86,0.00362],[124.42,0.00352],[151.98,0.00337],[185.64,0.00318],[226.76,0.00296],[276.99,0.0027],[338.34,0.00243],[413.27,0.00215],[504.81,0.00187],[616.62,0.0016],[753.19,0.00135],[920.02,0.00112],[1123.79,0.00091],[1372.7,0.00073],[1676.73,0.00058],[2048.11,0.00045]],"median":7.9,"low":3.5,"high":93.0,"p2":0.1783}},
  andres: {"alb":{"status":"descartada","label":"Ruled out","cat":"A1","p":[0.9933,0.0066,0.0001],"p2":0.0067,"median":12.4,"low":4.6,"high":19.1,"action":"No albuminuria. Repeat screening per guideline (yearly in diabetes).","chronic":false,"resolve":null},"blood":{"egfr":[74.0,74.0,74.0,true,"measured"],"hba1c":[5.7,5.3,6.4,false,"estimated"],"potassium":[4.1,3.6,4.6,false,"estimated"],"non_hdl":[128.4,86.7,181.1,false,"estimated"],"nt_probnp":[59.0,32.6,206.1,false,"estimated"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.9933,0.0066,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0067,"dm":"unlikely","pDm":0.0594,"hf":"to rule out","pBnp":0.2402,"pAf":null,"pEf":0.0809,"pNew":0.1354,"byTest":{"glucosa":0.0594,"ecocardiograma":0.0809},"recs":[["Fasting capillary glucose (at the pharmacy or at home)","Estimated P(undiagnosed diabetes): 6%. A single glucose check almost always settles it without labs."],["Ecocardiograma","P(ejection fraction ≤ 40%) after the home heart recording: 8%. Order NT-proBNP first if there is a waiting list: if high, the echocardiogram is priority."]],"alerts":[],"hr":0.96,"cv":{"score":0.0835,"probs":[0.0,1.0,0.0],"rec":1,"cat":1,"pUp":0.0,"approx":false},"row":{"group":"medir","p":0.1354,"test":"ecocardiograma","how":"cardiology or pocket ultrasound at the center"},"belief":{"pts":[[1.02,0.0],[1.25,1e-05],[1.53,5e-05],[1.86,0.00034],[2.28,0.00161],[2.78,0.00507],[3.4,0.01036],[4.15,0.0139],[5.07,0.01329],[6.19,0.01198],[7.56,0.01637],[9.23,0.03228],[11.28,0.05816],[13.78,0.07288],[16.83,0.05697],[20.55,0.0277],[25.11,0.00911],[30.67,0.00236],[37.46,0.00059],[45.76,0.00017],[55.89,6e-05],[68.27,3e-05],[83.39,2e-05],[101.86,1e-05],[124.42,1e-05],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":12.4,"low":4.6,"high":19.1,"p2":0.0067}},
}

// Live request bodies: the same data the copy was computed with.
const LIVE = {
  julian: {"assess":{"age":62,"female":false,"bmi":29.5,"waist":104,"sbp":146,"dbp":88,"hypertension":true,"bp_meds":true,"high_cholesterol":true,"cholesterol_meds":true,"smoker_ever":true,"measured":{"total_cholesterol":205,"hdl":46},"urine_samples":[{"kind":"tira","date":"2026-07-14","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-07-15","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-07-16","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-02","albumin_mg_l":80,"creatinine_mg_dl":100}],"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":62,"female":false,"diabetes":false},"samples":[{"kind":"tira","date":"2026-07-14","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-07-15","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-07-16","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-02","albumin_mg_l":80,"creatinine_mg_dl":100}],"as_of":"2026-11-16"},"trend":{"age":62,"female":false,"diabetes":false,"p_a2":0.9864,"p_a3":0.0001,"measurements":[{"date":"2021-03-15","egfr":96},{"date":"2022-04-20","egfr":94},{"date":"2023-05-08","egfr":93},{"date":"2024-05-06","egfr":90}],"as_of":"2026-11-16"}},
  marta: {"assess":{"age":47,"female":true,"bmi":31.0,"waist":99,"sbp":128,"dbp":80,"diabetes":true,"diabetes_pills":true,"measured":{"hba1c":7.4,"total_cholesterol":190,"hdl":52},"urine_samples":[{"kind":"tira","date":"2026-11-13","albumin_mg_l":30,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-14","albumin_mg_l":30,"creatinine_mg_dl":50}],"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":47,"female":true,"diabetes":true},"samples":[{"kind":"tira","date":"2026-11-13","albumin_mg_l":30,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-14","albumin_mg_l":30,"creatinine_mg_dl":50}],"as_of":"2026-11-16"}},
  pilar: {"assess":{"age":58,"female":true,"bmi":26.0,"waist":86,"sbp":128,"dbp":79,"measured":{"egfr":88,"total_cholesterol":212,"hdl":61},"urine_samples":[{"kind":"tira","date":"2026-11-12","albumin_mg_l":30,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-13","albumin_mg_l":30,"creatinine_mg_dl":100}],"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":58,"female":true,"diabetes":false,"egfr":88},"samples":[{"kind":"tira","date":"2026-11-12","albumin_mg_l":30,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-13","albumin_mg_l":30,"creatinine_mg_dl":100}],"as_of":"2026-11-16"}},
  antonio: {"assess":{"age":81,"female":false,"bmi":27.5,"sbp":150,"dbp":72,"hypertension":true,"bp_meds":true,"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":81,"female":false,"diabetes":false},"samples":[],"as_of":"2026-11-16"}},
  francisco: {"assess":{"age":66,"female":false,"bmi":31.0,"waist":108,"sbp":134,"dbp":82,"hypertension":true,"bp_meds":true,"high_cholesterol":true,"cholesterol_meds":true,"smoker_ever":true,"measured":{"egfr":78,"total_cholesterol":196,"hdl":41},"urine_samples":[{"kind":"laboratorio","date":"2026-09-22","uacr":9.0,"sample_type":"first_morning","creatinine_mg_dl":110}],"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":66,"female":false,"diabetes":false,"egfr":78},"samples":[{"kind":"laboratorio","date":"2026-09-22","uacr":9.0,"sample_type":"first_morning","creatinine_mg_dl":110}],"as_of":"2026-11-16"}},
  dolores: {"assess":{"age":69,"female":true,"bmi":30.0,"waist":98,"sbp":136,"dbp":80,"diabetes":true,"diabetes_pills":true,"hypertension":true,"bp_meds":true,"measured":{"egfr":66,"hba1c":7.6,"total_cholesterol":190,"hdl":50},"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":69,"female":true,"diabetes":true,"egfr":66},"samples":[],"as_of":"2026-11-16"}},
}
