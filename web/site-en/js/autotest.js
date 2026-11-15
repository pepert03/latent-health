// Smoke test for the patient app. Loads only with ?auto=<final tab> in the URL.
// Walks through Pilar's case by itself (borderline strip, repeat, tube, tube, repeat in three months),
// asks the assistant and leaves the result in document.title as "AUTO:{json}".
const params = new URLSearchParams(location.search)
const finalTab = params.get('auto') || 'registro'
const log = []
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
addEventListener('error', (event) => log.push(`ERROR ${event.message}`))
addEventListener('unhandledrejection', (event) => log.push(`ERROR ${event.reason}`))

async function find(selector) {
  for (let i = 0; i < 160; i++) {
    const el = document.querySelector(selector)
    if (el) return el
    await sleep(50)
  }
  throw new Error(`${selector} never appeared`)
}

async function click(selector) {
  const el = await find(selector)
  el.click()
  await sleep(450)
}

const title = () => document.querySelector('#app-view h3')?.textContent ?? '?'

async function test(kind, a, b) {
  await click('[data-act="advance"]')
  await click('[data-act="begin"]')
  // The assistant asks one thing at a time: answer "No" to everything.
  for (let i = 0; i < 6; i++) {
    const next = await find('[data-act="qa"][data-v="no"]:not([disabled]), [data-act="answers"]')
    if (next.dataset.act === 'answers') break
    next.click()
    await sleep(950)
  }
  await click('[data-act="answers"]')
  if (kind === 'tira') {
    await click(`#app-pick-a button[data-v="${a}"]`)
    await click(`#app-pick-c button[data-v="${b}"]`)
    await click('[data-act="strip"]')
  } else {
    await click(`[data-act="tube"][data-v="${a}"]`)
  }
  await find('[data-act="home"]')
  log.push(`${kind} ${a}${b ? `/${b}` : ''} -> ${title()}`)
  await click('[data-act="home"]')
}

async function run() {
  await find('#app-view h3') // the app has already talked to the model
  log.push(`start -> ${title()}`)
  await test('tira', 30, 100)
  await test('tira', 30, 50)
  await test('tubo', 58)
  await test('tubo', 64)
  log.push(`reminder -> ${document.querySelector('#app-view .when')?.textContent}`)
  await click('#app-tabs [data-tab="chat"]')
  await click('[data-act="idea"]')
  for (let i = 0; i < 400 && document.querySelector('.msg.wait'); i++) await sleep(100)
  log.push(`chat -> ${document.querySelector('.chat-log .msg:last-child')?.textContent.slice(0, 90)}`)
  if (finalTab === 'medico') {
    await click('#app-tabs [data-tab="medico"]')
    await click('[data-act="callme"]')
  } else if (finalTab !== 'chat') {
    await click(`#app-tabs [data-tab="${finalTab}"]`)
  }
  await sleep(600)
  document.querySelector('#app').scrollIntoView()
}

run()
  .catch((error) => log.push(`ERROR ${error.message}`))
  .finally(() => {
    document.title = `AUTO:${JSON.stringify(log)}`
  })
