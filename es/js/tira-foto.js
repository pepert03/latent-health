/*
  LatentHealth · la «foto» que ve la cámara del móvil: la tira mojada puesta en la plantilla de color,
  sobre una mesa de cocina de roble claro con luz de ventana. Móvil en la mano a unos 20 cm, inclinado
  unos 10° y girado unos 4°. Es una imagen fija: se acumulan muestras con la lente desplazada
  (profundidad de campo), la luz movida por el hueco de la ventana (sombras blandas) y un leve
  desplazamiento de píxel (antialias); al final, viñeteo, una pizca de aberración cromática y ruido de
  sensor. La tira y la plantilla son las mismas piezas que el kit 3D (tira.js y plantilla.js).

  import { renderStripPhoto } from './js/tira-foto.js'
  const { canvas, dataURL, puntos } = await renderStripPhoto(el, { samples: 128, blanca: false })

  blanca: true pinta las almohadillas en blanco (#ffffff) para teñirlas después con mix-blend-mode:
  multiply; el resto de la imagen sale idéntica. `puntos` trae las posiciones en la foto (0-1, origen
  arriba a la izquierda) de lo que busca la app: marcas, esquinas de la plantilla y de la tira (punta
  izquierda, punta derecha, mango derecha, mango izquierda), almohadillas y parches.
*/
import * as THREE from '../vendor/three/build/three.module.min.js'
import { TIRA, DEMO } from './tira.js'
import { PLANTILLA } from './plantilla.js'
import {
  rng,
  valueNoise,
  loadKitFonts,
  makeCanvas,
  stripCanvas,
  templateCanvas,
  stripShadowCanvas,
  buildStrip,
  buildTemplate,
  stripOnTemplate,
  stripLocal,
  tplLocal,
  padRect,
  STRIP,
  SACHET,
  sachetMaterial,
  buildSachet,
  contactShadows,
} from './kit3d.js'

const DEG = Math.PI / 180

/**
 * Roble claro en tablas a lo largo de x, sin repetir: veta recta casi paralela que ondula muy despacio,
 * fibras finas estiradas, poros y la junta entre tablas.
 */
function woodCanvas(S = 2048, cm = 40, seed = 3) {
  const rand = rng(seed)
  const slow = valueNoise(rand, 64)
  const fib = valueNoise(rand, 1024)
  const tint = valueNoise(rand, 32)
  const c = makeCanvas(S, S)
  const ctx = c.getContext('2d')
  const img = ctx.createImageData(S, S)
  const d = img.data
  const plankW = 11 // cm
  const planks = Math.ceil(cm / plankW) + 1
  const shift = Array.from({ length: planks }, () => rand() * 50)
  const tone = Array.from({ length: planks }, () => (rand() - 0.5) * 0.12)
  const lines = Array.from({ length: planks }, () => 16 + rand() * 10) // vetas por tabla
  const light = [239, 226, 204]
  const dark = [201, 172, 132]
  for (let y = 0; y < S; y++) {
    const ycm = (y / S) * cm
    const pi = Math.floor(ycm / plankW)
    const pf = ycm / plankW - pi
    for (let x = 0; x < S; x++) {
      const xcm = (x / S) * cm + shift[pi]
      // la veta: líneas finas casi paralelas, con una ondulación lenta y suave
      const w = (slow(xcm * 0.09, pf * 1.5 + pi * 3.1) - 0.5) * 1.6 + (slow(xcm * 0.5 + 9, pf * 4 + pi) - 0.5) * 0.25
      const r = pf * lines[pi] + w
      const t = r - Math.floor(r)
      const line = Math.exp(-((t - 0.5) ** 2) / (2 * 0.05 * 0.05)) * 0.65 + Math.exp(-((t - 0.38) ** 2) / (2 * 0.16 * 0.16)) * 0.22
      // fibras: ruido muy estirado a lo largo de la tabla
      const f = fib(xcm * 0.9, ycm * 38) - 0.5
      const g = tint(xcm * 0.12, ycm * 0.12) - 0.5
      let k = 0.12 + line * 0.5 + f * 0.32 + g * 0.18 + tone[pi]
      if (rand() < 0.004) k += 0.35 // poros
      const edge = Math.min(pf, 1 - pf) * plankW
      if (edge < 0.04) k = 1.25
      else if (edge < 0.1) k += 0.18
      k = Math.max(0, Math.min(1.3, k))
      const i = (y * S + x) * 4
      d[i] = light[0] + (dark[0] - light[0]) * k
      d[i + 1] = light[1] + (dark[1] - light[1]) * k
      d[i + 2] = light[2] + (dark[2] - light[2]) * k
      d[i + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
  return c
}

/** Fibras finas del papel de la plantilla (relieve, tesela que se repite). */
function paperBump(S = 512, seed = 9) {
  const rand = rng(seed)
  const n = valueNoise(rand, 128)
  const c = makeCanvas(S, S)
  const ctx = c.getContext('2d')
  const img = ctx.createImageData(S, S)
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      const v = 128 + 50 * (n((x / S) * 128, (y / S) * 128) - 0.5) + 26 * (rand() - 0.5)
      const i = (y * S + x) * 4
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v
      img.data[i + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
  return c
}

/** Cocina para los reflejos: paredes cálidas, una ventana grande a la izquierda y una lámpara. */
function kitchenEnv() {
  const env = new THREE.Scene()
  const room = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial({ color: '#a9a297', side: THREE.BackSide }))
  room.scale.set(420, 260, 420)
  room.position.y = 90
  env.add(room)
  const panel = (scalar, w, h, pos, look, tint) => {
    const m = new THREE.MeshBasicMaterial({ color: tint, side: THREE.DoubleSide })
    m.color.multiplyScalar(scalar)
    const p = new THREE.Mesh(new THREE.PlaneGeometry(w, h), m)
    p.position.set(...pos)
    p.lookAt(...look)
    env.add(p)
  }
  panel(6.5, 150, 110, [-205, 110, -30], [0, 60, -30], '#f3f6fb') // ventana
  panel(1.6, 60, 60, [20, 218, 10], [20, 0, 10], '#fff1df') // lámpara
  panel(0.9, 160, 90, [205, 80, 0], [0, 60, 0], '#efe8de') // pared de enfrente
  const dispose = () => env.traverse((o) => (o.geometry?.dispose(), o.material?.dispose()))
  return { env, dispose }
}

function halton(i, b) {
  let f = 1
  let r = 0
  while (i > 0) {
    f /= b
    r += f * (i % b)
    i = Math.floor(i / b)
  }
  return r
}

const FULLSCREEN_VS = 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }'

/**
 * Dibuja la foto en `container` y devuelve { canvas, dataURL, puntos } cuando termina.
 * opts: samples (128), blanca (false), width/height (900 × 1200), seed, tilt (°), roll (°), dist (cm),
 * fill (fracción del alto que ocupa la plantilla).
 */
export async function renderStripPhoto(container, opts = {}) {
  const o = { samples: 128, blanca: false, width: 900, height: 1200, seed: 7, tilt: 10, roll: 4, dist: 20, fill: 0.75, ...opts }
  await loadKitFonts()
  const W = Math.round(o.width)
  const H = Math.round(o.height)

  const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false, preserveDrawingBuffer: true })
  renderer.setPixelRatio(1)
  renderer.setSize(W, H, false)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.NeutralToneMapping
  renderer.toneMappingExposure = o.exposure ?? 1.15
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  const canvas = renderer.domElement
  canvas.setAttribute('aria-hidden', 'true')
  canvas.style.display = 'block'
  canvas.style.width = '100%'
  canvas.style.height = '100%'
  container.appendChild(canvas)
  const aniso = renderer.capabilities.getMaxAnisotropy()
  const textures = []
  const tex = (c, { srgb = true } = {}) => {
    const t = new THREE.CanvasTexture(c)
    if (srgb) t.colorSpace = THREE.SRGBColorSpace
    t.anisotropy = aniso
    textures.push(t)
    return t
  }

  const pads = o.blanca ? { a: '#ffffff', c: '#ffffff' } : DEMO
  const [stripC, tplC] = await Promise.all([stripCanvas(pads, 2048), templateCanvas(1200, { clean: true })])

  const scene = new THREE.Scene()
  scene.background = new THREE.Color('#d8cdb8')
  const pmrem = new THREE.PMREMGenerator(renderer)
  const kitchen = kitchenEnv()
  const envRT = pmrem.fromScene(kitchen.env, 0.03, 1, 1000)
  kitchen.dispose()
  pmrem.dispose()
  scene.environment = envRT.texture
  scene.environmentIntensity = o.ambient ?? 0.4

  // ── Mesa de roble claro ──
  const WOOD_CM = 40
  const woodC = woodCanvas(2048, WOOD_CM, o.seed + 3)
  const wood = tex(woodC)
  const woodBump = tex(woodC, { srgb: false })
  const table = new THREE.Mesh(
    new THREE.PlaneGeometry(WOOD_CM, WOOD_CM).rotateX(-Math.PI / 2),
    new THREE.MeshPhysicalMaterial({ map: wood, bumpMap: woodBump, bumpScale: 0.4, roughness: 0.58, clearcoat: 0.2, clearcoatRoughness: 0.42 }),
  )
  table.rotation.y = 9 * DEG
  table.position.set(1.5, 0, 0)
  table.receiveShadow = true
  scene.add(table)

  // ── Plantilla con la tira puesta ──
  const tplMap = tex(tplC)
  const pb = tex(paperBump(512, o.seed), { srgb: false })
  pb.wrapS = pb.wrapT = THREE.RepeatWrapping
  pb.repeat.set(5, (5 * PLANTILLA.h) / PLANTILLA.w)
  const template = buildTemplate(
    { empty: tplMap, clean: tplMap },
    { roughness: 0.86, bumpMap: pb, bumpScale: 0.25, shadowTexture: tex(stripShadowCanvas(), { srgb: false }), shadowOpacity: 0.2 },
  )
  template.userData.stripOn(1)
  scene.add(template)

  const stripMap = tex(stripC)
  const strip = buildStrip({ seca: stripMap, demo: stripMap }, { padRoughness: 0.5 })
  const on = stripOnTemplate()
  strip.position.copy(on.pos)
  strip.quaternion.copy(on.q)
  template.add(strip)

  // ── El sobre abierto, asomando por el borde de la derecha, y el trozo rasgado ──
  const mSachet = sachetMaterial(tex)
  const sachet = buildSachet(mSachet)
  sachet.body.position.set(5.9, 0.075, 2.4)
  sachet.body.rotation.y = 78 * DEG
  scene.add(sachet.body)
  sachet.tear.position.set(5.2, 0.03, -3.4)
  sachet.tear.rotation.set(0, 118 * DEG, 0)
  scene.add(sachet.tear)

  // ── Luz de la ventana (área: se mueve en cada muestra) y relleno de la habitación ──
  // Cae con la distancia (decay 2): a metro y medio, la mesa se oscurece algo hacia la derecha.
  const keyBase = new THREE.Vector3(-115, 82, -26)
  const d0 = keyBase.length()
  const key = new THREE.SpotLight('#fbfcff', (o.key ?? 3.6) * d0 * d0, 0, 0.36, 1, 2)
  key.position.copy(keyBase)
  key.target.position.set(-6, 0, -5)
  key.castShadow = true
  key.shadow.mapSize.set(4096, 4096)
  key.shadow.camera.near = 60
  key.shadow.camera.far = 260
  key.shadow.bias = -0.00004
  key.shadow.normalBias = 0.004
  key.shadow.radius = 2
  scene.add(key, key.target)

  const contact = contactShadows(renderer, {
    size: 40,
    res: 1024,
    height: 0.6,
    darkness: 1.1,
    y: 0.001,
    layers: [
      { blur: 0.06, opacity: 0.32 },
      { blur: 0.5, opacity: 0.22, res: 512, passes: 3 },
    ],
  })
  scene.add(contact.group)
  scene.updateMatrixWorld(true)
  contact.update(scene, [table])

  // ── Cámara del móvil: a `dist` cm, inclinada `tilt` y girada `roll` ──
  const camera = new THREE.PerspectiveCamera(40, W / H, 2, 300)
  const target = new THREE.Vector3(0.15, 0, 0.25)
  const tilt = o.tilt * DEG
  const roll = o.roll * DEG
  camera.position.set(target.x, o.dist * Math.cos(tilt), target.z + o.dist * Math.sin(tilt))
  camera.up.set(Math.sin(roll), 0, -Math.cos(roll))
  camera.lookAt(target)
  camera.updateMatrixWorld()
  const corner = (tx, ty) => tplLocal(tx, ty).applyMatrix4(template.matrixWorld)
  const cardPts = [
    [0, 0],
    [PLANTILLA.w, 0],
    [PLANTILLA.w, PLANTILLA.h],
    [0, PLANTILLA.h],
  ].map(([x, y]) => corner(x, y))
  // campo de visión para que la plantilla ocupe `fill` del alto
  let lo = 8
  let hi = 100
  const v = new THREE.Vector3()
  for (let i = 0; i < 40; i++) {
    camera.fov = (lo + hi) / 2
    camera.updateProjectionMatrix()
    let y0 = Infinity
    let y1 = -Infinity
    for (const p of cardPts) {
      v.copy(p).project(camera)
      y0 = Math.min(y0, v.y)
      y1 = Math.max(y1, v.y)
    }
    if ((y1 - y0) / 2 > o.fill) lo = camera.fov
    else hi = camera.fov
  }
  camera.fov = hi
  camera.updateProjectionMatrix()

  // ── Puntos para la app: proyectados con la cámara central (sin desplazar la lente) ──
  scene.updateMatrixWorld(true)
  const toImg = (p) => {
    v.copy(p).project(camera)
    return [+((v.x + 1) / 2).toFixed(5), +((1 - v.y) / 2).toFixed(5)]
  }
  const onTpl = (tx, ty) => toImg(corner(tx, ty))
  const onStrip = (sx, sy, y = STRIP.t) => toImg(stripLocal(sx, sy, y).applyMatrix4(strip.matrixWorld))
  const padTop = STRIP.t + STRIP.pad
  const padInfo = (key) => {
    const [x0, y0, x1, y1] = padRect(key)
    return {
      centro: onStrip((x0 + x1) / 2, (y0 + y1) / 2, padTop),
      // punta izquierda, punta derecha, mango derecha, mango izquierda
      esquinas: [onStrip(x1, y0, padTop), onStrip(x1, y1, padTop), onStrip(x0, y1, padTop), onStrip(x0, y0, padTop)],
    }
  }
  const pa = padInfo('a')
  const pc = padInfo('c')
  const puntos = {
    imagen: { ancho: W, alto: H },
    nota: 'Coordenadas normalizadas (0-1, origen arriba a la izquierda). Esquinas: punta/arriba izquierda, punta/arriba derecha, mango/abajo derecha, mango/abajo izquierda.',
    marcas: PLANTILLA.marcas.map(([x, y]) => onTpl(x, y)),
    plantilla: [
      [0, 0],
      [PLANTILLA.w, 0],
      [PLANTILLA.w, PLANTILLA.h],
      [0, PLANTILLA.h],
    ].map(([x, y]) => onTpl(x, y)),
    tira: [onStrip(TIRA.w, 0), onStrip(TIRA.w, TIRA.h), onStrip(0, TIRA.h), onStrip(0, 0)],
    almohadillas: { a: pa.centro, c: pc.centro },
    esquinasAlmohadillas: { a: pa.esquinas, c: pc.esquinas },
    blanco: TIRA.blanco ? onStrip(TIRA.blanco[0], TIRA.blanco[1]) : undefined,
    parches: PLANTILLA.parches.map((p) => onTpl(p.x + p.w / 2, p.y + p.h / 2)),
  }

  // ── Acumulación ──
  const base = { pos: camera.position.clone(), quat: camera.quaternion.clone() }
  const right = new THREE.Vector3(1, 0, 0).applyQuaternion(base.quat)
  const up = new THREE.Vector3(0, 1, 0).applyQuaternion(base.quat)
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(base.quat)
  const focusDist = target.clone().sub(base.pos).dot(fwd)
  const lensR = o.lens ?? 0.05
  const near = camera.near
  const top0 = near * Math.tan((camera.fov * DEG) / 2)
  const right0 = top0 * camera.aspect

  const rtSample = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, depthBuffer: true })
  const floatBlend = renderer.extensions.has('EXT_float_blend')
  const rtAccum = new THREE.WebGLRenderTarget(W, H, { type: floatBlend ? THREE.FloatType : THREE.HalfFloatType, depthBuffer: false })
  const quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
  const quadGeo = new THREE.PlaneGeometry(2, 2)
  const accMat = new THREE.ShaderMaterial({
    uniforms: { t: { value: rtSample.texture }, w: { value: 1 / o.samples } },
    vertexShader: FULLSCREEN_VS,
    fragmentShader: 'uniform sampler2D t; uniform float w; varying vec2 vUv; void main() { gl_FragColor = vec4(texture2D(t, vUv).rgb * w, 1.0); }',
    blending: THREE.AdditiveBlending,
    depthTest: false,
    depthWrite: false,
    transparent: true,
    toneMapped: false,
  })
  const accQuad = new THREE.Mesh(quadGeo, accMat)
  accQuad.frustumCulled = false

  renderer.setRenderTarget(rtAccum)
  renderer.setClearColor(0x000000, 0)
  renderer.clear()
  const rand = rng(o.seed + 101)
  const ldir = keyBase.clone().normalize()
  const lu = new THREE.Vector3().crossVectors(ldir, new THREE.Vector3(0, 1, 0)).normalize()
  const lv = new THREE.Vector3().crossVectors(ldir, lu).normalize()
  for (let i = 0; i < o.samples; i++) {
    const r = Math.sqrt((i + 0.5) / o.samples) * lensR
    const a = i * 2.399963229728653
    const dx = r * Math.cos(a)
    const dy = r * Math.sin(a)
    camera.position.copy(base.pos).addScaledVector(right, dx).addScaledVector(up, dy)
    camera.quaternion.copy(base.quat)
    camera.updateMatrixWorld()
    const jx = (halton(i + 1, 2) - 0.5) * ((2 * right0) / W)
    const jy = (halton(i + 1, 3) - 0.5) * ((2 * top0) / H)
    const sx = (-dx * near) / focusDist + jx
    const sy = (-dy * near) / focusDist + jy
    camera.projectionMatrix.makePerspective(-right0 + sx, right0 + sx, top0 + sy, -top0 + sy, near, camera.far)
    camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert()
    // la ventana: un rectángulo de luz, más ancho que alto
    const wu = (rand() - 0.5) * 70
    const wv = (rand() - 0.5) * 40
    key.position.copy(keyBase).addScaledVector(lu, wu).addScaledVector(lv, wv)
    renderer.setRenderTarget(rtSample)
    renderer.setClearColor(0x000000, 1)
    renderer.clear()
    renderer.render(scene, camera)
    renderer.setRenderTarget(rtAccum)
    renderer.autoClear = false
    renderer.render(accQuad, quadCam)
    renderer.autoClear = true
  }

  // ── Revelado: viñeteo, aberración cromática leve, curva de tono y ruido de sensor ──
  const devMat = new THREE.ShaderMaterial({
    uniforms: { t: { value: rtAccum.texture }, seed: { value: (o.seed % 97) + 0.37 }, res: { value: new THREE.Vector2(W, H) } },
    vertexShader: FULLSCREEN_VS,
    fragmentShader: /* glsl */ `
      uniform sampler2D t; uniform float seed; uniform vec2 res; varying vec2 vUv;
      float hash(vec2 p) { p = fract(p * vec2(443.897, 441.423)); p += dot(p, p.yx + 19.19); return fract((p.x + p.y) * p.x); }
      void main() {
        vec2 d = vUv - 0.5;
        d.x *= res.x / res.y;
        float r2 = dot(d, d);
        vec2 ca = (vUv - 0.5) * 0.0009;
        vec3 col = vec3(texture2D(t, vUv - ca).r, texture2D(t, vUv).g, texture2D(t, vUv + ca).b);
        col *= 1.0 - 0.22 * r2;
        col *= vec3(1.015, 1.0, 0.975);
        gl_FragColor = vec4(col, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
        vec2 p = gl_FragCoord.xy;
        float n = hash(p + seed) + hash(p * 1.31 + seed * 3.7) - 1.0;
        float luma = dot(gl_FragColor.rgb, vec3(0.299, 0.587, 0.114));
        float amp = 0.022 * (1.1 - 0.55 * luma);
        vec3 chroma = vec3(hash(p + seed * 5.1) - 0.5, hash(p + seed * 7.3) - 0.5, hash(p + seed * 9.7) - 0.5) * 0.008;
        gl_FragColor.rgb += n * amp + chroma;
      }
    `,
    depthTest: false,
    depthWrite: false,
  })
  const devQuad = new THREE.Mesh(quadGeo, devMat)
  devQuad.frustumCulled = false
  renderer.setRenderTarget(null)
  renderer.render(devQuad, quadCam)
  const dataURL = canvas.toDataURL('image/png')

  // liberar lo que ya no hace falta (la imagen queda en el canvas)
  rtSample.dispose()
  rtAccum.dispose()
  contact.dispose()
  envRT.dispose()
  scene.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose()
    if (obj.material) [].concat(obj.material).forEach((m) => m.dispose())
  })
  textures.forEach((t) => t.dispose())
  accMat.dispose()
  devMat.dispose()
  quadGeo.dispose()
  return { canvas, dataURL, puntos }
}
