// Panel del médico (sección #medico): la consulta de LatentHealth como una aplicación de escritorio.
//
// - Hoy: la lista de trabajo del cupo (Actuar, Medir y Sin pendientes), con una acción de un clic
//   por fila, y la ficha del paciente: lo que cree el modelo (rejilla KDIGO, albuminuria, tendencia
//   del FG), las pruebas de casa, el riesgo cardiovascular y lo que ya viene preparado (petición,
//   nota con código CIE-10-ES, sugerencias de la guía y mensaje al paciente).
// - Pacientes, Mensajes (el de Pilar), Kits e Indicadores del cupo.
//
// Los pacientes son inventados. Sus números los calculó el modelo real (src/latenthealth) y van
// copiados al final de este archivo. Las fichas que la API puede representar entera se recalculan
// en vivo con POST /api/model/assess (Julián, además, con /albuminuria y /egfr-trend); si el
// servidor no responde, se queda la copia. Las cifras del cupo (kits, cobertura, embudo) son de
// ejemplo y así se rotulan. Es apoyo a la decisión: nada de aquí pauta un tratamiento.

const NB = ' '
const TODAY = '2026-11-16'
const MEDIR_TOTAL = 41
const SIN_PENDIENTES = 1454

// --- Formato español ---------------------------------------------------------------------------
const formats = new Map()
function num(value, decimals = 0) {
  if (!Number.isFinite(value)) return '—'
  if (!formats.has(decimals)) {
    formats.set(decimals, new Intl.NumberFormat('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: 'always' }))
  }
  return formats.get(decimals).format(value).replace('-', '−')
}
/** Probabilidad 0-1 -> «61 %». Nunca enseña 0 % ni 100 % si no lo son. */
function pct(p) {
  if (p == null || !Number.isFinite(p)) return '—'
  const v = Math.min(1, Math.max(0, p)) * 100
  if (v > 0 && v < 1) return `<${NB}1${NB}%`
  if (v > 99 && v < 100) return `>${NB}99${NB}%`
  return `${num(v)}${NB}%`
}
const pct1 = (p) => `${num(p * 100, 1)}${NB}%`
const range = (a, b, d = 0) => `${num(a, d)}–${num(b, d)}`
/** Los textos del modelo traen «4%»; en España va con espacio. */
const fixPct = (text) => String(text ?? '').replace(/(\d)%/g, `$1${NB}%`).replace(/(^|[\s(])-(\d)/g, '$1−$2')
const esc = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const val = (x, m) => (typeof x === 'function' ? x(m) : x)
const MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
const days = (iso) => Date.parse(`${iso}T00:00:00Z`) / 86_400_000

// --- Iconos: rejilla de 24, trazo de 1,75 y currentColor ---------------------------------------
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

// --- La carta de colores de la tira ------------------------------------------------------------
const ALB = { 10: 'var(--a10)', 30: 'var(--a30)', 80: 'var(--a80)', 150: 'var(--a150)' }
const CRE = { 10: 'var(--c10)', 50: 'var(--c50)', 100: 'var(--c100)', 200: 'var(--c200)', 300: 'var(--c300)' }
const swatch = (a, c) =>
  `<span class="dr-swatch" role="img" aria-label="Tira: albúmina ${a} mg/l, creatinina ${c} mg/dl" title="Albúmina ${a} mg/l · creatinina ${c} mg/dl"><i style="background:${ALB[a]}"></i><i style="background:${CRE[c]}"></i></span>`

// Estados de la albuminuria: color, forma y texto (los de la ficha «La tira»).
const STATE_ICON = {
  sin_medir: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2"/>',
  descartada: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2"/>',
  dudosa: '<path d="M1 1h12v12H1z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M13 1v12H1z" fill="currentColor"/>',
  pendiente_cronicidad: '<path d="M0 0h14v14H0z" fill="currentColor"/>',
  confirmada: '<path d="M0 0h14v14H0z" fill="currentColor"/><path d="M3 7.4l2.8 2.8L11 4.2" fill="none" stroke="#0b7774" stroke-width="2"/>',
}
const stateChip = (status, label) =>
  `<span class="dr-state dr-st-${status}"><svg viewBox="0 0 14 14" aria-hidden="true">${STATE_ICON[status] ?? ''}</svg>${esc(label)}</span>`

// --- Qué hace cada acción de un clic -----------------------------------------------------------
const ACTIONS = {
  registrar: { label: 'Registrar diagnóstico', icon: 'clipcheck', done: 'Diagnóstico registrado' },
  analitica: { label: 'Pedir analítica', icon: 'flask', done: 'Analítica pedida' },
  kit: { label: 'Enviar kit', icon: 'box', done: 'Kit enviado' },
  citar: { label: 'Citar', icon: 'calplus', done: 'Citado' },
  farmacia: { label: 'Avisar a la farmacia', icon: 'cross', done: 'Farmacia avisada' },
  recordar: { label: 'Recordar', icon: 'bell', done: 'Recordatorio enviado' },
  responder: { label: 'Responder', icon: 'reply', done: 'Respondido' },
}
const GROUPS = {
  act: ['Actuar', 'Hallazgos claros que no constan en la historia', 'alert'],
  med: ['Medir', 'Probabilidad de un hallazgo nuevo y la prueba que más aporta', 'flask'],
  ok: ['Sin pendientes', 'Bien estudiados: no ocupan sitio', 'check'],
}
const AREAS = [
  ['rinon', 'Riñón', 'drop'],
  ['tension', 'Tensión', 'gauge'],
  ['corazon', 'Ritmo y corazón', 'pulse'],
  ['glucosa', 'Glucosa', 'glu'],
  ['msg', 'Con mensaje', 'msg'],
]
const TEST_NAMES = {
  orina: 'Orina (cociente albúmina/creatinina)',
  creatinina: 'Creatinina (FG)',
  glucosa: 'Glucosa en la farmacia',
  HbA1c: 'HbA1c',
  'lípidos': 'Colesterol total y HDL',
  ecocardiograma: 'Ecocardiograma',
}

// --- Los pacientes de la lista (inventados) ----------------------------------------------------
// Los textos que llevan números son funciones del resultado del modelo (m): así cuadran con lo que
// devuelva la API en vivo.
const PATIENTS = [
  {
    id: 'julian',
    group: 'act',
    name: 'Julián Herrero Sanz',
    short: 'Julián Herrero',
    first: 'Julián',
    ini: 'JH',
    age: 62,
    sex: 'H',
    cip: '4821',
    areas: ['rinon', 'tension'],
    channel: 'Kit por la app · reloj',
    consta: ['Hipertensión arterial', 'Dislipemia', 'Exfumador'],
    meds: 'antihipertensivo y estatina',
    why: 'Albuminuria repetida en casa, sin enfermedad renal registrada',
    chips: [
      ['kid', 'drop', 'Albuminuria repetida en casa'],
      ['bp', 'gauge', (m) => `TA en casa ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)}`],
      ['watch', 'watch', 'Reloj: ritmo regular'],
    ],
    action: 'registrar',
    doneLabel: 'Registrado · I12.9 + N18.9',
    toast: 'Enfermedad renal registrada en la historia de Julián: I12.9 y N18.9.',
    last: 'Tira alta el 02/11',
    bpAlert: true,
    ctx: [
      'Cuatro tiras altas: tres en julio y una el 2 de noviembre, más de tres meses después. Cumple la cronicidad.',
      'Riesgo cardiovascular alto, ya constaba. Lo nuevo es el riñón.',
    ],
    quote: true,
    samples: [
      ['tira', 80, '2026-07-14'],
      ['tira', 80, '2026-07-15'],
      ['tira', 80, '2026-07-16'],
      ['tira', 80, '2026-11-02'],
    ],
    albNote: 'Lo que cree el filtro sobre su cociente verdadero tras las 4 tiras. Cuadrados: tiras.',
    trendNote: 'Sin creatinina desde mayo de 2024: la banda se abre porque el dato envejece.',
    tl: [
      { d: '9 nov', icon: 'watch', t: 'ECG de 30 s con el reloj', meta: 'ritmo sinusal', ecg: 'regular', sub: (m) => `Y 14 comprobaciones del pulso del 1 al 14 de noviembre, todas regulares: P(fibrilación auricular) ${pct(m.pAf)}.` },
      { d: '2-8 nov', icon: 'gauge', t: 'Semana de tensión', meta: 'manguito prestado', bp: true, sub: (m) => `${fixPct(m.bp.msg)} ${m.bp.n} lecturas en ${m.bp.days} días; el primero no cuenta.` },
      { d: '2 nov', icon: 'strip', t: 'Tira de repetición', meta: 'leída con el móvil', hot: true, swatches: [[80, 100]], sub: 'Más de tres meses después de las de julio: cumple la cronicidad.', said: 'Tu centro de salud te llamará para darte cita.' },
      { d: '12 oct', icon: 'box', t: 'Kit de repetición enviado', sub: 'Lo mandó el sistema al cumplirse los tres meses.' },
      { d: '14-16 jul', icon: 'strip', t: 'Tres tiras con el móvil', swatches: [[80, 100], [80, 100], [80, 100]], pseq: [0.04, 0.62, 0.92, 0.98], sub: 'P(albuminuria) antes y después de cada tira:', said: 'Hemos visto albúmina en la orina. Repetiremos la prueba pasados tres meses.' },
      { d: '10 jul', icon: 'box', t: 'Kit enviado', sub: 'Hipertenso sin cociente albúmina/creatinina en la historia.' },
      { d: 'may 2024', icon: 'flask', t: 'Última analítica: FG 90', meta: 'laboratorio', sub: 'Con creatinina, pero sin cociente albúmina/creatinina, como las tres anteriores.' },
    ],
    cvExtra: 'La albuminuria no la sube: ya era alto por el SCORE2.',
    req: [
      { on: true, t: 'Cociente albúmina/creatinina en orina', d: 'Primera orina de la mañana. Cuantifica la A2 que han visto las tiras.' },
      { on: true, t: 'Creatinina sérica y FG (CKD-EPI)', d: (m) => `Para el estadio G: P(FG < 60) ${pct(m.pG60)}. Último FG: 90, en mayo de 2024.` },
      { on: true, t: 'Potasio', d: 'Antes de iniciar o subir un IECA, un ARA-II o finerenona.' },
      { on: true, t: 'NT-proBNP', d: (m) => `P(≥ 125 pg/ml) estimada ${pct(m.pBnp)}; si sale alto, ecocardiograma.` },
      { on: false, t: 'HbA1c', d: (m) => `P(diabetes oculta) ${pct(m.pDm)}: primero, una glucosa en la farmacia.` },
    ],
    note: (m) =>
      `Cribado de albuminuria en casa (kit LatentHealth): 4 tiras leídas con el móvil, altas en julio (3) y el 02/11/2026, separadas más de 3 meses. Cociente estimado ${num(m.alb.median)} mg/g (${range(m.alb.low, m.alb.high)}), categoría A2 (P ${pct(m.alb.p[1])}). Último FG: 90 (05/2024); estimado hoy ${m.trend ? `${num(m.trend.level)} (${range(m.trend.low, m.trend.high)})` : 'sin medir'}. TA en casa ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)} mmHg (límite 135/85). Ritmo regular en 14 comprobaciones del reloj.\n` +
      `Juicio: albuminuria persistente A2 en paciente hipertenso, sin ERC registrada.\n` +
      `Plan: CAC y creatinina en el laboratorio, potasio y NT-proBNP. Revisar control tensional y nefroprotección según la guía.`,
    codesWhen: 'Códigos sugeridos (CIE-10-ES)',
    codes: [
      ['I12.9', 'Enfermedad renal crónica hipertensiva, estadio 1 a 4 o no especificado'],
      ['N18.9', 'Enfermedad renal crónica, no especificada (estadio G pendiente del FG)'],
    ],
    guide: [
      ['A valorar', 'Si su antihipertensivo no es un IECA ni un ARA-II, valorar cambiarlo: ERC con albuminuria A2 e hipertensión, sin diabetes.', 'KDIGO 2024 · rec. 3.6.2 (2C)'],
      ['A valorar', 'Tensión no controlada en casa. Objetivo en consulta: sistólica de 120 a 129 mmHg si la tolera.', 'ESC 2024 · hipertensión'],
      ['Más adelante', 'iSGLT2: la guía los recomienda con CAC de 200 mg/g o más, FG de 20 a 45 o insuficiencia cardíaca. Hoy no se cumple; revisar con la analítica y el NT-proBNP.', 'KDIGO 2024 · rec. 3.7.2 y 3.7.3'],
    ],
    msg: 'Hola, Julián. Las tiras de casa han encontrado albúmina en la orina en julio y en noviembre. Te he pedido una analítica para confirmarlo y ver cómo está el riñón: elige el día en la app. Después lo vemos en consulta con calma.',
  },
  {
    id: 'manuel',
    group: 'act',
    name: 'Manuel Castro Vidal',
    short: 'Manuel Castro',
    first: 'Manuel',
    ini: 'MC',
    age: 77,
    sex: 'H',
    cip: '1907',
    areas: ['corazon'],
    channel: 'App · reloj con ECG',
    consta: ['Hipertensión arterial'],
    meds: 'antihipertensivo',
    why: (m) => `Pulso irregular dos días seguidos: P(fibrilación auricular) ${pct(m.pAf)}`,
    chips: [
      ['ecg', 'pulse', 'Pulso irregular 2 días'],
      ['watch', 'watch', 'ECG del reloj'],
    ],
    action: 'citar',
    doneLabel: 'Citado · mañana 9:40',
    toast: 'Cita para Manuel: mañana a las 9:40, ECG con enfermería.',
    last: 'Pulso irregular el 13/11',
    ctx: [(m) => `Antes de medir, por su edad y sexo, la probabilidad era del ${pct(m.pAfPrior)} (estudio OFRECE).`, 'Sin fibrilación auricular registrada.'],
    samples: [['lab', 12, '2026-09-17']],
    albNote: 'Un cociente de laboratorio normal en septiembre. Círculo: laboratorio.',
    fgNote: 'Medido en la última analítica.',
    tl: [
      { d: '13 nov', icon: 'watch', t: 'Pulso irregular', meta: 'reloj', hot: true, ecg: 'af', sub: 'El reloj avisó y grabó 30 s de ECG de una derivación: intervalos irregulares y sin ondas P claras.' },
      { d: '12 nov', icon: 'pulse', t: 'Pulso irregular', meta: 'reloj', sub: 'Primera comprobación irregular.' },
      { d: '17 sep', icon: 'tube', t: 'Cociente albúmina/creatinina: 12 mg/g', meta: 'laboratorio', sub: 'Normal.' },
    ],
    reqTitle: 'Petición de pruebas',
    req: [
      { on: true, t: 'ECG de 12 derivaciones', d: 'Con enfermería, mañana a primera hora.' },
      { on: true, t: 'NT-proBNP', d: (m) => `P(≥ 125 pg/ml) estimada ${pct(m.pBnp)}; si sale alto, ecocardiograma.` },
      { on: false, t: 'Hemograma, TSH, iones y función hepática', d: 'Estudio inicial, si se confirma la fibrilación.' },
    ],
    note: (m) =>
      `Dos comprobaciones del pulso irregulares con el reloj (12 y 13/11/2026) y ECG de una derivación de 30 s con intervalos irregulares. P(fibrilación auricular) ${pct(m.pAf)} (antes de medir, ${pct(m.pAfPrior)} por edad y sexo). Sin fibrilación auricular registrada. Hipertenso en tratamiento.\n` +
      `Plan: ECG de 12 derivaciones y NT-proBNP. Si se confirma, CHA2DS2-VA = 3.`,
    codesWhen: 'Si el ECG la confirma (CIE-10-ES)',
    codes: [['I48.91', 'Fibrilación auricular, no especificada']],
    guide: [
      ['A valorar', 'El diagnóstico necesita un ECG: de 12 derivaciones, o de una derivación durante 30 s o más. Revisa el trazado del reloj.', 'ESC 2024 · fibrilación auricular'],
      ['Si se confirma', 'CHA₂DS₂-VA = 3 (75 años o más: 2; hipertensión: 1). Con 2 o más, la guía recomienda anticoagular.', 'ESC 2024 · fibrilación auricular'],
    ],
    msg: 'Hola, Manuel. Tu reloj ha notado el pulso irregular dos días. No es urgente, pero conviene un electrocardiograma: tienes cita mañana a las 9:40 con enfermería. Si notas mareo, dolor en el pecho o te falta el aire, llama al 112.',
  },
  {
    id: 'carmen',
    group: 'act',
    name: 'Lucía Prieto Gómez',
    short: 'Lucía Prieto',
    first: 'Lucía',
    ini: 'LP',
    age: 59,
    sex: 'M',
    cip: '3346',
    areas: ['tension', 'msg'],
    channel: 'App · manguito prestado',
    consta: ['Sin enfermedades crónicas registradas'],
    why: (m) => `Tensión en casa ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)} sin hipertensión registrada`,
    chips: [
      ['bp', 'gauge', (m) => `TA en casa ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)} · 7 días`],
      ['msg', 'msg', () => (replied('carmen') ? null : 'Mensaje nuevo')],
    ],
    action: 'registrar',
    doneLabel: 'Registrado · I10',
    toast: 'Hipertensión registrada en la historia de Lucía: I10.',
    last: 'Semana de tensión el 05-11/11',
    ctx: ['Tensión en consulta: 138/86. En casa, todos los días por encima de 135/85.'],
    samples: [['lab', 7, '2026-10-07']],
    albNote: 'Cociente de laboratorio normal en octubre.',
    fgNote: 'Medido en la última analítica.',
    tl: [
      { d: '5-11 nov', icon: 'gauge', t: 'Semana de tensión', meta: 'manguito prestado', hot: true, bp: true, sub: (m) => `${fixPct(m.bp.msg)} ${m.bp.n} lecturas en ${m.bp.days} días; el primero no cuenta.` },
      { d: '7 oct', icon: 'tube', t: 'Cociente albúmina/creatinina: 7 mg/g', meta: 'laboratorio', sub: 'Normal.' },
    ],
    reqTitle: 'Petición de pruebas',
    req: [
      { on: true, t: 'Sodio y potasio', d: 'Estudio básico de la hipertensión: el CAC, el FG y los lípidos ya constan.' },
      { on: true, t: 'ECG de 12 derivaciones', d: 'Estudio básico de la hipertensión.' },
      { on: false, t: 'HbA1c', d: (m) => `P(diabetes oculta) ${pct(m.pDm)}: basta una glucosa en la farmacia.` },
    ],
    note: (m) =>
      `Automedida de 7 días con manguito validado (05-11/11/2026): media ${Math.round(m.bp.sbp)}/${Math.round(m.bp.dbp)} mmHg, ${m.bp.n} lecturas en ${m.bp.days} días (límite 135/85). Tensión en consulta 138/86. CAC 7 mg/g (10/2026), FG 88. SCORE2 ${pct1(m.cv.score)}: riesgo bajo o moderado.\n` +
      `Juicio: hipertensión arterial confirmada por automedida.\n` +
      `Plan: estudio básico (iones, ECG) y cita para decidir tratamiento.`,
    codesWhen: 'Código sugerido (CIE-10-ES)',
    codes: [['I10', 'Hipertensión esencial (primaria)']],
    guide: [
      ['A valorar', 'Una media en casa de 135/85 o más confirma la hipertensión.', 'ESC 2024 · hipertensión'],
      ['A valorar', 'Con la hipertensión confirmada, la guía recomienda fármaco además de los cambios en el estilo de vida.', 'ESC 2024 · hipertensión'],
    ],
    msg: 'Hola, Lucía. Tu semana de tensión ha salido alta: 149/91 de media. Te llamamos para darte cita y hablar de cómo bajarla. El manguito lo puedes devolver en el centro o en tu farmacia.',
  },
  {
    id: 'rosa',
    group: 'act',
    name: 'Rosa Méndez Ibáñez',
    short: 'Rosa Méndez',
    first: 'Rosa',
    ini: 'RM',
    age: 68,
    sex: 'M',
    cip: '5560',
    areas: ['rinon', 'corazon'],
    channel: 'App',
    consta: ['Diabetes tipo 2', 'Hipertensión arterial'],
    meds: 'antidiabético oral y antihipertensivo',
    why: 'El FG baja año tras año: de 88 a 49 en cuatro años',
    chips: [
      ['kid', 'drop', (m) => `FG ${num(m.trend.slope, 1)} al año`],
      ['kid', 'tube', 'Orina nunca medida'],
      ['ecg', 'lungs', 'Le falta el aire en las escaleras'],
    ],
    action: 'citar',
    doneLabel: 'Citada · jueves 10:20',
    toast: 'Cita para Rosa: jueves 19/11 a las 10:20. El kit de orina le llega mañana.',
    last: 'Cuestionario de casa el 14/11',
    ctx: [
      (m) => `Pendiente de ${num(m.trend.slope, 1)} ml/min/1,73 m² al año (entre ${num(m.trend.slopeLow, 1)} y ${num(m.trend.slopeHigh, 1)}): descenso rápido.`,
      (m) => `La orina no se ha medido nunca: P(albuminuria) ${pct(m.alb.p2)}. El estadio KDIGO está incompleto.`,
      'En el cuestionario de casa dice que le falta el aire al subir escaleras.',
    ],
    samples: [],
    albNote: 'Sin ninguna muestra: lo que se espera para alguien con su historia.',
    trendNote: 'Cinco analíticas, una al año. La de octubre, 49.',
    tl: [
      { d: '14 nov', icon: 'doc', t: 'Cuestionario de casa', meta: 'app', hot: true, sub: 'Le falta el aire al subir escaleras; salud regular; alguna dificultad para caminar.' },
      { d: '27 oct', icon: 'flask', t: 'Analítica anual: FG 49', meta: 'laboratorio', sub: 'Sin cociente albúmina/creatinina, como en las cuatro anteriores.' },
    ],
    req: [
      { on: true, t: 'Cociente albúmina/creatinina en orina', d: (m) => `P(albuminuria) ${pct(m.alb.p2)}. Completa el estadio KDIGO.` },
      { on: true, t: 'Creatinina sérica y FG', d: 'Confirmar el 49 de octubre.' },
      { on: true, t: 'Potasio', d: 'Antes de iniciar o subir un IECA, un ARA-II o finerenona.' },
      { on: true, t: 'NT-proBNP', d: (m) => `P(≥ 125 pg/ml) estimada ${pct(m.pBnp)}, con disnea en las escaleras.` },
    ],
    note: (m) =>
      `FG de 88 a 49 en cuatro años (5 analíticas, 2022-2026). Tendencia ${num(m.trend.slope, 1)} ml/min/1,73 m² al año (${num(m.trend.slopeLow, 1)} a ${num(m.trend.slopeHigh, 1)}): descenso rápido. FG estimado hoy ${num(m.trend.level)} (${range(m.trend.low, m.trend.high)}). Albuminuria nunca medida (P ≥ 30 mg/g: ${pct(m.alb.p2)}). Diabetes tipo 2 e hipertensión. Disnea al subir escaleras (cuestionario de casa); P(NT-proBNP ≥ 125) ${pct(m.pBnp)}.\n` +
      `Plan: CAC, función renal, potasio y NT-proBNP; valorar derivación a nefrología.`,
    codesWhen: 'A confirmar con la próxima analítica (CIE-10-ES)',
    codes: [
      ['E11.22', 'Diabetes tipo 2 con enfermedad renal crónica diabética'],
      ['I12.9', 'Enfermedad renal crónica hipertensiva, estadio 1 a 4'],
      ['N18.31', 'Enfermedad renal crónica, estadio 3a'],
    ],
    guide: [
      ['A valorar', 'Pierde más de 5 ml/min/1,73 m² al año: progresión rápida. Valorar derivar a nefrología.', 'KDIGO 2024 · derivación'],
      ['A valorar', 'Diabetes tipo 2 con ERC y FG de 20 o más: iSGLT2.', 'KDIGO 2024 · rec. 3.7.1 (1A)'],
    ],
    msg: 'Hola, Rosa. Tus análisis muestran que el riñón filtra un poco menos cada año. Quiero verte esta semana: tienes cita el jueves a las 10:20. Antes, haz la prueba de orina del kit que te llega mañana.',
  },
  {
    id: 'ramon',
    group: 'act',
    name: 'Ramón Iglesias Soto',
    short: 'Ramón Iglesias',
    first: 'Ramón',
    ini: 'RI',
    age: 56,
    sex: 'H',
    cip: '7718',
    areas: ['glucosa', 'tension'],
    channel: 'App · farmacia',
    consta: ['Hipertensión arterial', 'Prediabetes', 'Fumador'],
    meds: 'sin tratamiento',
    why: 'Glucosa en ayunas de 126 o más dos días en la farmacia, sin diabetes registrada',
    chips: [['glu', 'glu', 'Glucosa en farmacia 134 · 141']],
    action: 'analitica',
    toast: 'Petición enviada: HbA1c, glucosa en ayunas, CAC y creatinina. Ramón elige el día en la app.',
    last: 'Glucosa en farmacia el 12/11',
    ctx: [(m) => `Con las dos glucosas, P(diabetes sin diagnosticar) ${pct(m.pDm)}.`, 'Prediabetes registrada, IMC 34, fuma y tiene diabetes en la familia.'],
    samples: [],
    albNote: 'Sin muestras de orina: lo que se espera para alguien con su historia.',
    fgNote: 'Estimado con la historia: no hay creatinina.',
    tl: [
      { d: '12 nov', icon: 'glu', t: 'Glucosa en la farmacia: 141 mg/dl', meta: 'en ayunas', hot: true, sub: 'Segundo día por encima de 126.' },
      { d: '10 nov', icon: 'glu', t: 'Glucosa en la farmacia: 134 mg/dl', meta: 'en ayunas' },
      { d: '6 nov', icon: 'cross', t: 'Vale de glucosa para su farmacia', sub: 'Paso 1 del cribado: P(diabetes oculta) del 2 % o más.' },
    ],
    req: [
      { on: true, t: 'HbA1c', d: (m) => `P(diabetes sin diagnosticar) ${pct(m.pDm)}: confirmar con análisis.` },
      { on: true, t: 'Glucosa venosa en ayunas', d: 'Aprovechando la extracción.' },
      { on: true, t: 'Cociente albúmina/creatinina en orina', d: 'Nunca medido.' },
      { on: true, t: 'Creatinina sérica y FG', d: 'Nunca medida.' },
    ],
    note: (m) =>
      `Glucosa capilar en ayunas en la farmacia: 134 (10/11) y 141 mg/dl (12/11/2026). Prediabetes registrada; IMC 34, fumador, antecedentes familiares de diabetes. P(diabetes sin diagnosticar) ${pct(m.pDm)}.\n` +
      `Plan: confirmar con HbA1c y glucosa venosa en ayunas; CAC y creatinina en la misma extracción.`,
    codesWhen: 'Si la HbA1c es de 6,5 % o más (CIE-10-ES)',
    codes: [['E11.9', 'Diabetes mellitus tipo 2 sin complicaciones']],
    guide: [
      ['A valorar', 'Diagnóstico con HbA1c de 6,5 % o más, o glucosa venosa en ayunas de 126 mg/dl o más, confirmadas.', 'ADA 2025 · Standards of Care'],
      ['A valorar', 'Tensión de consulta de 142/90 sin tratamiento: una semana de automedida antes de decidir.', 'ESC 2024 · hipertensión'],
    ],
    msg: 'Hola, Ramón. Las dos glucosas de la farmacia han salido algo altas. Te he pedido un análisis para confirmarlo: elige el día en la app y ve en ayunas.',
  },
  {
    id: 'elena',
    group: 'med',
    name: 'Elena Navarro Pascual',
    short: 'Elena Navarro',
    first: 'Elena',
    ini: 'EN',
    age: 74,
    sex: 'M',
    cip: '2284',
    areas: ['rinon'],
    channel: 'Kit por correo',
    consta: ['Hipertensión arterial'],
    meds: 'antihipertensivo',
    why: 'FG de 51 en la gota de sangre de casa: falta confirmarlo',
    chips: [
      ['kid', 'drop', 'FG capilar 51'],
      ['kid', 'tube', 'Orina sin medir'],
    ],
    test: 'Creatinina',
    testIcon: 'flask',
    how: 'analítica (ya hay gota de sangre)',
    action: 'analitica',
    toast: 'Petición enviada: creatinina, CAC, potasio y NT-proBNP. Elena elige el día en la app.',
    last: 'Gota de sangre el 11/11',
    samples: [],
    albNote: 'Sin muestras de orina: lo que se espera para alguien con su historia.',
    fgNote: 'La gota de sangre tiene más error que la analítica: el modelo la combina con la historia.',
    tl: [
      { d: '11 nov', icon: 'drop', t: 'Gota de sangre por correo: FG 51', meta: 'laboratorio', hot: true, sub: (m) => `Con la historia, el modelo lo deja en ${num(m.blood.egfr[0])} (${range(m.blood.egfr[1], m.blood.egfr[2])}).` },
      { d: '4 nov', icon: 'box', t: 'Kit enviado: gota de sangre', sub: 'La lista decía que la creatinina era lo que más aportaba.' },
    ],
    req: [
      { on: true, t: 'Creatinina sérica y FG', d: (m) => `P(FG < 60) ${pct(m.pG60)}. Confirma la gota de sangre.` },
      { on: true, t: 'Cociente albúmina/creatinina en orina', d: (m) => `P(albuminuria) ${pct(m.alb.p2)}. Completa el estadio.` },
      { on: true, t: 'Potasio', d: 'Si se confirma, antes de iniciar o subir un IECA o un ARA-II.' },
      { on: true, t: 'NT-proBNP', d: (m) => `P(≥ 125 pg/ml) estimada ${pct(m.pBnp)}.` },
    ],
    note: (m) =>
      `Gota de sangre en casa (11/11/2026): FG 51. Con la historia clínica, FG estimado ${num(m.blood.egfr[0])} (${range(m.blood.egfr[1], m.blood.egfr[2])}); P(FG < 60) ${pct(m.pG60)}. Albuminuria sin medir. Hipertensa en tratamiento.\n` +
      `Plan: confirmar en el laboratorio con CAC; NT-proBNP en la misma extracción.`,
    codesWhen: 'Si un FG < 60 se confirma pasados 3 meses (CIE-10-ES)',
    codes: [
      ['I12.9', 'Enfermedad renal crónica hipertensiva, estadio 1 a 4'],
      ['N18.31', 'Enfermedad renal crónica, estadio 3a'],
    ],
    guide: [['A valorar', 'Un FG por debajo de 60 aislado no basta: hay que confirmarlo pasados tres meses.', 'KDIGO 2024 · definición de ERC']],
    msg: 'Hola, Elena. La gota de sangre que mandaste hay que confirmarla con un análisis normal. Elige el día en la app; no hace falta ir en ayunas.',
  },
  {
    id: 'marta',
    group: 'med',
    name: 'Marta Romero Gil',
    short: 'Marta Romero',
    first: 'Marta',
    ini: 'MR',
    age: 47,
    sex: 'M',
    cip: '6093',
    areas: ['rinon'],
    channel: 'Kit por la app',
    consta: ['Diabetes tipo 2'],
    meds: 'antidiabético oral',
    why: 'Diabética: dos tiras dudosas; la app ya le ha pedido el tubo',
    chips: [
      ['kid', 'strip', '2 tiras dudosas'],
      ['auto', 'auto', 'En marcha en casa'],
    ],
    test: 'Orina',
    testIcon: 'tube',
    how: 'tubo del kit, ya pedido',
    action: 'recordar',
    toast: 'Recordatorio en la app de Marta: mañana, el tubo con la primera orina.',
    last: 'Tira dudosa el 14/11',
    samples: [
      ['tira', 30, '2026-11-13'],
      ['tira', 60, '2026-11-14'],
    ],
    albNote: 'Dos tiras dudosas: el filtro no puede descartar ni confirmar. Cuadrados: tiras.',
    fgNote: 'Estimado con la historia.',
    tl: [
      { d: '15 nov', icon: 'tube', t: 'La app pidió el tubo', hot: true, sub: (m) => `P(albuminuria) ${pct(m.alb.p2)}; con otra tira se resolvería solo el ${pct(m.alb.resolve)} de las veces.`, said: 'Para salir de dudas hace falta medirlo en el laboratorio.' },
      { d: '13-14 nov', icon: 'strip', t: 'Dos tiras con el móvil', swatches: [[30, 100], [30, 50]], pseq: [0.065, 0.12, 0.34], sub: 'P(albuminuria) antes y después de cada tira:' },
      { d: '10 nov', icon: 'clock', t: 'Prueba aplazada', sub: 'Contestó que tenía la regla: la app la pasó unos días.' },
      { d: '6 nov', icon: 'box', t: 'Kit enviado', sub: 'Cribado anual de la diabetes.' },
    ],
    req: [],
    reqEmpty: 'No hace falta pedir nada: el tubo va al laboratorio en el sobre del kit.',
    note: (m) =>
      `Cribado anual de albuminuria en casa: dos tiras dudosas (13 y 14/11/2026). P(albuminuria) ${pct(m.alb.p2)}; cociente estimado ${num(m.alb.median)} mg/g (${range(m.alb.low, m.alb.high)}). La app ha pedido muestra para el laboratorio (15/11).`,
    guide: [['Recordatorio', 'Diabetes tipo 2: cociente albúmina/creatinina y FG al menos una vez al año.', 'KDIGO 2024 · ADA 2025']],
    msg: 'Hola, Marta. Recuerda: mañana, llena el tubo con la primera orina del día y échalo al buzón en el sobre del kit.',
  },
  {
    id: 'antonio',
    group: 'med',
    name: 'Antonio Delgado Ferrer',
    short: 'Antonio Delgado',
    first: 'Antonio',
    ini: 'AD',
    age: 81,
    sex: 'H',
    cip: '0475',
    areas: ['rinon', 'corazon'],
    channel: 'Sin móvil: por teléfono',
    consta: ['Hipertensión arterial'],
    meds: 'antihipertensivo',
    why: 'Sin analítica desde 2019 y sin móvil',
    chips: [
      ['kid', 'flask', 'Sin creatinina desde 2019'],
      ['auto', 'call', 'Aviso por teléfono'],
    ],
    test: 'Creatinina',
    testIcon: 'flask',
    how: 'analítica en el centro',
    action: 'analitica',
    toast: 'Petición enviada: creatinina, NT-proBNP, CAC y glucosa. Enfermería llamará a Antonio para la cita.',
    last: 'Tensión en consulta, 2025',
    samples: [],
    albNote: 'Sin muestras de orina: lo que se espera para alguien con su historia.',
    fgNote: 'Estimado con la historia: la última creatinina es de 2019.',
    tl: [{ d: '2019', icon: 'flask', t: 'Última analítica', sub: 'Desde entonces, solo la tensión en consulta (150/72). No usa móvil: el kit de orina iría por correo.' }],
    req: [
      { on: true, t: 'Creatinina sérica y FG', d: (m) => `P(FG < 60) ${pct(m.pG60)}.` },
      { on: true, t: 'NT-proBNP', d: (m) => `P(≥ 125 pg/ml) estimada ${pct(m.pBnp)}; si sale alto, ecocardiograma.` },
      { on: true, t: 'Cociente albúmina/creatinina en orina', d: (m) => `P(albuminuria) ${pct(m.alb.p2)}.` },
      { on: true, t: 'Glucosa', d: (m) => `P(diabetes oculta) ${pct(m.pDm)}. Aprovechando la extracción.` },
      { on: false, t: 'Colesterol total y HDL', d: 'El SCORE2-OP se ha calculado con lípidos típicos.' },
    ],
    note: (m) =>
      `Sin analítica desde 2019. Hipertenso en tratamiento; TA en consulta 150/72. Estimado con la historia: FG ${num(m.blood.egfr[0])} (${range(m.blood.egfr[1], m.blood.egfr[2])}), P(FG < 60) ${pct(m.pG60)}; P(NT-proBNP ≥ 125) ${pct(m.pBnp)}. No usa móvil: avisar por teléfono.\n` +
      `Plan: analítica con creatinina, NT-proBNP, CAC y glucosa.`,
    guide: [['A valorar', 'NT-proBNP de 125 pg/ml o más fuera de una descompensación: ecocardiograma.', 'ESC 2021 · insuficiencia cardíaca']],
    msg: null,
    msgVia: 'Avisar a enfermería',
    msgToast: 'Aviso a enfermería: llamar a Antonio para la extracción.',
  },
  {
    id: 'dolores',
    group: 'med',
    name: 'Dolores Sánchez Ortiz',
    short: 'Dolores Sánchez',
    first: 'Dolores',
    ini: 'DS',
    age: 69,
    sex: 'M',
    cip: '5132',
    areas: ['rinon'],
    channel: 'App',
    consta: ['Diabetes tipo 2', 'Hipertensión arterial'],
    meds: 'antidiabético oral y antihipertensivo',
    why: 'Diabética e hipertensa: la orina no se ha medido nunca',
    chips: [['kid', 'tube', 'Cociente nunca medido']],
    test: 'Orina',
    testIcon: 'box',
    how: 'kit en casa (app)',
    action: 'kit',
    toast: 'Kit de orina en camino: 3 tiras y 2 tubos. La app avisará a Dolores el día de la prueba.',
    last: 'Analítica anual el 20/10',
    samples: [],
    albNote: 'Sin muestras: lo que se espera para una diabética e hipertensa de su edad.',
    fgNote: 'Medido en la analítica anual.',
    tl: [{ d: '20 oct', icon: 'flask', t: 'Analítica anual: FG 66, HbA1c 7,6 %', meta: 'laboratorio', sub: 'Sin cociente albúmina/creatinina, como en las tres anteriores.' }],
    req: [],
    reqEmpty: 'Con el kit basta: si las tiras dudan, la app pide el tubo.',
    note: (m) =>
      `Diabetes tipo 2 e hipertensión. FG 66, HbA1c 7,6 % (10/2026). Cociente albúmina/creatinina nunca medido: P(albuminuria) ${pct(m.alb.p2)}.\n` + `Plan: kit de orina en casa (tiras y, si dudan, tubo para el laboratorio).`,
    guide: [['A valorar', 'Diabetes tipo 2: cociente albúmina/creatinina y FG al menos una vez al año.', 'KDIGO 2024 · ADA 2025']],
    msg: 'Hola, Dolores. Te llega a casa un kit para una prueba de orina. La app te dirá qué día hacerla: son tres minutos.',
  },
  {
    id: 'pilar',
    group: 'med',
    name: 'Pilar Garrido Lozano',
    short: 'Pilar Garrido',
    first: 'Pilar',
    ini: 'PG',
    age: 58,
    sex: 'M',
    cip: '8152',
    areas: ['rinon', 'msg'],
    channel: 'Kit por la app',
    consta: ['Sin enfermedades crónicas registradas'],
    why: 'Tira dudosa en su primer cribado; el tubo va camino del laboratorio',
    chips: [
      ['kid', 'strip', '2 tiras dudosas'],
      ['kid', 'tube', 'Tubo enviado'],
      ['msg', 'msg', () => (replied('pilar') ? null : 'Mensaje nuevo')],
    ],
    test: 'Orina',
    testIcon: 'tube',
    how: 'tubo en el laboratorio',
    action: 'responder',
    toast: 'Respuesta enviada a Pilar.',
    last: 'Tubo enviado el 14/11',
    samples: [
      ['tira', 30, '2026-11-12'],
      ['tira', 30, '2026-11-13'],
    ],
    albNote: 'Dos tiras con albúmina 30 mg/l: dudosas. El tubo lo aclarará.',
    fgNote: 'Medido en su última analítica.',
    tl: [
      { d: '15 nov', icon: 'msg', t: 'Mensaje a su médico', meta: 'con las pruebas adjuntas', hot: true, sub: '«¿Tengo que pedir cita?»' },
      { d: '14 nov', icon: 'tube', t: 'Tubo enviado', sub: 'Llega al laboratorio el martes 17.' },
      { d: '12-13 nov', icon: 'strip', t: 'Dos tiras con el móvil', swatches: [[30, 100], [30, 100]], pseq: [0.02, 0.07, 0.12], sub: 'P(albuminuria) antes y después de cada tira:', said: 'Para salir de dudas hace falta medirlo en el laboratorio.' },
      { d: '10 nov', icon: 'box', t: 'Kit enviado', sub: 'Primer cribado.' },
    ],
    req: [],
    reqEmpty: 'El tubo ya va camino del laboratorio: no hace falta pedir nada.',
    note: (m) =>
      `Primer cribado de albuminuria en casa: dos tiras con albúmina 30 mg/l (12 y 13/11/2026), dudosas. P(albuminuria) ${pct(m.alb.p2)}; cociente estimado ${num(m.alb.median)} mg/g (${range(m.alb.low, m.alb.high)}). Tubo enviado al laboratorio el 14/11.`,
    guide: [['Qué esperar', 'Si el tubo sale normal, el cribado termina hasta el año que viene; si sale alto, la app pide repetir a los tres meses.', 'Protocolo del kit']],
    msg: null,
    msgVia: 'Responder',
  },
  {
    id: 'andres',
    group: 'med',
    name: 'Andrés Molina Rey',
    short: 'Andrés Molina',
    first: 'Andrés',
    ini: 'AM',
    age: 70,
    sex: 'H',
    cip: '3901',
    areas: ['corazon'],
    channel: 'App · reloj con ECG',
    consta: ['Hipertensión arterial', 'Dislipemia'],
    meds: 'antihipertensivo y estatina',
    why: 'El ECG de 30 s de su reloj apunta a un corazón que bombea poco',
    chips: [
      ['watch', 'watch', 'ECG del reloj (30 s)'],
      ['ecg', 'heart', (m) => `P(FE baja) ${pct(m.pEf)}`],
    ],
    test: 'NT-proBNP',
    testIcon: 'flask',
    how: 'analítica; si sale alto, ecocardiograma',
    action: 'analitica',
    toast: 'Petición enviada: NT-proBNP. Si sale alto, el ecocardiograma irá como preferente.',
    last: 'ECG del reloj el 09/11',
    samples: [['lab', 15, '2026-10-01']],
    albNote: 'Cociente de laboratorio normal en octubre.',
    fgNote: 'Medido en la última analítica.',
    tl: [
      { d: '9 nov', icon: 'watch', t: 'ECG de 30 s con el reloj', meta: 'una derivación', hot: true, ecg: 'lowef', sub: (m) => `Patrón asociado a fracción de eyección baja: P(FE ≤ 40 %) ${pct(m.pEf)}; antes de grabar, 0,9 %.` },
      { d: '1 oct', icon: 'tube', t: 'Cociente albúmina/creatinina: 15 mg/g', meta: 'laboratorio', sub: 'Normal.' },
    ],
    req: [
      { on: true, t: 'NT-proBNP', d: 'Si es de 125 pg/ml o más, ecocardiograma preferente.' },
      { on: false, t: 'Ecocardiograma', d: 'Directamente, si no hay lista de espera.' },
    ],
    note: (m) =>
      `ECG de una derivación de 30 s con el reloj (09/11/2026): patrón asociado a fracción de eyección baja. P(FE ≤ 40 %) ${pct(m.pEf)} (antes de grabar, 0,9 %). Sin insuficiencia cardíaca registrada. El modelo se validó con el aparato en el pecho; con reloj, está sin validar.\n` +
      `Plan: NT-proBNP; si es de 125 pg/ml o más, ecocardiograma preferente.`,
    guide: [['A valorar', 'NT-proBNP de 125 pg/ml o más fuera de una descompensación: ecocardiograma.', 'ESC 2021 · insuficiencia cardíaca']],
    msg: 'Hola, Andrés. El electrocardiograma de tu reloj conviene completarlo con un análisis de sangre. Elige el día en la app. Si te falta el aire o se te hinchan los tobillos, pide cita antes.',
  },
  {
    id: 'francisco',
    group: 'med',
    name: 'Francisco Vega Martín',
    short: 'Francisco Vega',
    first: 'Francisco',
    ini: 'FV',
    age: 66,
    sex: 'H',
    cip: '6627',
    areas: ['glucosa'],
    channel: 'App · farmacia',
    consta: ['Hipertensión arterial', 'Dislipemia', 'Exfumador'],
    meds: 'antihipertensivo y estatina',
    why: 'Nunca se ha medido la glucosa',
    chips: [['glu', 'glu', 'Glucosa nunca medida']],
    test: 'Glucosa',
    testIcon: 'cross',
    how: 'una medida en la farmacia',
    action: 'farmacia',
    toast: 'Vale enviado a su farmacia: glucosa capilar en ayunas. La app avisará a Francisco.',
    last: 'Cociente normal el 22/09',
    samples: [['lab', 9, '2026-09-22']],
    albNote: 'Cociente de laboratorio normal en septiembre.',
    fgNote: 'Medido en la última analítica.',
    tl: [{ d: '22 sep', icon: 'tube', t: 'Cociente albúmina/creatinina: 9 mg/g', meta: 'laboratorio', sub: 'Normal. Nunca se ha medido la glucosa ni la HbA1c.' }],
    req: [
      { on: true, t: 'Glucosa capilar en ayunas, en la farmacia', d: (m) => `Paso 1: P(diabetes oculta) ${pct(m.pDm)}, del 2 % o más.` },
      { on: false, t: 'HbA1c', d: 'Paso 2: solo si, con la glucosa, la probabilidad sigue en el 2 % o más.' },
    ],
    reqTitle: 'Glucosa en dos pasos',
    reqBtn: 'Enviar el vale',
    note: (m) => `Hipertenso y dislipémico, IMC 31, exfumador. Sin glucosa ni HbA1c en la historia: P(diabetes sin diagnosticar) ${pct(m.pDm)}.\nPlan: glucosa capilar en ayunas en la farmacia; HbA1c solo si la probabilidad sigue en el 2 % o más.`,
    guide: [['A valorar', 'Cribado de diabetes en adultos con sobrepeso y otro factor de riesgo, como la hipertensión.', 'ADA 2025 · Standards of Care']],
    msg: 'Hola, Francisco. Cuando te venga bien, pásate en ayunas por tu farmacia: te miden la glucosa con un pinchazo en el dedo. Ya tienen tu vale.',
  },
]
const P = Object.fromEntries(PATIENTS.map((p) => [p.id, p]))

// Más pacientes del cupo, sin nada pendiente (para la vista Pacientes).
const QUIET = [
  ['Lucía Ferrer Campos', 'LF', 45, 'M', '2219', 'Analítica y orina normales en 2026', 'bajo o moderado'],
  ['Luis Ortega Blanco', 'LO', 66, 'H', '7390', 'Diabético con iSGLT2: FG estable', 'alto'],
  ['Vicente Lara Pons', 'VL', 73, 'H', '1182', 'ERC G3a A2 registrada; seguimiento al día', 'muy alto'],
]

// --- Mensajes ----------------------------------------------------------------------------------
const MESSAGES = [
  {
    id: 'pilar',
    when: 'Ayer, 19:42',
    unread: true,
    text: 'Hola, Carmen. La app me ha pedido el tubo y ya lo he mandado. ¿Tengo que pedir cita?',
    sugg: [
      'No hace falta cita por ahora, Pilar. Cuando llegue el resultado del laboratorio, la app te dirá qué hacer y yo también lo veré. Si hiciera falta, te llamamos.',
      'Gracias, Pilar. Pide cita para dentro de dos semanas y lo vemos juntos con el resultado.',
      'Recibido. Te escribo en cuanto llegue el resultado del laboratorio.',
    ],
  },
  {
    id: 'carmen',
    when: 'Ayer, 12:05',
    unread: true,
    text: 'Ya he terminado la semana de la tensión. ¿Devuelvo el manguito en el centro o en la farmacia?',
    sugg: [
      'Puedes devolverlo en el centro o en tu farmacia, como te venga mejor. Ya he visto la semana: te llamamos para darte cita y hablar de la tensión.',
      'Gracias, Lucía. Devuélvelo en la farmacia. Te llamamos esta semana para verte.',
    ],
  },
  {
    id: 'marta',
    when: 'Domingo, 21:10',
    unread: false,
    text: '¿Tengo que estar en ayunas para llenar el tubo?',
    bot: 'No hace falta ayunar: lo importante es que sea la primera orina del día. Llena el tubo hasta la marca y échalo al buzón en el sobre del kit.',
  },
]

// --- Kits (los de los pacientes de hoy; las cifras de la semana son de ejemplo) -----------------
const KIT_STEPS = ['Enviado', 'Entregado', 'En uso', 'Hecho']
const KITS = [
  ['pilar', '3 tiras y 2 tubos', 'App', 3, 'Tubo en camino', '14/11 · llega al laboratorio el 17/11'],
  ['marta', '3 tiras y 2 tubos', 'App', 2, 'Tubo pedido', '15/11 · la app pidió el tubo'],
  ['carmen', 'Manguito, 7 días', 'App', 3, 'Manguito por devolver', '11/11 · semana completa'],
  ['julian', 'Tiras de repetición y manguito', 'App', 4, 'Terminado', '10/11 · manguito devuelto'],
  ['ramon', 'Glucosa en la farmacia', 'Farmacia', 4, 'Hecho', '12/11 · 141 mg/dl en ayunas'],
  ['elena', 'Gota de sangre por correo', 'Correo', 4, 'Resultado recibido', '11/11 · FG capilar 51'],
  ['andres', 'ECG de 30 s con su reloj', 'Reloj', 4, 'Hecho', '09/11 · grabación valorada'],
  ['dolores', '3 tiras y 2 tubos', 'App', 0, 'Propuesto hoy', 'Falta tu visto bueno'],
  ['francisco', 'Vale de glucosa', 'Farmacia', 0, 'Propuesto hoy', 'Falta tu visto bueno'],
]

// --- Estado ------------------------------------------------------------------------------------
const S = {
  view: 'hoy',
  sel: 'julian',
  group: 'todo',
  area: null,
  q: '',
  done: {}, // id -> etiqueta de la acción hecha
  sent: {}, // 'id:req' | 'id:note' | 'id:msg' -> true
  req: {}, // id -> [marcadas]
  notes: {}, // id -> texto editado
  live: {}, // id -> { m, ms }
  liveState: {}, // id -> 'wait' | 'ok' | 'off'
  conn: 'wait',
  msgSel: 'pilar',
  msgs: {}, // id -> { read, replies: [] }
  draft: {}, // id -> texto de la respuesta
  sugg: {}, // id -> índice de la sugerencia elegida
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

// --- Gráficas ----------------------------------------------------------------------------------
const KR = [
  [0, 1, 2],
  [0, 1, 2],
  [1, 2, 3],
  [2, 3, 3],
  [3, 3, 3],
  [3, 3, 3],
]
const KR_LABEL = ['bajo', 'moderado', 'alto', 'muy alto']
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
const cellPct = (p) => (p < 0.005 ? '·' : p < 0.01 ? `<1${NB}%` : `${Math.round(p * 100)}${NB}%`)

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
        return `<td class="kr${KR[gi][ai]}${p < 0.005 ? ' is-zero' : ''}${isTop ? ' is-top' : ''}" style="--p:${Math.max(0.02, p).toFixed(3)};--k:${k++}" title="${g} · ${A_COLS[ai][0]}: ${pct(p)} (riesgo ${KR_LABEL[KR[gi][ai]]})">${cellPct(p)}${p >= 0.005 ? '<i></i>' : ''}</td>`
      })
      .join('')
    return `<tr><th scope="row">${g}<small>${r}</small></th>${cells}</tr>`
  }).join('')
  return `<div class="dr-card">
    <div class="dr-ch"><p>Estadio KDIGO</p><small>probabilidad por casilla</small></div>
    <table class="dr-kdigo"><caption class="dr-sr">Probabilidad de cada combinación de filtrado glomerular (G) y albuminuria (A). Color: riesgo KDIGO.</caption>
      <thead><tr><th scope="col"><span class="dr-sr">FG</span></th>${A_COLS.map(([a, r]) => `<th scope="col">${a}<small>${r}</small></th>`).join('')}</tr></thead>
      <tbody>${body}</tbody></table>
    <p class="dr-ktop">Más probable: <b>${G_ROWS[top[0]][0]} · ${A_COLS[top[1]][0]}</b> (${pct(best)})</p>
    <p class="dr-klegend" aria-hidden="true">Riesgo:${KR_LABEL.map((l, i) => `<span><i style="background:${KR_COLOR[i]}"></i>${l}</span>`).join('')}</p>
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
      const title = `<title>${kind === 'tira' ? 'Tira' : 'Laboratorio'} del ${date.slice(8, 10)}/${date.slice(5, 7)}: ${num(u)} mg/g</title>`
      return kind === 'tira'
        ? `<rect x="${(cx - 4.5).toFixed(1)}" y="${(cy - 4.5).toFixed(1)}" width="9" height="9" fill="#fff" stroke="#0d2226" stroke-width="1.6">${title}</rect>`
        : `<circle cx="${cx}" cy="${cy}" r="4.6" fill="#0d2226" stroke="#fff" stroke-width="1.4">${title}</circle>`
    })
    .join('')
  const mx = x(median).toFixed(1)
  return `<svg class="dr-svg dr-fade" viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribución del cociente albúmina/creatinina verdadero, en escala logarítmica">
    <defs><linearGradient id="dr-bg-alb" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#5fbe8c" stop-opacity=".9"/><stop offset="1" stop-color="#0b7774" stop-opacity=".55"/></linearGradient></defs>
    ${zones}${refs}
    <path d="${area}" fill="url(#dr-bg-alb)"/><path d="M${line}" fill="none" stroke="#0b7774" stroke-width="1.6"/>
    <line x1="${mx}" x2="${mx}" y1="${T + 2}" y2="${base}" stroke="#0d2226" stroke-width="1.6"/>
    <line class="dr-s-ax" x1="${L}" x2="${W - R}" y1="${base}" y2="${base}"/>${ticks}${marks}
    <text x="${W - R}" y="${H - 1}" text-anchor="end">mg/g</text>
  </svg>`
}

function trendSVG(t) {
  // En el móvil, menos ancho de dibujo: así el texto no se encoge al escalar.
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
  const dots = meas.map(([d, v]) => `<circle cx="${x(d).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3.6" fill="#0d2226" stroke="#fff" stroke-width="1.3"><title>${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}: FG ${num(v)}</title></circle>`).join('')
  const years = []
  const ya = new Date(d0 * 86_400_000).getUTCFullYear() + 1
  const yb = new Date(d1 * 86_400_000).getUTCFullYear()
  for (let yr = ya; yr <= yb; yr++) years.push(yr)
  const yTicks = years.map((yr) => `<line class="dr-s-ax" x1="${x(`${yr}-01-01`).toFixed(1)}" x2="${x(`${yr}-01-01`).toFixed(1)}" y1="${H - B}" y2="${H - B + 4}"/><text x="${x(`${yr}-01-01`).toFixed(1)}" y="${H - 6}" text-anchor="middle">${yr}</text>`).join('')
  const tx = x(TODAY)
  return `<svg class="dr-svg dr-fade" viewBox="0 0 ${W} ${H}" role="img" aria-label="Filtrado glomerular: analíticas, tendencia del modelo y su incertidumbre hasta hoy">
    ${bands}${refs}
    <path d="${bandPath}" fill="#0b7774" fill-opacity=".14"/>
    ${solid ? `<path d="M${solid}" fill="none" stroke="#0b7774" stroke-width="2"/>` : ''}
    ${dash ? `<path d="${dash}" fill="none" stroke="#0b7774" stroke-width="2" stroke-dasharray="4 4"/>` : ''}
    <line x1="${tx.toFixed(1)}" x2="${tx.toFixed(1)}" y1="${T}" y2="${H - B}" stroke="#0d2226" stroke-width="1" opacity=".35"/>
    <circle cx="${tx.toFixed(1)}" cy="${y(t.level).toFixed(1)}" r="4.2" fill="#fff" stroke="#0b7774" stroke-width="2"/>
    <text class="dr-s-lbl" x="${(tx - 6).toFixed(1)}" y="${(y(t.high) - 5).toFixed(1)}" text-anchor="end">hoy ${num(t.level)}</text>
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
  const dots = (k, c) => byDay.map((d, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(d[k]).toFixed(1)}" r="2.6" fill="${i === 0 ? '#fff' : c}" stroke="${c}" stroke-width="1.4"><title>${d[0].slice(8, 10)}/${d[0].slice(5, 7)}: ${d[1]}/${d[2]}${i === 0 ? ' (no cuenta)' : ''}</title></circle>`).join('')
  return `<svg class="dr-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tensión media de cada día frente a los límites de 135/85">
    <line x1="${L}" x2="${W - R}" y1="${y(135)}" y2="${y(135)}" stroke="#d9766e" stroke-dasharray="4 3"/><text x="${L - 4}" y="${y(135) + 3}" text-anchor="end">135</text>
    <line x1="${L}" x2="${W - R}" y1="${y(85)}" y2="${y(85)}" stroke="#0b7774" stroke-dasharray="4 3"/><text x="${L - 4}" y="${y(85) + 3}" text-anchor="end">85</text>
    <path d="M${line(1)}" fill="none" stroke="#d9766e" stroke-width="1.8"/>${dots(1, '#d9766e')}
    <path d="M${line(2)}" fill="none" stroke="#0b7774" stroke-width="1.8"/>${dots(2, '#0b7774')}
    <text x="${L}" y="${H - 3}">${byDay[0][0].slice(8, 10)}/${byDay[0][0].slice(5, 7)}</text><text x="${W - R}" y="${H - 3}" text-anchor="end">${byDay[byDay.length - 1][0].slice(8, 10)}/${byDay[byDay.length - 1][0].slice(5, 7)}</text>
  </svg>`
}

/** Un trocito de ECG de una derivación (3 s de los 30), dibujado con ondas gaussianas. */
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

// --- Piezas de la ficha ------------------------------------------------------------------------
function albHTML(p, m) {
  const a = m.alb
  if (!a) return ''
  return `<div class="dr-card">
    <div class="dr-ch"><p>Albuminuria</p>${stateChip(a.status, a.label)}</div>
    <p class="dr-big"><b>${num(a.median)}<small> mg/g</small></b><small>${range(a.low, a.high)} · P(30 o más) ${pct(a.p2)}</small></p>
    ${m.belief ? beliefSVG(m.belief, p.samples ?? [], a.median) : ''}
    <p class="dr-note-s">${esc(p.albNote ?? '')}</p>
  </div>`
}

const TREND_LABEL = { estable: 'estable', descenso: 'en descenso', descenso_rapido: 'descenso rápido', incierto: 'incierta', insuficiente: 'pocos datos', sin_datos: 'sin datos' }
function fgHTML(p, m) {
  const t = m.trend
  if (t) {
    return `<div class="dr-card">
      <div class="dr-ch"><p>Tendencia del FG</p><small>${(t.meas ?? []).length} analíticas · ${TREND_LABEL[t.status] ?? t.status}</small></div>
      <p class="dr-big"><b>${num(t.slope, 1)}<small> ml/min/1,73 m² al año</small></b><small>entre ${num(t.slopeLow, 1)} y ${num(t.slopeHigh, 1)} · hoy, ${num(t.level)} (${range(t.low, t.high)})</small></p>
      ${trendSVG(t)}
      <p class="dr-note-s">${esc(p.trendNote ?? '')}</p>
    </div>`
  }
  const e = m.blood?.egfr
  if (!e) return ''
  const measured = e[3]
  return `<div class="dr-card">
    <div class="dr-ch"><p>Filtrado glomerular</p><small>${measured ? 'medido' : esc(e[4])}</small></div>
    <p class="dr-big"><b>${num(e[0])}<small> ml/min/1,73 m²</small></b><small>${measured ? 'sin serie para la tendencia' : `entre ${range(e[1], e[2])} · P(FG < 60) ${pct(m.pG60)}`}</small></p>
    <p class="dr-note-s">${esc(p.fgNote ?? '')}</p>
  </div>`
}

function probsHTML(m) {
  const rows = [['Enfermedad renal (FG < 60 o cociente ≥ 30)', m.pCkd]]
  rows.push(m.pDm == null ? ['Diabetes', 'registrada'] : ['Diabetes sin diagnosticar', m.pDm])
  if (m.pBnp != null) rows.push(['NT-proBNP ≥ 125 pg/ml', m.pBnp])
  if (m.pAf != null) rows.push(['Fibrilación auricular', m.pAf])
  if (m.pEf != null) rows.push(['Fracción de eyección ≤ 40 %', m.pEf])
  return `<ul class="dr-probs" aria-label="Otras probabilidades">${rows
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
  return `<ul class="dr-probs" aria-label="Hallazgo nuevo si solo se hiciera cada prueba">${rows
    .map(([t, p], i) => `<li><span>${i === 0 ? '<em class="dr-best">la que más aporta</em>' : ''}${esc(TEST_NAMES[t] ?? t)}</span><b>${pct(p)}</b><span class="dr-bar" aria-hidden="true"><i style="--p:${p.toFixed(3)}"></i></span></li>`)
    .join('')}</ul>`
}

function srcHTML(p) {
  const st = S.liveState[p.id]
  const live = S.live[p.id]
  if (LIVE[p.id] && st === 'wait') return '<span class="dr-src is-wait"><i></i>consultando al modelo…</span>'
  if (live) {
    const calls = ['assess', ...(LIVE[p.id].albuminuria ? ['albuminuria'] : []), ...(LIVE[p.id].trend ? ['egfr-trend'] : [])]
    return `<span class="dr-src is-live" title="Recalculado ahora: ${calls.map((c) => `POST /api/model/${c}`).join(', ')}"><i></i>calculado por el modelo · ${num(live.ms)} ms</span>`
  }
  return '<span class="dr-src" title="Calculado con el mismo modelo el 16/11/2026 y guardado en la página"><i></i>calculado por el modelo · copia guardada</span>'
}

function cvHTML(p, m) {
  const cv = m.cv
  if (!cv) return ''
  const names = ['Bajo o moderado', 'Alto', 'Muy alto']
  const head = `<em aria-hidden="true"></em>${names.map((n) => `<em>${n}</em>`).join('')}`
  const rec = `<span>Consta en la historia</span>${names
    .map((n, i) => `<div class="dr-cv-c${i === cv.rec ? ' is-on' : ''}">${i === cv.rec ? `<b>${cv.approx ? 'SCORE2-OP' : 'SCORE2'} ${pct1(cv.score)}</b><small>${cv.approx ? 'con datos supuestos' : 'con lo que consta'}</small>` : ''}</div>`)
    .join('')}`
  const home = `<span>Con lo medido en casa</span>${cv.probs
    .map((q, i) => `<div class="dr-cv-c${i === cv.cat ? ' is-on' : ''}" style="--p:${q.toFixed(3)}"><i></i><b>${pct(q)}</b></div>`)
    .join('')}`
  const more = []
  if (cv.rec === cv.cat && cv.probs[cv.cat] > 0.9) more.push(`Misma categoría: ${names[cv.cat].toLowerCase()}. ${esc(p.cvExtra ?? '')}`)
  else if (cv.probs[2] > 0.05 && cv.rec < 2) more.push(`Probabilidad de que sea muy alto: <b>${pct(cv.probs[2])}</b>. Lo aclara lo que falta por medir.`)
  if (m.hr) more.push(`Con lo medido en casa, su riesgo de muerte cardiovascular es <b>${num(m.hr, 1)}</b> veces el de su edad y sexo (modelo con desenlaces).`)
  return `<div class="dr-cv" role="table" aria-label="Categoría de riesgo cardiovascular: la que consta y la probable con lo medido en casa">${head}${rec}${home}</div>
    ${more.length ? `<p class="dr-cv-more">${more.map((t) => `<span>${t}</span>`).join('')}</p>` : ''}`
}

function reqHTML(p, m) {
  const items = p.req ?? []
  if (!items.length) return `<div class="dr-box"><div class="dr-box-h">${ico('flask')}<p>Petición</p><small>nada que pedir</small></div><div class="dr-box-b"><p class="dr-note-s">${esc(p.reqEmpty ?? '')}</p></div></div>`
  const checked = S.req[p.id] ?? items.map((x) => x.on)
  const sent = S.sent[`${p.id}:req`]
  const n = checked.filter(Boolean).length
  return `<div class="dr-box">
    <div class="dr-box-h">${ico('flask')}<p>${esc(p.reqTitle ?? 'Petición de analítica')}</p><small>rellena · revisa y envía</small></div>
    <div class="dr-box-b"><div class="dr-req">${items
      .map(
        (x, i) =>
          `<label><input type="checkbox" data-req="${p.id}" data-i="${i}"${checked[i] ? ' checked' : ''}${sent ? ' disabled' : ''}><span><b>${esc(x.t)}</b><span>${esc(fixPct(val(x.d, m)))}</span></span></label>`,
      )
      .join('')}</div></div>
    <div class="dr-box-f"><p>${p.action === 'farmacia' ? 'La farmacia recibe el vale y la app avisa al paciente.' : 'El paciente elige el día de la extracción en la app.'}</p>${
      sent
        ? `<span class="dr-done">${ico('check')}${p.action === 'farmacia' ? 'Vale enviado' : 'Petición enviada'}</span>`
        : `<button type="button" class="dr-btn is-sm" data-do="req" data-id="${p.id}"${n ? '' : ' disabled'}>${ico('send')}${esc(p.reqBtn ?? `Enviar petición (${n})`)}</button>`
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
    <div class="dr-box-h">${ico('doc')}<p>Nota clínica</p><small>preescrita · editable</small></div>
    <div class="dr-box-b"><label class="dr-sr" for="dr-note-${p.id}">Nota clínica de ${esc(p.first)}</label><textarea class="dr-notetext" id="dr-note-${p.id}" data-note="${p.id}" rows="7" spellcheck="false">${esc(text)}</textarea>${codes}</div>
    <div class="dr-box-f"><p>Se pega en el evolutivo con los códigos.</p>${
      copied ? `<span class="dr-done">${ico('check')}Copiada a la historia</span>` : `<button type="button" class="dr-btn is-sm" data-do="copy" data-id="${p.id}">${ico('copy')}Copiar a la historia</button>`
    }</div>
  </div>`
}

function guideHTML(p) {
  if (!p.guide?.length) return ''
  return `<div class="dr-box">
    <div class="dr-box-h">${ico('book')}<p>Sugerencias de la guía</p><small>a valorar</small></div>
    <div class="dr-box-b"><ul class="dr-guide">${p.guide
      .map(([tag, text, src]) => `<li><span class="dr-tag${tag === 'A valorar' || tag === 'Si se confirma' ? '' : ' is-later'}">${esc(tag)}</span><p>${esc(text)}</p><cite>${esc(src)}</cite></li>`)
      .join('')}</ul>
    <p class="dr-disc">${ico('shield')}Apoyo a la decisión: LatentHealth no pauta tratamientos. Decides tú.</p></div>
  </div>`
}

function msgHTML(p) {
  if (!p.msg) return ''
  const sent = S.sent[`${p.id}:msg`]
  return `<div class="dr-box">
    <div class="dr-box-h">${ico('send')}<p>Mensaje al paciente</p><small>borrador · lo verá en la app</small></div>
    <div class="dr-box-b"><p class="dr-msgprev">${esc(p.msg)}</p></div>
    <div class="dr-box-f"><p>Con sus pruebas de casa enlazadas.</p>${
      sent ? `<span class="dr-done">${ico('check')}Enviado</span>` : `<button type="button" class="dr-btn is-sm" data-do="msg" data-id="${p.id}">${ico('send')}Enviar al paciente</button>`
    }</div>
  </div>`
}

function timelineHTML(p, m) {
  const items = (p.tl ?? []).map((e) => {
    let extra = ''
    if (e.swatches) extra += `<p class="dr-sub">${e.swatches.map(([a, c]) => swatch(a, c)).join(' ')}</p>`
    if (e.pseq) {
      extra += `<div class="dr-pseq" aria-label="Probabilidad de albuminuria tras cada tira">${e.pseq
        .map((q, i) => `${i ? ico('chev') : ''}<span class="${q >= 0.95 ? 'is-top' : q >= 0.5 ? 'is-hi' : ''}">${pct(q)}</span>`)
        .join('')}</div>`
    }
    if (e.bp && m.bp?.byDay) extra += `<div class="dr-mini">${bpSVG(m.bp.byDay)}</div>`
    if (e.ecg) {
      const label = { regular: 'ritmo regular', af: 'ritmo irregular, sin ondas P claras', lowef: 'QRS de bajo voltaje y algo ancho' }[e.ecg]
      extra += `<div class="dr-ecg" role="img" aria-label="Trozo del ECG del reloj: ${label}" title="3 s de los 30 grabados (trazado ilustrativo)"><svg viewBox="0 0 360 46" preserveAspectRatio="none" aria-hidden="true"><path d="${ecgPath(e.ecg)}"/></svg></div>`
    }
    if (e.said) extra += `<p class="dr-app-said">${ico('phone')}La app le dijo: «${esc(e.said)}»</p>`
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
    items.push(`<li class="is-ctx">${ico('flask', 'sm')}<span>Probabilidad de un hallazgo nuevo si se completan las pruebas: <b>${pct(m.row?.p)}</b>.</span></li>`)
  }
  for (const c of p.ctx ?? []) items.push(`<li class="is-ctx">${ico('info', 'sm')}<span>${esc(val(c, m))}</span></li>`)
  const quote = p.quote && m.alb?.action ? `<p class="dr-quote"><b>Lo que dice el filtro de albuminuria</b><br>${esc(fixPct(m.alb.action))}</p>` : ''
  return `<ul class="dr-reasons">${items.join('')}</ul>${p.group === 'med' ? byTestHTML(m) : ''}${quote}`
}

function fileHTML(p) {
  const m = M(p.id)
  const a = ACTIONS[p.action]
  const done = S.done[p.id]
  const sex = p.sex === 'H' ? 'Hombre' : 'Mujer'
  const meds = p.meds ? `<span>Toma</span>${esc(p.meds)}` : ''
  const primary = done
    ? `<span class="dr-done">${ico('check')}${esc(done)}</span>`
    : `<button type="button" class="dr-btn is-pri" data-do="row" data-id="${p.id}">${ico(a.icon)}${a.label}</button>`
  const second = p.msg
    ? S.sent[`${p.id}:msg`]
      ? `<span class="dr-done">${ico('check')}Mensaje enviado</span>`
      : `<button type="button" class="dr-btn" data-do="msg" data-id="${p.id}">${ico('send')}Enviar al paciente</button>`
    : p.msgToast
      ? `<button type="button" class="dr-btn" data-do="msg" data-id="${p.id}">${ico('call')}${esc(p.msgVia)}</button>`
      : ''
  const copy = S.sent[`${p.id}:note`] ? `<span class="dr-done">${ico('check')}Nota copiada</span>` : `<button type="button" class="dr-btn" data-do="copy" data-id="${p.id}">${ico('copy')}Copiar a la historia</button>`
  return `<header class="dr-fhead">
      <span class="dr-av is-lg" aria-hidden="true">${p.ini}</span>
      <div><h3 id="dr-file-h">${esc(p.name)}</h3><p>${p.age} años · ${sex} · CIP •••• ${p.cip} · ${esc(p.channel)}</p></div>
      <div class="dr-fhead-r"><span class="dr-pill g-${p.group}">${GROUPS[p.group][0]}</span><span id="dr-src">${srcHTML(p)}</span></div>
    </header>
    <p class="dr-consta"><span>Consta</span>${p.consta.map((c) => `<em>${esc(c)}</em>`).join('')}${meds}</p>
    <div class="dr-fbody">
      <section class="dr-sec" aria-labelledby="dr-s1"><div class="dr-sh"><h4 id="dr-s1">Por qué está en la lista</h4><small>${p.group === 'act' ? 'hallazgo que no consta' : 'lo que aportaría medir'}</small></div>${whyHTML(p, m)}</section>
      <section class="dr-sec" aria-labelledby="dr-s2"><div class="dr-sh"><h4 id="dr-s2">Lo que cree el modelo</h4><small>a ${TODAY.slice(8, 10)}/${TODAY.slice(5, 7)}/${TODAY.slice(0, 4)}</small></div>
        <div class="dr-m2">${kdigoHTML(m)}${albHTML(p, m)}</div>${fgHTML(p, m)}${probsHTML(m)}</section>
      <section class="dr-sec" aria-labelledby="dr-s3"><div class="dr-sh"><h4 id="dr-s3">Pruebas en casa y laboratorio</h4><small>lo más reciente arriba</small></div>${timelineHTML(p, m)}</section>
      <section class="dr-sec" aria-labelledby="dr-s4"><div class="dr-sh"><h4 id="dr-s4">Riesgo cardiovascular</h4><small>SCORE2 y guía europea</small></div>${cvHTML(p, m)}</section>
      <section class="dr-sec" aria-labelledby="dr-s5"><div class="dr-sh"><h4 id="dr-s5">Preparado para ti</h4><small>revisa, cambia lo que quieras y envía</small></div>
        <div class="dr-prep">${reqHTML(p, m)}${noteHTML(p, m)}${guideHTML(p)}${msgHTML(p)}</div></section>
    </div>
    <div class="dr-fbar">${primary}<span class="dr-sp"></span>${copy}${second}</div>`
}

// --- La lista ----------------------------------------------------------------------------------
function rowHTML(p, i) {
  const m = M(p.id)
  const sel = p.id === S.sel
  const done = S.done[p.id]
  const chips = p.chips
    .map(([k, icon, t]) => [k, icon, val(t, m)])
    .filter(([, , t]) => t)
    .map(([k, icon, t]) => `<span class="dr-chip dr-k-${k}">${ico(icon)}${esc(t)}</span>`)
    .join('')
  // Lo que ya se ha hecho desde la ficha también se ve en la fila.
  const marks = []
  if (S.sent[`${p.id}:req`] && p.action !== 'analitica' && p.action !== 'farmacia') marks.push('Petición enviada')
  if (S.sent[`${p.id}:note`]) marks.push('Nota en la historia')
  if (S.sent[`${p.id}:msg`]) marks.push(p.msg ? 'Mensaje enviado' : 'Enfermería avisada')
  const marked = marks.map((t) => `<span class="dr-chip dr-k-done">${ico('check')}${t}</span>`).join('')
  const prob =
    p.group === 'med' && m.row
      ? `<div class="dr-prob"><span class="dr-bar" role="img" aria-label="Probabilidad de un hallazgo nuevo: ${pct(m.row.p)}"><i style="--p:${m.row.p.toFixed(3)};--i:${i}"></i></span><b aria-hidden="true">${pct(m.row.p)}</b><span>${ico(p.testIcon ?? 'flask', 'xs')}<em>${esc(p.test)}</em>· ${esc(p.how)}</span></div>`
      : ''
  const act = done
    ? `<span class="dr-done">${ico('check')}${esc(done)}<button type="button" data-do="undo" data-id="${p.id}" aria-label="Deshacer: ${esc(done)}">Deshacer</button></span>`
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

// Lo que se hace en casa (kit, vale de farmacia, recordatorio) se puede aprobar de una vez.
const HOME_ACTIONS = { kit: 'un kit', farmacia: 'un vale de farmacia', recordar: 'un recordatorio' }
const batchable = () => PATIENTS.filter((p) => p.action in HOME_ACTIONS && !S.done[p.id])
const listText = (items) => (items.length > 1 ? `${items.slice(0, -1).join(', ')} y ${items[items.length - 1]}` : items[0] ?? '')

function batchHTML() {
  const items = batchable()
  if (!items.length) return ''
  const n = items.length
  return `<div class="dr-batch">${ico('auto')}<p><b>${n === 1 ? 'Una propuesta' : `${n} propuestas`} de casa</b>, listas para aprobar: ${listText(items.map((p) => `${HOME_ACTIONS[p.action]} (${p.first})`))}.</p>
    <button type="button" class="dr-btn is-sm" data-do="batch">${ico('check')}Aprobar ${n === 1 ? 'la' : `las ${n}`}</button></div>`
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
  toast(`Aprobado de una vez: ${listText(items.map((p) => HOME_ACTIONS[p.action]))}. Cada paciente lo verá en la app.`, () => {
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
      ${rows.length ? `<ul class="dr-rows">${rows.map((p) => rowHTML(p, i++)).join('')}</ul>` : '<p class="dr-empty">Nadie con este filtro en este grupo.</p>'}
      ${g === 'med' && !S.area ? `<p class="dr-more">${ico('chev', 'xs')}Y ${MEDIR_TOTAL - 7} más, con probabilidad por debajo del 7${NB}%.</p>` : ''}
    </section>`)
  }
  if (S.group === 'todo' && !S.area) {
    out.push(`<section class="dr-group g-ok" aria-label="Sin pendientes">
      <div class="dr-gh"><span class="dr-gtag">${ico('check')}Sin pendientes<b>${num(SIN_PENDIENTES)}</b></span><small>${GROUPS.ok[1]}</small></div>
      <button type="button" class="dr-more" data-do="view" data-view="pacientes">${ico('users', 'xs')}Ver el cupo entero</button>
    </section>`)
  }
  return out.join('')
}

function filtersHTML() {
  const all = PATIENTS.length
  const segs = [
    ['todo', 'Todo', all],
    ['act', 'Actuar', PATIENTS.filter((p) => p.group === 'act').length],
    ['med', 'Medir', PATIENTS.filter((p) => p.group === 'med').length],
  ]
    .map(([k, l, n]) => `<button type="button" data-seg="${k}" aria-pressed="${S.group === k}">${l}<b>${n}</b></button>`)
    .join('')
  const chips = AREAS.map(([k, l, icon]) => `<button type="button" class="dr-fchip" data-area="${k}" aria-pressed="${S.area === k}">${ico(icon, 'xs')}${l}</button>`).join('')
  return `<div class="dr-seg" role="group" aria-label="Grupo">${segs}</div><div class="dr-fchips" role="group" aria-label="Filtrar por señal">${chips}</div>`
}

function hoyHTML() {
  const p = P[S.sel] ?? PATIENTS[0]
  return `<div class="dr-view dr-hoy">
    <section class="dr-listpane dr-scroll" id="dr-listpane" aria-label="Lista de trabajo de hoy">
      <header class="dr-lhead">
        <h3>Hoy <small>cupo de 1.500 · ejemplo</small></h3>
        <p class="dr-lsum">Ordenados por lo que cambiaría, no por quién está peor.</p>
        <div class="dr-filters" id="dr-filters">${filtersHTML()}</div>
      </header>
      <div id="dr-groups">${groupsHTML()}</div>
    </section>
    <article class="dr-file dr-scroll" id="dr-file" tabindex="-1" aria-labelledby="dr-file-h">${fileHTML(p)}</article>
  </div>`
}

// --- Otras vistas ------------------------------------------------------------------------------
function attachHTML(id) {
  const p = P[id]
  const m = M(id)
  if (id === 'pilar') {
    return `<div class="dr-attach"><p class="dr-attach-h">${ico('paperclip', 'xs')}Sus pruebas de casa, adjuntas</p><ul>
      <li><time>12/11</time>${swatch(30, 100)} Tira: albúmina 30 mg/l, creatinina 100 mg/dl ${stateChip('dudosa', 'Dudosa')} <span>→ «Repite mañana»</span></li>
      <li><time>13/11</time>${swatch(30, 100)} Tira: igual ${stateChip('dudosa', 'Dudosa')} <span>→ «Manda el tubo»</span></li>
      <li><time>14/11</time>${ico('tube', 'xs')} Tubo enviado: llega al laboratorio el martes 17</li></ul>
      <p class="dr-model-says">El modelo: P(albuminuria) <b>${pct(m.alb.p2)}</b>, cociente estimado ${num(m.alb.median)} mg/g (${range(m.alb.low, m.alb.high)}). Si el tubo sale normal, el cribado termina; si sale alto, la app pide repetir a los tres meses. Mientras llega el resultado, el protocolo no pide cita.</p></div>`
  }
  if (id === 'carmen') {
    return `<div class="dr-attach"><p class="dr-attach-h">${ico('paperclip', 'xs')}Su semana de tensión, adjunta</p><div class="dr-mini">${bpSVG(m.bp.byDay)}</div>
      <p class="dr-model-says">${esc(fixPct(m.bp.msg))} Sin hipertensión registrada: está en tu lista de hoy, en Actuar.</p></div>`
  }
  return ''
}

function inboxHTML() {
  const sel = MESSAGES.find((x) => x.id === S.msgSel) ?? MESSAGES[0]
  const p = P[sel.id]
  const list = MESSAGES.map((x) => {
    const q = P[x.id]
    const isUnread = x.unread && !S.msgs[x.id]?.read
    const tag = x.bot ? `<span class="dr-chip dr-k-auto">${ico('auto')}Respondido por el asistente</span>` : isUnread ? `<span class="dr-chip dr-k-msg">${ico('msg')}Sin responder</span>` : `<span class="dr-chip">${ico('check')}Respondido</span>`
    return `<button type="button" class="dr-mitem${isUnread ? ' is-unread' : ''}" data-msg="${x.id}" aria-current="${x.id === sel.id}"><span class="dr-av" aria-hidden="true">${q.ini}</span><b>${esc(q.short)}<small>${esc(x.when)}</small></b><span class="dr-mtext">${esc(x.text)}</span>${tag}</button>`
  }).join('')
  const replies = (S.msgs[sel.id]?.replies ?? []).map((r) => `<p class="dr-bub is-me"><small>Tú · ahora</small>${esc(r)}</p>`).join('')
  const thread = `<p class="dr-bub"><small>${esc(p.first)} · ${esc(sel.when)}</small>${esc(sel.text)}</p>${attachHTML(sel.id)}${
    sel.bot ? `<p class="dr-bub is-bot"><small>Asistente de la app · al momento</small>${esc(sel.bot)}</p><p class="dr-note-s">${ico('info', 'xs')} Pregunta de las que se repiten: la contestó el asistente con lo que pone el protocolo del kit. Te llega para que lo sepas.</p>` : ''
  }${replies}`
  let reply = ''
  if (!sel.bot && !replied(sel.id)) {
    const chosen = S.sugg[sel.id]
    const sugg = `<div class="dr-sugg"><p>Respuestas sugeridas</p>${sel.sugg
      .map((s, i) => `<button type="button" data-sugg="${i}" aria-pressed="${chosen === i}">${ico('reply')}<span>${esc(s)}</span></button>`)
      .join('')}</div>`
    reply = `${sugg}`
  }
  const box = sel.bot
    ? ''
    : `<div class="dr-reply"><label class="dr-sr" for="dr-reply-t">Tu respuesta a ${esc(p.first)}</label><textarea id="dr-reply-t" data-draft="${sel.id}" placeholder="Escribe o elige una respuesta sugerida">${esc(S.draft[sel.id] ?? '')}</textarea>
        <div><p>Le llega a la app. Si hace falta, la cita se pide desde aquí.</p><button type="button" class="dr-btn" data-open-file="${sel.id}">${ico('doc')}Ver ficha</button><button type="button" class="dr-btn is-pri" data-do="reply" data-id="${sel.id}">${ico('send')}Enviar respuesta</button></div></div>`
  return `<div class="dr-view dr-inbox">
    <section class="dr-mlist dr-scroll" aria-label="Mensajes de pacientes"><header><h3>Mensajes</h3><p>${unread()} sin responder · ${MESSAGES.length} esta semana</p></header>${list}</section>
    <section class="dr-conv dr-scroll" aria-label="Conversación con ${esc(p.first)}">
      <div class="dr-conv-h"><span class="dr-av" aria-hidden="true">${p.ini}</span><div><h4>${esc(p.name)}</h4><p>${p.age} años · ${esc(p.channel)}</p></div></div>
      <div class="dr-thread">${thread}${reply}</div>${box}
    </section>
  </div>`
}

function kitsHTML() {
  const rows = KITS.map(([id, what, ch, step0, state0, last0]) => {
    const p = P[id]
    const sentNow = S.done[id] && (p.action === 'kit' || p.action === 'farmacia')
    const step = sentNow ? 1 : step0
    const state = sentNow ? (p.action === 'farmacia' ? 'Farmacia avisada' : 'Enviado hoy') : state0
    const last = sentNow ? 'Hoy · con tu visto bueno' : last0
    const steps = KIT_STEPS.map((s, i) => `<i class="${i < step ? 'is-on' : ''}${i === step - 1 && step < 4 ? ' is-now' : ''}" title="${s}"></i>`).join('')
    const pill = step === 0 ? 'med' : step >= 4 ? 'ok' : 'teal'
    const action = step === 0 ? `<button type="button" class="dr-btn is-sm" data-do="row" data-id="${id}">${ico(ACTIONS[p.action].icon)}${ACTIONS[p.action].label}</button>` : ''
    return `<tr class="is-click" data-pid="${id}" tabindex="0"><td><b>${esc(p.short)}</b><small>${p.age} · ${p.sex}</small></td><td>${esc(what)}</td><td>${esc(ch)}</td><td><span class="dr-steps" aria-label="${KIT_STEPS[Math.max(0, step - 1)]}">${steps}</span> <span class="dr-pill g-${pill}">${esc(state)}</span></td><td>${esc(last)}${action ? `<br>${action}` : ''}</td></tr>`
  }).join('')
  return `<div class="dr-view dr-page dr-scroll">
    <div class="dr-pagehead"><div><h3>Kits</h3><p>Lo que lleva cada uno lo decide su ficha: solo lo que le falta. Las tiras se mandan; los aparatos se prestan.</p></div><span class="dr-egb">${ico('info', 'xs')}Cifras de la semana: ejemplo</span></div>
    <div class="dr-kpis">
      <div class="dr-kpi"><b>48</b><span>kits enviados esta semana</span><small>a quien le faltaba la prueba</small></div>
      <div class="dr-kpi"><b>41</b><span>tiras leídas con el móvil</span><small>sin pasar por el centro</small></div>
      <div class="dr-kpi"><b>9</b><span>dudas resueltas en casa</span><small>repitiendo la tira</small></div>
      <div class="dr-kpi"><b>4</b><span>manguitos prestados ahora</span><small>2 por devolver</small></div>
    </div>
    <div class="dr-tablewrap"><table class="dr-table is-resp"><caption class="dr-sr">Kits de los pacientes de la lista de hoy</caption>
      <thead><tr><th scope="col">Paciente</th><th scope="col">Qué lleva</th><th scope="col">Canal</th><th scope="col">Estado</th><th scope="col">Último paso</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
  </div>`
}

function indicadoresHTML() {
  const cov = [
    ['Hipertensos', 412, 0.06, 0.58, 0.041, '4,1'],
    ['Diabéticos', 167, 0.38, 0.84, 0.351, '35,1'],
  ]
    .map(
      ([name, n, before, now, ref, refText]) => `<div class="dr-cov-r"><p>${name}<small>${num(n)} en el cupo</small></p>
      <div class="dr-cov-bars">
        <span>Antes</span><span class="dr-bar is-was" style="position:relative"><i style="--p:${before}"></i><span class="dr-ref" style="--x:${ref}" data-l="Shin 2021: ${refText}${NB}%"></span></span><b>${pct(before)}</b>
        <span>Ahora</span><span class="dr-bar is-teal"><i style="--p:${now}"></i></span><b>${pct(now)}</b>
      </div></div>`,
    )
    .join('')
  const funnel = [
    ['Kits enviados', 186],
    ['Pruebas hechas en casa', 152],
    ['Tiras dudosas', 24],
    ['Tubos al laboratorio', 19],
    ['Diagnósticos nuevos', 11],
  ]
    .map(([l, n], i) => `<li><span class="dr-fbarw"><i style="--p:${(n / 186).toFixed(3)};--i:${i}"></i><span>${l}</span></span><b>${n}</b></li>`)
    .join('')
  const auto = [
    ['box', 48, 'Kits enviados', 'a quien su ficha decía que le faltaba la prueba'],
    ['strip', 41, 'Tiras leídas con el móvil', 'cada una actualiza el filtro bayesiano'],
    ['auto', 9, 'Dudas resueltas en casa', 'repitiendo la tira, sin cita ni laboratorio'],
    ['tube', 6, 'Tubos al laboratorio', 'solo cuando otra tira no iba a resolver'],
    ['doc', 12, 'Notas clínicas preparadas', 'con el código CIE-10-ES sugerido'],
    ['flask', 7, 'Peticiones rellenas', 'con el motivo de cada prueba'],
    ['bell', 57, 'Recordatorios', 'el día de la prueba, en la app o por SMS'],
    ['msg', 14, 'Preguntas contestadas por el asistente', 'las de siempre: ayunas, regla, cómo leer la tira'],
  ]
    .map(([icon, n, t, s]) => `<li>${ico(icon)}<span>${t}<small>${s}</small></span><b>${n}</b></li>`)
    .join('')
  return `<div class="dr-view dr-page dr-scroll">
    <div class="dr-pagehead"><div><h3>Indicadores del cupo</h3><p>Lo que ha cambiado desde que el kit llega a casa.</p></div><span class="dr-egb">${ico('info', 'xs')}Datos de ejemplo</span></div>
    <div class="dr-ind">
      <section class="dr-panel"><h4>Prueba de orina en los últimos 12 meses</h4><p>Cociente albúmina/creatinina medido, por grupo.</p>
        <div class="dr-cov">${cov}</div>
        <p class="dr-src-n">«Antes»: el año previo al kit. La raya es la cifra publicada: Shin et al., <i>Hypertension</i> 2021, 3,7 millones de adultos de EE. UU.</p></section>
      <section class="dr-panel"><h4>Del kit al diagnóstico</h4><p>Últimos 90 días.</p><ol class="dr-funnel">${funnel}</ol>
        <p class="dr-funnel-n">Los 11 diagnósticos nuevos: 6 de enfermedad renal, 3 de hipertensión, 1 de fibrilación auricular y 1 de diabetes.</p></section>
    </div>
    <section class="dr-panel" style="margin-top:14px"><h4>Lo que se ha hecho solo esta semana</h4><p>Trabajo que antes pasaba por la consulta.</p><ul class="dr-autot">${auto}</ul></section>
  </div>`
}

function pacientesHTML() {
  const q = S.q.trim().toLowerCase()
  const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  const hit = (name, cip) => !q || norm(name).includes(norm(q)) || cip.includes(q.replace(/\D/g, '') || '\u0000')
  const rows = PATIENTS.filter((p) => hit(p.name, p.cip))
    .map((p) => {
      const m = M(p.id)
      const cv = m.cv ? ['bajo o moderado', 'alto', 'muy alto'][m.cv.rec] : '—'
      return `<tr class="is-click" data-pid="${p.id}" tabindex="0"><td><b>${esc(p.name)}</b><small>CIP •••• ${p.cip}</small></td><td>${p.age} · ${p.sex}</td><td><span class="dr-pill g-${p.group}">${GROUPS[p.group][0]}</span></td><td>${esc(p.last)}</td><td>${cv}</td></tr>`
    })
    .join('')
  const quiet = QUIET.filter(([name, , , , cip]) => hit(name, cip))
    .map(([name, , age, sex, cip, last, cv]) => `<tr><td><b>${esc(name)}</b><small>CIP •••• ${cip}</small></td><td>${age} · ${sex}</td><td><span class="dr-pill g-ok">Sin pendientes</span></td><td>${esc(last)}</td><td>${cv}</td></tr>`)
    .join('')
  const empty = !rows && !quiet ? `<p class="dr-empty">Nadie con «${esc(S.q)}» en esta muestra del cupo.</p>` : ''
  return `<div class="dr-view dr-page dr-scroll">
    <div class="dr-pagehead"><div><h3>Pacientes</h3><p>${q ? `Resultados para «${esc(S.q)}». Intro abre la ficha del primero.` : 'Una muestra del cupo de 1.500: los de la lista de hoy y algunos sin pendientes.'}</p></div><span class="dr-egb">${ico('info', 'xs')}Pacientes inventados</span></div>
    ${empty}${rows || quiet ? `<div class="dr-tablewrap"><table class="dr-table is-resp"><caption class="dr-sr">Pacientes del cupo</caption><thead><tr><th scope="col">Paciente</th><th scope="col">Edad</th><th scope="col">Hoy</th><th scope="col">Lo último</th><th scope="col">Riesgo CV que consta</th></tr></thead><tbody>${rows}${quiet}</tbody></table></div>` : ''}
  </div>`
}

// --- Pintar ------------------------------------------------------------------------------------
const NAV = [
  ['hoy', 'Hoy', 'hoy'],
  ['pacientes', 'Pacientes', 'users'],
  ['mensajes', 'Mensajes', 'msg'],
  ['kits', 'Kits', 'box'],
  ['indicadores', 'Indicadores del cupo', 'chart'],
]

function navHTML() {
  return NAV.map(([k, l, icon]) => {
    const n = k === 'hoy' ? pending('act') + pending('med') : k === 'mensajes' ? unread() : ''
    return `<li><button type="button" data-nav="${k}" aria-current="${S.view === k ? 'page' : 'false'}" title="${l}">${ico(icon)}<span>${l}</span><span class="dr-n${k === 'mensajes' && n ? ' is-hot' : ''}">${n || ''}</span></button></li>`
  }).join('')
}

function shellHTML() {
  const auto = [
    [48, 'kits enviados'],
    [41, 'tiras leídas'],
    [9, 'dudas resueltas en casa'],
    [6, 'tubos al laboratorio'],
    [12, 'notas preparadas'],
    [57, 'recordatorios'],
  ]
    .map(([n, l]) => `<li><b>${n}</b><span>${l}</span></li>`)
    .join('')
  return `<div class="dr-win" role="region" aria-label="Consulta de LatentHealth: demostración con pacientes inventados">
    <header class="dr-top">
      <div class="dr-dots" aria-hidden="true"><i></i><i></i><i></i></div>
      <p class="dr-brand"><span class="dr-pads" aria-hidden="true"><i></i><i></i><i></i><i></i></span>LatentHealth<span>Consulta</span></p>
      <label class="dr-search">${ico('search', 'sm')}<span class="dr-sr">Buscar paciente o CIP</span><input type="search" id="dr-q" placeholder="Buscar paciente o CIP" autocomplete="off" spellcheck="false" /><kbd aria-hidden="true">/</kbd></label>
      <p class="dr-date">${ico('cal', 'sm')}<span>Lunes, 16 de noviembre</span></p>
      <div class="dr-user"><span class="dr-av is-me" aria-hidden="true">CR</span><span><b>Carmen Ruiz</b><small>Medicina de familia</small></span></div>
    </header>
    <div class="dr-body">
      <nav class="dr-side" aria-label="Secciones de la consulta">
        <ul class="dr-nav" id="dr-nav">${navHTML()}</ul>
        <section class="dr-auto" aria-label="Lo automatizado esta semana">
          <p class="dr-side-h">Automatizado esta semana</p>
          <p class="dr-side-sub">cifras de ejemplo</p>
          <ul>${auto}</ul>
          <button type="button" class="dr-auto-more" data-nav="indicadores">${ico('chart', 'xs')}Ver indicadores</button>
        </section>
        <p class="dr-conn" id="dr-conn" title="Las fichas se recalculan con el modelo que corre en este ordenador"><i></i><span>Conectando con el modelo…</span></p>
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
  el.lastElementChild.textContent = state === 'on' ? 'Modelo en vivo, en este ordenador' : 'Sin conexión: copia guardada'
}

// --- Acciones ----------------------------------------------------------------------------------
function toast(text, undo) {
  const el = $('#dr-toast')
  clearTimeout(toastTimer)
  toastUndo = undo ?? null
  el.innerHTML = `${ico('check')}<span>${esc(text)}</span>${undo ? '<button type="button" data-do="toast-undo">Deshacer</button>' : ''}`
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
  toast(`Deshecho: ${p.first} vuelve a estar pendiente.`)
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
      ? `Vale enviado a la farmacia de ${p.first}: ${names[0].toLowerCase()}.`
      : `Petición enviada al laboratorio con ${names.length} ${names.length === 1 ? 'prueba' : 'pruebas'}. ${p.first} elige el día en la app.`,
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
    // Sin permiso para el portapapeles, la demo sigue igual.
  }
  S.sent[`${id}:note`] = true
  afterChange(id)
  toast(`Nota copiada en la historia de ${p.first}${p.codes?.length ? ` con ${p.codes.map(([c]) => c).join(' y ')}` : ''}.`, () => {
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
  toast(p.msgToast ?? `Mensaje enviado a la app de ${p.first}.`, () => {
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
  if (P[id].action === 'responder') S.done[id] = 'Respondido'
  renderView()
  toast(`Respuesta enviada a ${P[id].first}. La verá en la app.`)
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

// --- Modelo en vivo ----------------------------------------------------------------------------
async function post(path, body, signal) {
  const response = await fetch(`/api${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

/** Respuesta de la API -> la misma forma que la copia guardada. */
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
    // Si el médico está escribiendo en la ficha (la nota), no se le repinta debajo: solo cambia la etiqueta.
    const typing = document.activeElement?.closest?.('#dr-file') && document.activeElement.matches('textarea, input')
    if (S.live[id] && !typing) renderFile({ keepScroll: true })
    else updateSrc()
  }
}

function updateSrc() {
  const el = $('#dr-src')
  if (el) el.innerHTML = srcHTML(P[S.sel])
}

// --- Eventos -----------------------------------------------------------------------------------
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
      if (!p.reqBtn) button.lastChild.textContent = `Enviar petición (${n})`
    }
  }
}

// --- Arranque ----------------------------------------------------------------------------------
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
  // Entra cuando su borde superior pasa del 85 % de la pantalla (en el móvil la ventana es muy alta y un
  // umbral proporcional no llegaría a cumplirse).
  const seen = new IntersectionObserver(
    (entries) => {
      if (!entries[0].isIntersecting) return
      seen.disconnect()
      enter()
    },
    { threshold: 0, rootMargin: '0px 0px -15% 0px' },
  )
  seen.observe(host)
  // El modelo se consulta un poco antes de llegar, para que la ficha ya esté calculada.
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

// --- Copia del modelo (calculada el 16/11/2026 con src/latenthealth; ver la cabecera) ----------
// Resultado del modelo por paciente (forma compacta; ver fromApi para el significado de cada campo).
const MODEL = {
  julian: {"alb":{"status":"confirmada","label":"Confirmada","cat":"A2","p":[0.0136,0.9864,0.0001],"p2":0.9864,"median":63.3,"low":40.5,"high":98.1,"action":"Albuminuria persistente A2: registrar ERC (categoría A2) y revisar el tratamiento nefroprotector según la guía.","chronic":true,"resolve":null},"blood":{"egfr":[91.5,63.4,104.7,false,"estimado"],"hba1c":[5.8,5.3,6.5,false,"estimado"],"potassium":[4.0,3.4,4.5,false,"estimado"],"non_hdl":[137.9,92.7,204.1,false,"estimado"],"nt_probnp":[136.6,34.2,318.7,false,"estimado"]},"pG60":0.0519,"joint":[[0.0092,0.5082,0.0001],[0.004,0.4267,0.0001],[0.0004,0.0456,0.0001],[0.0001,0.0059,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.9868,"dm":"poco probable","pDm":0.0916,"hf":"a descartar","pBnp":0.5143,"pAf":0.0001,"pEf":null,"pNew":0.1387,"byTest":{"creatinina":0.0519,"glucosa":0.0916},"recs":[["Creatinina (FG)","P(FG < 60) estimada: 5%; hay que medirlo para estadificar la ERC."],["Glucosa capilar en ayunas (en la farmacia o en casa)","P(diabetes sin diagnosticar) estimada: 9%. Una medida de glucosa lo aclara casi siempre sin análisis."],["NT-proBNP","P(NT-proBNP ≥ 125) estimada: 51%; si sale alto, ecocardiograma."],["Potasio","Antes de iniciar o subir IECA/ARA-II o finerenona."],["Tensión en casa","Tensión en consulta de 146 mmHg. Una semana de automedida con manguito validado."],["Preguntas sobre síntomas","Falta de aire al subir cuestas y dificultad para caminar, contestadas desde casa: afinan la sospecha de insuficiencia cardíaca antes de pedir el NT-proBNP."]],"alerts":["Albuminuria persistente sin enfermedad renal crónica registrada."],"hr":1.65,"cv":{"score":0.0697,"probs":[0.0,0.9941,0.0059],"rec":1,"cat":1,"pUp":0.0059,"approx":false},"row":{"group":"actuar","p":0.1387,"test":"glucosa","how":"una medida en la farmacia, o con su glucómetro"},"belief":{"pts":[[1.02,0.0],[1.25,0.0],[1.53,0.0],[1.86,0.0],[2.28,0.0],[2.78,0.0],[3.4,0.0],[4.15,0.0],[5.07,0.0],[6.19,0.0],[7.56,0.0],[9.23,0.0],[11.28,0.0],[13.78,1e-05],[16.83,7e-05],[20.55,0.0004],[25.11,0.00201],[30.67,0.00767],[37.46,0.02175],[45.76,0.04551],[55.89,0.06961],[68.27,0.07679],[83.39,0.06011],[101.86,0.03293],[124.42,0.01251],[151.98,0.00329],[185.64,0.0006],[226.76,8e-05],[276.99,1e-05],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":63.9,"low":40.8,"high":98.7,"p2":0.9869},"trend":{"level":88.2,"low":79.2,"high":97.0,"slope":-1.13,"slopeLow":-3.17,"slopeHigh":0.85,"status":"estable","traj":[["2021-03-15",94.7,89.6,99.8],["2022-04-20",93.5,89.2,97.7],["2023-05-08",92.3,88.0,96.5],["2024-05-06",91.1,86.0,96.1]],"meas":[["2021-03-15",96.0],["2022-04-20",94.0],["2023-05-08",93.0],["2024-05-06",90.0]],"proj":[["2027-11-16",87.1,76.2,97.7],["2028-11-16",85.9,73.2,98.4],["2029-11-16",84.8,70.1,99.2],["2031-11-16",82.5,63.7,100.9]]},"bp":{"sbp":140.8,"dbp":86.6,"p":0.9999,"valid":true,"msg":"Tensión alta en casa: media 141/87 mmHg (límite 135/85).","n":24,"days":6,"byDay":[["2026-11-02",143,86],["2026-11-03",140,85],["2026-11-04",141,87],["2026-11-05",143,86],["2026-11-06",140,88],["2026-11-07",140,86],["2026-11-08",141,87]]},"pAfPrior":0.0056},
  manuel: {"alb":{"status":"descartada","label":"Descartada","cat":"A1","p":[0.9979,0.0021,0.0001],"p2":0.0021,"median":10.2,"low":4.5,"high":15.9,"action":"Sin albuminuria. Repetir el cribado según la guía (anual en diabetes).","chronic":false,"resolve":null},"blood":{"egfr":[71.0,71.0,71.0,true,"medido"],"hba1c":[5.7,5.2,6.4,false,"estimado"],"potassium":[4.1,3.7,4.7,false,"estimado"],"non_hdl":[133.0,93.4,181.7,false,"estimado"],"nt_probnp":[143.1,49.0,290.1,false,"estimado"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.9979,0.0021,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0021,"dm":"poco probable","pDm":0.0658,"hf":"a descartar","pBnp":0.6296,"pAf":0.729,"pEf":null,"pNew":0.0658,"byTest":{"glucosa":0.0658},"recs":[["Glucosa capilar en ayunas (en la farmacia o en casa)","P(diabetes sin diagnosticar) estimada: 7%. Una medida de glucosa lo aclara casi siempre sin análisis."],["NT-proBNP","P(NT-proBNP ≥ 125) estimada: 63%; si sale alto, ecocardiograma."],["ECG","P(fibrilación auricular) tras las comprobaciones en casa: 73%."],["Preguntas sobre síntomas","Falta de aire al subir cuestas y dificultad para caminar, contestadas desde casa: afinan la sospecha de insuficiencia cardíaca antes de pedir el NT-proBNP."]],"alerts":["Pulso irregular repetido en casa (P(fibrilación auricular) = 73%)."],"hr":0.93,"cv":{"score":0.1362,"probs":[0.0,1.0,0.0],"rec":1,"cat":1,"pUp":0.0,"approx":false},"row":{"group":"actuar","p":0.0658,"test":"glucosa","how":"una medida en la farmacia, o con su glucómetro"},"pAfPrior":0.0133,"belief":{"pts":[[1.02,0.0],[1.25,1e-05],[1.53,6e-05],[1.86,0.00036],[2.28,0.00163],[2.78,0.00511],[3.4,0.01069],[4.15,0.01544],[5.07,0.01741],[6.19,0.02074],[7.56,0.03341],[9.23,0.05638],[11.28,0.07074],[13.78,0.05736],[16.83,0.0297],[20.55,0.01047],[25.11,0.00283],[30.67,0.00069],[37.46,0.00018],[45.76,6e-05],[55.89,2e-05],[68.27,1e-05],[83.39,1e-05],[101.86,1e-05],[124.42,0.0],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":10.2,"low":4.5,"high":15.9,"p2":0.0021}},
  carmen: {"alb":{"status":"descartada","label":"Descartada","cat":"A1","p":[0.9999,0.0001,0.0001],"p2":0.0001,"median":5.6,"low":3.9,"high":8.0,"action":"Sin albuminuria. Repetir el cribado según la guía (anual en diabetes).","chronic":false,"resolve":null},"blood":{"egfr":[88.0,88.0,88.0,true,"medido"],"hba1c":[5.6,5.2,6.1,false,"estimado"],"potassium":[3.9,3.5,4.4,false,"estimado"],"non_hdl":[145.3,100.6,195.4,false,"estimado"],"nt_probnp":[63.2,29.1,189.5,false,"estimado"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.9999,0.0001,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0001,"dm":"poco probable","pDm":0.0261,"hf":"poco probable","pBnp":0.1645,"pAf":null,"pEf":null,"pNew":0.0261,"byTest":{"glucosa":0.0261},"recs":[["Glucosa capilar en ayunas (en la farmacia o en casa)","P(diabetes sin diagnosticar) estimada: 3%. Una medida de glucosa lo aclara casi siempre sin análisis."]],"alerts":["Tensión alta en casa: media 149/91 mmHg (límite 135/85). Sin hipertensión registrada."],"hr":0.66,"cv":{"score":0.0411,"probs":[1.0,0.0001,0.0],"rec":0,"cat":0,"pUp":0.0001,"approx":false},"bp":{"sbp":148.5,"dbp":91.3,"p":1.0,"valid":true,"msg":"Tensión alta en casa: media 149/91 mmHg (límite 135/85).","n":24,"days":6,"byDay":[["2026-11-05",154,91],["2026-11-06",147,92],["2026-11-07",150,92],["2026-11-08",148,90],["2026-11-09",148,92],["2026-11-10",150,91],["2026-11-11",149,90]]},"row":{"group":"actuar","p":0.0261,"test":"glucosa","how":"una medida en la farmacia, o con su glucómetro"},"belief":{"pts":[[1.02,0.0],[1.25,0.0],[1.53,2e-05],[1.86,0.00017],[2.28,0.00114],[2.78,0.00525],[3.4,0.01768],[4.15,0.04697],[5.07,0.08769],[6.19,0.0937],[7.56,0.05342],[9.23,0.01922],[11.28,0.0058],[13.78,0.00163],[16.83,0.00044],[20.55,0.00013],[25.11,4e-05],[30.67,2e-05],[37.46,1e-05],[45.76,0.0],[55.89,0.0],[68.27,0.0],[83.39,0.0],[101.86,0.0],[124.42,0.0],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":5.6,"low":3.9,"high":8.0,"p2":0.0001}},
  rosa: {"alb":{"status":"sin_medir","label":"Sin medir","cat":"A1","p":[0.7069,0.2197,0.0734],"p2":0.2931,"median":10.1,"low":3.2,"high":203.5,"action":"Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 29%.","chronic":false,"resolve":0.7596},"blood":{"egfr":[50.7,46.9,54.5,false,"tendencia de 5 analíticas"],"hba1c":[7.1,7.1,7.1,true,"medido"],"potassium":[4.0,3.5,4.7,false,"estimado"],"non_hdl":[130.3,83.7,180.9,false,"estimado"],"nt_probnp":[107.9,40.4,502.2,false,"estimado"]},"pG60":1.0,"joint":[[0.0,0.0,0.0],[0.0,0.0,0.0],[0.6899,0.213,0.0712],[0.017,0.0068,0.0022],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":1.0,"dm":"diagnosticada","pDm":null,"hf":"a descartar","pBnp":0.4587,"pAf":null,"pEf":null,"pNew":0.3101,"byTest":{"orina":0.2931},"recs":[["UACR (primera orina de la mañana)","Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 29%."],["NT-proBNP","P(NT-proBNP ≥ 125) estimada: 46%; si sale alto, ecocardiograma."],["Potasio","Antes de iniciar o subir IECA/ARA-II o finerenona."]],"alerts":["Descenso rápido del FG: -8,2 ml/min/1,73 m² al año."],"hr":1.41,"cv":{"score":0.088,"probs":[0.0,0.6899,0.3101],"rec":1,"cat":1,"pUp":0.3101,"approx":false},"trend":{"level":50.7,"low":46.9,"high":54.5,"slope":-8.18,"slopeLow":-10.08,"slopeHigh":-6.29,"status":"descenso_rapido","traj":[["2022-10-28",84.9,80.0,89.8],["2023-10-28",76.7,73.0,80.3],["2024-10-27",68.2,65.2,71.2],["2025-10-27",59.7,56.8,62.6],["2026-10-27",51.2,47.5,54.8]],"meas":[["2022-10-28",88],["2023-10-28",79],["2024-10-27",68],["2025-10-27",60],["2026-10-27",49]]},"row":{"group":"actuar","p":0.3101,"test":"orina","how":"kit de orina en casa (aplicación)"},"belief":{"pts":[[1.02,0.00023],[1.25,0.00039],[1.53,0.00077],[1.86,0.00201],[2.28,0.0062],[2.78,0.01572],[3.4,0.02675],[4.15,0.02973],[5.07,0.02429],[6.19,0.01931],[7.56,0.01815],[9.23,0.01818],[11.28,0.01738],[13.78,0.01555],[16.83,0.01322],[20.55,0.01097],[25.11,0.00921],[30.67,0.00807],[37.46,0.00747],[45.76,0.00723],[55.89,0.00716],[68.27,0.00713],[83.39,0.00706],[101.86,0.0069],[124.42,0.00665],[151.98,0.00631],[185.64,0.00589],[226.76,0.0054],[276.99,0.00488],[338.34,0.00434],[413.27,0.0038],[504.81,0.00327],[616.62,0.00276],[753.19,0.0023],[920.02,0.00189],[1123.79,0.00152],[1372.7,0.00121],[1676.73,0.00094],[2048.11,0.00072]],"median":10.6,"low":3.2,"high":214.1,"p2":0.3063}},
  ramon: {"alb":{"status":"sin_medir","label":"Sin medir","cat":"A1","p":[0.9654,0.0273,0.0073],"p2":0.0346,"median":4.0,"low":2.6,"high":11.1,"action":"Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 3%.","chronic":false,"resolve":0.9528},"blood":{"egfr":[92.5,68.3,106.1,false,"estimado"],"hba1c":[6.2,5.7,7.6,false,"estimado con la glucosa de casa"],"potassium":[4.1,3.6,4.5,false,"estimado"],"non_hdl":[150.7,105.5,212.0,false,"estimado"],"nt_probnp":[41.9,16.0,119.6,false,"estimado"]},"pG60":0.0102,"joint":[[0.543,0.0085,0.0019],[0.4137,0.0175,0.0051],[0.0087,0.0012,0.0003],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0433,"dm":"posible","pDm":0.3743,"hf":"poco probable","pBnp":0.0932,"pAf":null,"pEf":null,"pNew":0.4014,"byTest":{"orina":0.0346,"creatinina":0.0102,"HbA1c":0.3743},"recs":[["UACR (primera orina de la mañana)","Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 3%."],["HbA1c","P(diabetes sin diagnosticar) con la glucosa capilar: 37%. Confirmar con análisis."],["Tensión en casa","Tensión en consulta de 142 mmHg. Una semana de automedida con manguito validado."]],"alerts":["Glucosa en ayunas de 126 mg/dl o más en dos días distintos, medida en casa, sin diabetes registrada: confirmar con HbA1c."],"hr":0.91,"cv":{"score":0.0968,"probs":[0.0,0.9997,0.0003],"rec":1,"cat":1,"pUp":0.0003,"approx":false},"row":{"group":"actuar","p":0.4014,"test":"HbA1c","how":"analítica"},"belief":{"pts":[[1.02,4e-05],[1.25,0.00013],[1.53,0.0006],[1.86,0.00366],[2.28,0.01652],[2.78,0.04588],[3.4,0.07539],[4.15,0.0733],[5.07,0.04394],[6.19,0.01955],[7.56,0.01059],[9.23,0.0087],[11.28,0.00777],[13.78,0.00647],[16.83,0.00493],[20.55,0.00347],[25.11,0.00231],[30.67,0.00151],[37.46,0.00103],[45.76,0.00078],[55.89,0.00066],[68.27,0.00061],[83.39,0.00058],[101.86,0.00056],[124.42,0.00054],[151.98,0.00051],[185.64,0.00048],[226.76,0.00044],[276.99,0.00039],[338.34,0.00035],[413.27,0.0003],[504.81,0.00026],[616.62,0.00022],[753.19,0.00018],[920.02,0.00015],[1123.79,0.00012],[1372.7,0.0001],[1676.73,7e-05],[2048.11,6e-05]],"median":3.9,"low":2.6,"high":10.5,"p2":0.0285}},
  elena: {"alb":{"status":"sin_medir","label":"Sin medir","cat":"A1","p":[0.9438,0.0439,0.0123],"p2":0.0562,"median":4.6,"low":2.9,"high":17.1,"action":"Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 6%.","chronic":false,"resolve":0.8977},"blood":{"egfr":[58.9,50.5,67.5,false,"capilar en casa"],"hba1c":[5.8,5.3,6.3,false,"estimado"],"potassium":[4.0,3.2,4.5,false,"estimado"],"non_hdl":[141.9,99.1,188.5,false,"estimado"],"nt_probnp":[170.5,48.4,427.0,false,"estimado"]},"pG60":0.5501,"joint":[[0.0,0.0,0.0],[0.4311,0.015,0.0038],[0.4844,0.0256,0.0075],[0.0283,0.0033,0.001],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.5689,"dm":"poco probable","pDm":0.0511,"hf":"a descartar","pBnp":0.6344,"pAf":null,"pEf":null,"pNew":0.5909,"byTest":{"orina":0.0562,"creatinina":0.5501,"glucosa":0.0511},"recs":[["UACR (primera orina de la mañana)","Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 6%."],["Creatinina (FG)","P(FG < 60) estimada: 55%; hay que medirlo para estadificar la ERC. Ya hay una punción capilar; conviene confirmarla en el laboratorio."],["Glucosa capilar en ayunas (en la farmacia o en casa)","P(diabetes sin diagnosticar) estimada: 5%. Una medida de glucosa lo aclara casi siempre sin análisis."],["NT-proBNP","P(NT-proBNP ≥ 125) estimada: 63%; si sale alto, ecocardiograma."],["Potasio","Antes de iniciar o subir IECA/ARA-II o finerenona."],["Tensión en casa","Tensión en consulta de 142 mmHg. Una semana de automedida con manguito validado."],["Preguntas sobre síntomas","Falta de aire al subir cuestas y dificultad para caminar, contestadas desde casa: afinan la sospecha de insuficiencia cardíaca antes de pedir el NT-proBNP."]],"alerts":[],"hr":1.01,"cv":{"score":0.0881,"probs":[0.0,0.9882,0.0118],"rec":1,"cat":1,"pUp":0.0118,"approx":false},"row":{"group":"medir","p":0.5909,"test":"creatinina","how":"punción capilar en casa o analítica"},"belief":{"pts":[[1.02,5e-05],[1.25,0.00013],[1.53,0.0004],[1.86,0.00187],[2.28,0.00885],[2.78,0.0287],[3.4,0.05684],[4.15,0.06746],[5.07,0.04979],[6.19,0.02703],[7.56,0.01639],[9.23,0.01389],[11.28,0.01279],[13.78,0.01102],[16.83,0.00869],[20.55,0.00632],[25.11,0.00431],[30.67,0.00286],[37.46,0.00195],[45.76,0.00145],[55.89,0.00121],[68.27,0.0011],[83.39,0.00105],[101.86,0.00102],[124.42,0.00098],[151.98,0.00093],[185.64,0.00087],[226.76,0.00081],[276.99,0.00073],[338.34,0.00065],[413.27,0.00057],[504.81,0.0005],[616.62,0.00042],[753.19,0.00035],[920.02,0.00029],[1123.79,0.00023],[1372.7,0.00019],[1676.73,0.00015],[2048.11,0.00011]],"median":4.6,"low":2.9,"high":16.6,"p2":0.0531}},
  marta: {"alb":{"status":"dudosa","label":"Dudosa","cat":"A1","p":[0.6612,0.3388,0.0001],"p2":0.3388,"median":24.4,"low":13.6,"high":43.0,"action":"Repetir en primera orina de la mañana, evitando ejercicio intenso, fiebre o infección de orina. Probabilidad de que resuelva la duda: 27% (con una muestra aleatoria, 22%).","chronic":false,"resolve":0.2655},"blood":{"egfr":[108.5,82.0,117.3,false,"estimado"],"hba1c":[7.4,7.4,7.4,true,"medido"],"potassium":[4.0,3.6,4.4,false,"estimado"],"non_hdl":[135.0,84.7,191.9,false,"estimado"],"nt_probnp":[36.7,8.4,114.6,false,"estimado"]},"pG60":0.0026,"joint":[[0.5529,0.2648,0.0001],[0.1072,0.0725,0.0001],[0.0011,0.0015,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.3399,"dm":"diagnosticada","pDm":null,"hf":"poco probable","pBnp":0.0782,"pAf":null,"pEf":null,"pNew":0.3399,"byTest":{"orina":0.3388,"creatinina":0.0026},"recs":[["UACR (primera orina de la mañana)","Repetir en primera orina de la mañana, evitando ejercicio intenso, fiebre o infección de orina. Probabilidad de que resuelva la duda: 27% (con una muestra aleatoria, 22%)."]],"alerts":[],"hr":0.81,"cv":{"score":0.0302,"probs":[0.0,0.9985,0.0015],"rec":1,"cat":1,"pUp":0.0015,"approx":false},"row":{"group":"medir","p":0.3399,"test":"orina","how":"kit de orina en casa (aplicación)"},"belief":{"pts":[[1.02,0.0],[1.25,0.0],[1.53,0.0],[1.86,0.0],[2.28,0.0],[2.78,4e-05],[3.4,0.0002],[4.15,0.00065],[5.07,0.00134],[6.19,0.00197],[7.56,0.00279],[9.23,0.00532],[11.28,0.01176],[13.78,0.02373],[16.83,0.03987],[20.55,0.05387],[25.11,0.05785],[30.67,0.0499],[37.46,0.03583],[45.76,0.02262],[55.89,0.01315],[68.27,0.00705],[83.39,0.00336],[101.86,0.00138],[124.42,0.00048],[151.98,0.00014],[185.64,4e-05],[226.76,1e-05],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":24.4,"low":13.4,"high":46.1,"p2":0.3492}},
  pilar: {"alb":{"status":"dudosa","label":"Dudosa","cat":"A1","p":[0.8768,0.1232,0.0001],"p2":0.1232,"median":18.5,"low":9.6,"high":30.6,"action":"Repetir en primera orina de la mañana, evitando ejercicio intenso, fiebre o infección de orina. Probabilidad de que resuelva la duda: 57% (con una muestra aleatoria, 52%).","chronic":false,"resolve":0.5747},"blood":{"egfr":[88.0,88.0,88.0,true,"medido"],"hba1c":[5.6,5.1,6.4,false,"estimado"],"potassium":[4.0,3.5,4.4,false,"estimado"],"non_hdl":[135.2,90.2,188.2,false,"estimado"],"nt_probnp":[62.7,25.1,155.0,false,"estimado"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.8768,0.1232,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.1232,"dm":"poco probable","pDm":0.0308,"hf":"poco probable","pBnp":0.1716,"pAf":null,"pEf":null,"pNew":0.1502,"byTest":{"orina":0.1232,"glucosa":0.0308},"recs":[["UACR (primera orina de la mañana)","Repetir en primera orina de la mañana, evitando ejercicio intenso, fiebre o infección de orina. Probabilidad de que resuelva la duda: 57% (con una muestra aleatoria, 52%)."],["Glucosa capilar en ayunas (en la farmacia o en casa)","P(diabetes sin diagnosticar) estimada: 3%. Una medida de glucosa lo aclara casi siempre sin análisis."]],"alerts":[],"hr":0.53,"cv":{"score":0.0273,"probs":[1.0,0.0001,0.0],"rec":0,"cat":0,"pUp":0.0001,"approx":false},"row":{"group":"medir","p":0.1502,"test":"orina","how":"kit de orina en casa (aplicación)"},"belief":{"pts":[[1.02,0.0],[1.25,0.0],[1.53,0.0],[1.86,0.0],[2.28,2e-05],[2.78,0.00017],[3.4,0.00088],[4.15,0.00278],[5.07,0.00546],[6.19,0.00721],[7.56,0.00797],[9.23,0.01161],[11.28,0.02323],[13.78,0.04276],[16.83,0.06099],[20.55,0.0652],[25.11,0.05205],[30.67,0.03123],[37.46,0.01432],[45.76,0.00522],[55.89,0.00162],[68.27,0.00046],[83.39,0.00012],[101.86,3e-05],[124.42,1e-05],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":18.5,"low":9.6,"high":30.6,"p2":0.1232}},
  antonio: {"alb":{"status":"sin_medir","label":"Sin medir","cat":"A1","p":[0.9133,0.0675,0.0192],"p2":0.0867,"median":4.9,"low":2.9,"high":24.2,"action":"Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 9%.","chronic":false,"resolve":0.8994},"blood":{"egfr":[75.0,51.3,89.5,false,"estimado"],"hba1c":[5.8,5.2,6.3,false,"estimado"],"potassium":[4.2,3.7,4.7,false,"estimado"],"non_hdl":[133.9,92.4,180.2,false,"estimado"],"nt_probnp":[199.9,88.3,3035.6,false,"estimado"]},"pG60":0.1557,"joint":[[0.0806,0.0026,0.0005],[0.7106,0.0388,0.0112],[0.0922,0.0151,0.0046],[0.023,0.0072,0.002],[0.0069,0.0038,0.001],[0.0,0.0,0.0]],"pCkd":0.2088,"dm":"poco probable","pDm":0.0341,"hf":"a descartar","pBnp":0.8258,"pAf":null,"pEf":null,"pNew":0.2358,"byTest":{"orina":0.0867,"creatinina":0.1557,"lípidos":0.0,"glucosa":0.0341},"recs":[["UACR (primera orina de la mañana)","Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 9%."],["Creatinina (FG)","P(FG < 60) estimada: 16%; hay que medirlo para estadificar la ERC."],["Glucosa capilar en ayunas (en la farmacia o en casa)","P(diabetes sin diagnosticar) estimada: 3%. Una medida de glucosa lo aclara casi siempre sin análisis."],["NT-proBNP","P(NT-proBNP ≥ 125) estimada: 83%; si sale alto, ecocardiograma."],["Tensión en casa","Tensión en consulta de 150 mmHg. Una semana de automedida con manguito validado."],["Preguntas sobre síntomas","Falta de aire al subir cuestas y dificultad para caminar, contestadas desde casa: afinan la sospecha de insuficiencia cardíaca antes de pedir el NT-proBNP."]],"alerts":[],"hr":0.94,"cv":{"score":0.192,"probs":[0.0,0.0195,0.9805],"rec":2,"cat":2,"pUp":0.0,"approx":true},"row":{"group":"medir","p":0.2358,"test":"creatinina","how":"punción capilar en casa o analítica"},"belief":{"pts":[[1.02,3e-05],[1.25,6e-05],[1.53,0.00018],[1.86,0.00066],[2.28,0.00335],[2.78,0.01417],[3.4,0.03884],[4.15,0.06424],[5.07,0.06418],[6.19,0.0416],[7.56,0.02267],[9.23,0.01595],[11.28,0.01443],[13.78,0.01304],[16.83,0.01081],[20.55,0.00816],[25.11,0.00565],[30.67,0.00364],[37.46,0.00224],[45.76,0.0014],[55.89,0.00095],[68.27,0.00074],[83.39,0.00065],[101.86,0.00061],[124.42,0.00058],[151.98,0.00056],[185.64,0.00053],[226.76,0.00049],[276.99,0.00045],[338.34,0.00041],[413.27,0.00036],[504.81,0.00032],[616.62,0.00027],[753.19,0.00023],[920.02,0.00019],[1123.79,0.00016],[1372.7,0.00013],[1676.73,0.0001],[2048.11,8e-05]],"median":5.2,"low":3.3,"high":16.8,"p2":0.0419}},
  francisco: {"alb":{"status":"descartada","label":"Descartada","cat":"A1","p":[0.9997,0.0003,0.0001],"p2":0.0003,"median":7.2,"low":3.7,"high":11.8,"action":"Sin albuminuria. Repetir el cribado según la guía (anual en diabetes).","chronic":false,"resolve":null},"blood":{"egfr":[78.0,78.0,78.0,true,"medido"],"hba1c":[5.8,5.3,6.4,false,"estimado"],"potassium":[4.1,3.5,4.5,false,"estimado"],"non_hdl":[135.3,90.3,188.4,false,"estimado"],"nt_probnp":[56.2,18.4,229.5,false,"estimado"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.9997,0.0003,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0003,"dm":"poco probable","pDm":0.0704,"hf":"poco probable","pBnp":0.1712,"pAf":null,"pEf":null,"pNew":0.0704,"byTest":{"glucosa":0.0704},"recs":[["Glucosa capilar en ayunas (en la farmacia o en casa)","P(diabetes sin diagnosticar) estimada: 7%. Una medida de glucosa lo aclara casi siempre sin análisis."]],"alerts":[],"hr":0.37,"cv":{"score":0.0784,"probs":[0.0,1.0,0.0],"rec":1,"cat":1,"pUp":0.0,"approx":false},"row":{"group":"medir","p":0.0704,"test":"glucosa","how":"una medida en la farmacia, o con su glucómetro"},"belief":{"pts":[[1.02,0.0],[1.25,1e-05],[1.53,0.00011],[1.86,0.00067],[2.28,0.00297],[2.78,0.00894],[3.4,0.01863],[4.15,0.02929],[5.07,0.03874],[6.19,0.04816],[7.56,0.05881],[9.23,0.05955],[11.28,0.04108],[13.78,0.01851],[16.83,0.00587],[20.55,0.00149],[25.11,0.00035],[30.67,9e-05],[37.46,3e-05],[45.76,1e-05],[55.89,1e-05],[68.27,0.0],[83.39,0.0],[101.86,0.0],[124.42,0.0],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":7.2,"low":3.7,"high":11.8,"p2":0.0003}},
  dolores: {"alb":{"status":"sin_medir","label":"Sin medir","cat":"A1","p":[0.8217,0.1336,0.0447],"p2":0.1783,"median":7.9,"low":3.5,"high":93.0,"action":"Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 18%.","chronic":false,"resolve":0.7957},"blood":{"egfr":[66.0,66.0,66.0,true,"medido"],"hba1c":[7.6,7.6,7.6,true,"medido"],"potassium":[4.0,3.4,4.5,false,"estimado"],"non_hdl":[131.6,83.2,185.2,false,"estimado"],"nt_probnp":[103.1,29.6,428.7,false,"estimado"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.8217,0.1336,0.0447],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.1783,"dm":"diagnosticada","pDm":null,"hf":"a descartar","pBnp":0.4277,"pAf":null,"pEf":null,"pNew":0.1783,"byTest":{"orina":0.1783},"recs":[["UACR (primera orina de la mañana)","Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: 18%."],["NT-proBNP","P(NT-proBNP ≥ 125) estimada: 43%; si sale alto, ecocardiograma."],["Preguntas sobre síntomas","Falta de aire al subir cuestas y dificultad para caminar, contestadas desde casa: afinan la sospecha de insuficiencia cardíaca antes de pedir el NT-proBNP."]],"alerts":[],"hr":0.71,"cv":{"score":0.0956,"probs":[0.0,0.9553,0.0447],"rec":1,"cat":1,"pUp":0.0447,"approx":false},"row":{"group":"medir","p":0.1783,"test":"orina","how":"kit de orina en casa (aplicación)"},"belief":{"pts":[[1.02,0.0001],[1.25,0.00019],[1.53,0.00039],[1.86,0.00099],[2.28,0.00334],[2.78,0.011],[3.4,0.02594],[4.15,0.03915],[5.07,0.03854],[6.19,0.02902],[7.56,0.02287],[9.23,0.02158],[11.28,0.02102],[13.78,0.01915],[16.83,0.01608],[20.55,0.01257],[25.11,0.00938],[30.67,0.00693],[37.46,0.00532],[45.76,0.00441],[55.89,0.00397],[68.27,0.00378],[83.39,0.00369],[101.86,0.00362],[124.42,0.00352],[151.98,0.00337],[185.64,0.00318],[226.76,0.00296],[276.99,0.0027],[338.34,0.00243],[413.27,0.00215],[504.81,0.00187],[616.62,0.0016],[753.19,0.00135],[920.02,0.00112],[1123.79,0.00091],[1372.7,0.00073],[1676.73,0.00058],[2048.11,0.00045]],"median":7.9,"low":3.5,"high":93.0,"p2":0.1783}},
  andres: {"alb":{"status":"descartada","label":"Descartada","cat":"A1","p":[0.9933,0.0066,0.0001],"p2":0.0067,"median":12.4,"low":4.6,"high":19.1,"action":"Sin albuminuria. Repetir el cribado según la guía (anual en diabetes).","chronic":false,"resolve":null},"blood":{"egfr":[74.0,74.0,74.0,true,"medido"],"hba1c":[5.7,5.3,6.4,false,"estimado"],"potassium":[4.1,3.6,4.6,false,"estimado"],"non_hdl":[128.4,86.7,181.1,false,"estimado"],"nt_probnp":[59.0,32.6,206.1,false,"estimado"]},"pG60":0.0,"joint":[[0.0,0.0,0.0],[0.9933,0.0066,0.0001],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,0.0]],"pCkd":0.0067,"dm":"poco probable","pDm":0.0594,"hf":"a descartar","pBnp":0.2402,"pAf":null,"pEf":0.0809,"pNew":0.1354,"byTest":{"glucosa":0.0594,"ecocardiograma":0.0809},"recs":[["Glucosa capilar en ayunas (en la farmacia o en casa)","P(diabetes sin diagnosticar) estimada: 6%. Una medida de glucosa lo aclara casi siempre sin análisis."],["Ecocardiograma","P(fracción de eyección ≤ 40 %) tras la grabación del corazón en casa: 8%. Pedir antes el NT-proBNP si hay lista de espera: si sale alto, el ecocardiograma es preferente."]],"alerts":[],"hr":0.96,"cv":{"score":0.0835,"probs":[0.0,1.0,0.0],"rec":1,"cat":1,"pUp":0.0,"approx":false},"row":{"group":"medir","p":0.1354,"test":"ecocardiograma","how":"cardiología o ecógrafo de bolsillo en el centro"},"belief":{"pts":[[1.02,0.0],[1.25,1e-05],[1.53,5e-05],[1.86,0.00034],[2.28,0.00161],[2.78,0.00507],[3.4,0.01036],[4.15,0.0139],[5.07,0.01329],[6.19,0.01198],[7.56,0.01637],[9.23,0.03228],[11.28,0.05816],[13.78,0.07288],[16.83,0.05697],[20.55,0.0277],[25.11,0.00911],[30.67,0.00236],[37.46,0.00059],[45.76,0.00017],[55.89,6e-05],[68.27,3e-05],[83.39,2e-05],[101.86,1e-05],[124.42,1e-05],[151.98,0.0],[185.64,0.0],[226.76,0.0],[276.99,0.0],[338.34,0.0],[413.27,0.0],[504.81,0.0],[616.62,0.0],[753.19,0.0],[920.02,0.0],[1123.79,0.0],[1372.7,0.0],[1676.73,0.0],[2048.11,0.0]],"median":12.4,"low":4.6,"high":19.1,"p2":0.0067}},
}

// Cuerpos de las peticiones en vivo: los mismos datos con los que se calculó la copia.
const LIVE = {
  julian: {"assess":{"age":62,"female":false,"bmi":29.5,"waist":104,"sbp":146,"dbp":88,"hypertension":true,"bp_meds":true,"high_cholesterol":true,"cholesterol_meds":true,"smoker_ever":true,"measured":{"total_cholesterol":205,"hdl":46},"urine_samples":[{"kind":"tira","date":"2026-07-14","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-07-15","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-07-16","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-02","albumin_mg_l":80,"creatinine_mg_dl":100}],"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":62,"female":false,"diabetes":false},"samples":[{"kind":"tira","date":"2026-07-14","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-07-15","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-07-16","albumin_mg_l":80,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-02","albumin_mg_l":80,"creatinine_mg_dl":100}],"as_of":"2026-11-16"},"trend":{"age":62,"female":false,"diabetes":false,"p_a2":0.9864,"p_a3":0.0001,"measurements":[{"date":"2021-03-15","egfr":96},{"date":"2022-04-20","egfr":94},{"date":"2023-05-08","egfr":93},{"date":"2024-05-06","egfr":90}],"as_of":"2026-11-16"}},
  marta: {"assess":{"age":47,"female":true,"bmi":31.0,"waist":99,"sbp":128,"dbp":80,"diabetes":true,"diabetes_pills":true,"measured":{"hba1c":7.4,"total_cholesterol":190,"hdl":52},"urine_samples":[{"kind":"tira","date":"2026-11-13","albumin_mg_l":30,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-14","albumin_mg_l":30,"creatinine_mg_dl":50}],"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":47,"female":true,"diabetes":true},"samples":[{"kind":"tira","date":"2026-11-13","albumin_mg_l":30,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-14","albumin_mg_l":30,"creatinine_mg_dl":50}],"as_of":"2026-11-16"}},
  pilar: {"assess":{"age":58,"female":true,"bmi":26.0,"waist":86,"sbp":128,"dbp":79,"measured":{"egfr":88,"total_cholesterol":212,"hdl":61},"urine_samples":[{"kind":"tira","date":"2026-11-12","albumin_mg_l":30,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-13","albumin_mg_l":30,"creatinine_mg_dl":100}],"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":58,"female":true,"diabetes":false,"egfr":88},"samples":[{"kind":"tira","date":"2026-11-12","albumin_mg_l":30,"creatinine_mg_dl":100},{"kind":"tira","date":"2026-11-13","albumin_mg_l":30,"creatinine_mg_dl":100}],"as_of":"2026-11-16"}},
  antonio: {"assess":{"age":81,"female":false,"bmi":27.5,"sbp":150,"dbp":72,"hypertension":true,"bp_meds":true,"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":81,"female":false,"diabetes":false},"samples":[],"as_of":"2026-11-16"}},
  francisco: {"assess":{"age":66,"female":false,"bmi":31.0,"waist":108,"sbp":134,"dbp":82,"hypertension":true,"bp_meds":true,"high_cholesterol":true,"cholesterol_meds":true,"smoker_ever":true,"measured":{"egfr":78,"total_cholesterol":196,"hdl":41},"urine_samples":[{"kind":"laboratorio","date":"2026-09-22","uacr":9.0,"sample_type":"first_morning","creatinine_mg_dl":110}],"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":66,"female":false,"diabetes":false,"egfr":78},"samples":[{"kind":"laboratorio","date":"2026-09-22","uacr":9.0,"sample_type":"first_morning","creatinine_mg_dl":110}],"as_of":"2026-11-16"}},
  dolores: {"assess":{"age":69,"female":true,"bmi":30.0,"waist":98,"sbp":136,"dbp":80,"diabetes":true,"diabetes_pills":true,"hypertension":true,"bp_meds":true,"measured":{"egfr":66,"hba1c":7.6,"total_cholesterol":190,"hdl":50},"as_of":"2026-11-16"},"albuminuria":{"patient":{"age":69,"female":true,"diabetes":true,"egfr":66},"samples":[],"as_of":"2026-11-16"}},
}
