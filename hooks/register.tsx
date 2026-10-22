import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Corrida, Frame } from '../types'

const PANE = 'doom'
// tope por partida: Jev y Haiku cuestan tokens, que no se quede prendido si nadie mira
const MAX_MS = 10 * 60 * 1000

const frame = atom({ plugin: 'doom-pane', key: 'frame' } as const, null)
const bitacora = atom({ plugin: 'doom-pane', key: 'bitacora' } as const, [])
const activo = atom({ plugin: 'doom-pane', key: 'activo' } as const, false)

type Idioma = 'es' | 'en'

const TXT = {
  es: {
    language: 'in Mexican Spanish',
    loading: 'Cargando el infierno...',
    stopped: 'detenido (/doom para arrancar)',
    pilot: 'piloto',
    narrates: 'narra',
    mode: 'modo',
    goal: 'meta',
    plan: 'plan de Claude',
    danger: 'peligro',
    decisions: 'decisiones',
    errors: 'errores',
    startJev: 'Jev toma el volante, Claude narra...',
    startClaude: 'Claude toma el control...',
    running: 'Doom ya esta corriendo.',
    stoppedMsg: 'Doom detenido y panel cerrado.',
    okJev: 'Doom arrancado. Pilota Jev, narra Claude. /doom-stop para detenerlo.',
    okClaude: 'Doom arrancado. Pilota Claude (Haiku). /doom-stop para detenerlo.',
    noKey: 'Sin TypeSafe API key: pilota Claude. Ponla en /config para que pilote Jev.',
    needSetup: 'Primero corre /doom-setup (instala ViZDoom en un entorno de Python).',
    crashed: 'Doom se cayo',
    timeout: 'Doom se apago solo a los 10 minutos para no gastar tokens.',
    log: 'Bitacora de decisiones',
  },
  en: {
    language: 'in English',
    loading: 'Loading hell...',
    stopped: 'stopped (/doom to start)',
    pilot: 'pilot',
    narrates: 'narrator',
    mode: 'mode',
    goal: 'goal',
    plan: 'Claude plan',
    danger: 'danger',
    decisions: 'decisions',
    errors: 'errors',
    startJev: 'Jev takes the wheel, Claude narrates...',
    startClaude: 'Claude takes control...',
    running: 'Doom is already running.',
    stoppedMsg: 'Doom stopped and pane closed.',
    okJev: 'Doom started. Jev pilots, Claude narrates. /doom-stop to stop it.',
    okClaude: 'Doom started. Claude (Haiku) pilots. /doom-stop to stop it.',
    noKey: 'No TypeSafe API key: Claude pilots. Set it in /config to let Jev pilot.',
    needSetup: 'Run /doom-setup first (installs ViZDoom in a Python environment).',
    crashed: 'Doom crashed',
    timeout: 'Doom stopped itself after 10 minutes to save tokens.',
    log: 'Decision log',
  },
} as const

let corriendo = false
let generacion = 0
let tamano = ''
let idioma: Idioma = 'es'
let version = ''

// la version sale del plugin.json instalado, para saber que copia esta corriendo
async function leerVersion($: EngineInterface) {
  if (version) return version
  try {
    version = String(JSON.parse(await $.fs.read(`${$.plugin.root}/.claude-plugin/plugin.json`)).version ?? '?')
  } catch {
    version = '?'
  }
  return version
}

function detener() {
  corriendo = false
  generacion++
}

// Doom es 4:3 y cada celda trae dos pixeles en vertical: filas = cols * 3 / 8
function medir(columnas: number, renglones: number) {
  const libres = Math.max(6, renglones - 14)
  let cols = Math.max(16, Math.min(240, columnas - 2))
  let filas = Math.round((cols * 3) / 8)
  if (filas > libres) {
    filas = libres
    cols = Math.floor((filas * 8) / 3)
  }
  return { cols, filas }
}

// recorta una fila al ancho del panel para que no se parta en renglones
function recortar(fila: Corrida[], ancho: number) {
  const out: Corrida[] = []
  let usado = 0
  for (const [n, a, b] of fila) {
    if (usado >= ancho) break
    const k = Math.min(n, ancho - usado)
    out.push([k, a, b])
    usado += k
  }
  return out
}

// lo que el bridge nombra en espanol (modos, tacticas, metas), en el idioma del panel
const PALABRA_EN: Record<string, string> = {
  atacar: 'attack', explorar: 'explore', retirada: 'retreat', recoger: 'pick up', avanzar: 'advance',
  pelear: 'fight', esquivar: 'dodge',
}
const COLOR_EN: Record<string, string> = { roja: 'red', azul: 'blue', amarilla: 'yellow' }

function palabra(w: string | null | undefined) {
  if (!w) return '-'
  return idioma === 'en' ? (PALABRA_EN[w] ?? w) : w
}

// id interno de meta (llave_roja, interruptor_3...) -> texto corto
function nombreMeta(id: string | null | undefined) {
  if (!id) return '-'
  const [base, resto = ''] = id.split('_')
  if (idioma === 'en') {
    const en: Record<string, string> = {
      llave: `${COLOR_EN[resto] ?? resto} key`, interruptor: `switch ${resto}`, pisar: `walk-over line ${resto}`,
      municion: 'ammo', salud: 'health', arma: 'weapon', frontera: 'unexplored area', salida: 'exit',
    }
    return en[base] ?? id
  }
  const es: Record<string, string> = {
    llave: `llave ${resto}`, interruptor: `interruptor ${resto}`, pisar: `linea ${resto} al pisar`,
    municion: 'municion', salud: 'salud', arma: 'arma', frontera: 'zona sin explorar', salida: 'salida',
  }
  return es[base] ?? id
}

function probsTexto(probs: Record<string, number>) {
  return Object.entries(probs)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${palabra(k)} ${v.toFixed(2)}`)
    .join(' ')
}

// Rutas: el codigo vive en la carpeta del plugin; el entorno de Python y los
// archivos de intercambio en ~/.doom-pane, para que una actualizacion no los borre
async function rutas($: EngineInterface) {
  const esWindows = (await $.env.get('OS')) === 'Windows_NT'
  const home = ((await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? '.').replaceAll('\\', '/')
  const datos = `${home}/.doom-pane`
  const venv = `${datos}/venv`
  return {
    esWindows,
    datos,
    venv,
    python: esWindows ? `${venv}/Scripts/python.exe` : `${venv}/bin/python`,
    puente: `${$.plugin.root}/bridge/doom_bridge.py`,
    requisitos: `${$.plugin.root}/bridge/requirements.txt`,
    ordenes: `${datos}/orders.json`,
    logs: `${datos}/logs`,
    pantalla: `${datos}/screen.json`,
  }
}

export const register: Register = (on, options) => {
  const apiKey = String(options.typesafe_api_key ?? '').trim()
  idioma = options.language === 'en' ? 'en' : 'es'

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'doom',
      description: 'Doom in a pane. Options: "claude" (Haiku pilots), "en" / "es" (narration language)',
    })
    await $.command.register({ name: 'doom-stop', description: 'Stop Doom and close the pane' })
    await $.command.register({ name: 'doom-setup', description: 'Install ViZDoom in ~/.doom-pane/venv (one time)' })
    return next(e)
  })

  on('command.run', { command: 'doom-setup' }, async $ => {
    const r = await rutas($)
    const candidatos = r.esWindows ? [['py', '-3'], ['python'], ['python3']] : [['python3'], ['python']]
    let base: string[] | null = null
    for (const c of candidatos) {
      try {
        const v = await $.process.run([...c, '--version'])
        if (v.exitCode === 0) {
          base = c
          break
        }
      } catch {
        // no existe ese ejecutable: probar el siguiente
      }
    }
    if (!base) return { text: 'Python 3.9+ not found. Install it from python.org and run /doom-setup again.' }
    $.ui.toast('Creating Python environment...')
    const mk = await $.process.run([...base, '-m', 'venv', r.venv], { timeoutMs: 120000 })
    if (mk.exitCode !== 0) return { text: `venv failed:\n${mk.stderr.slice(-800)}` }
    $.ui.toast('Installing ViZDoom (can take a few minutes)...', { timeoutMs: 10000 })
    const pip = await $.process.run([r.python, '-m', 'pip', 'install', '-q', '-r', r.requisitos], { timeoutMs: 600000 })
    if (pip.exitCode !== 0) return { text: `pip install failed:\n${pip.stderr.slice(-1200)}` }
    return { text: `Ready. ViZDoom installed in ${r.venv}. Now run /doom` }
  })

  // cerrar el panel (X o Esc) tambien detiene el juego: si no, Jev y Haiku siguen gastando
  on('ui.close', async ($, e, next) => {
    if (e.id === PANE && corriendo) {
      detener()
      await update($, activo, () => false)
    }
    return next(e)
  })

  on('command.run', { command: 'doom-stop' }, async $ => {
    detener()
    await update($, activo, () => false)
    await $.ui.close({ id: PANE })
    return { text: TXT[idioma].stoppedMsg }
  })

  on('command.run', { command: 'doom' }, async ($, e) => {
    const palabras = e.args.trim().toLowerCase().split(/\s+/)
    if (palabras.includes('en')) idioma = 'en'
    if (palabras.includes('es')) idioma = 'es'
    const T = TXT[idioma]
    const v = await leerVersion($)
    const r = await rutas($)
    if (!(await $.fs.exists(r.python))) return { text: T.needSetup }

    await $.ui.open({ id: PANE, title: 'DOOM in Claude Code', focus: true, closeOnEscape: true })
    if (corriendo) return { text: T.running }
    const piloto = palabras.includes('claude') || !apiKey ? 'claude' : 'jev'
    corriendo = true
    const mia = ++generacion
    const inicio = await $.clock.now()
    const sello = new Date(inicio).toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15)
    const logJuego = `${r.logs}/match-${sello}.jsonl`
    const logClaude = `${r.logs}/match-${sello}-claude.json`
    const dichos: { t: number; piloto: string; modelo: string; frame: number; estado: string; respuesta: string }[] = []
    const planner = (await $.fs.read(`${$.plugin.root}/prompts/planner.md`)).replaceAll('{LANGUAGE}', T.language)
    // el rompecabezas del nivel llega en algunas lineas (cada ~5 s); se guarda el ultimo
    let resumen = ''
    await $.fs.write(r.ordenes, JSON.stringify({ plan: [] }))
    await update($, bitacora, () => [piloto === 'jev' ? T.startJev : T.startClaude])
    await update($, frame, () => null)
    await update($, activo, () => true)

    // Proceso del juego: lee stdout por lineas y se queda con el frame mas nuevo
    void (async () => {
      let resto = ''
      let pintando = false
      try {
        const juego = $.process.spawn({
          argv: [r.python, '-u', r.puente, '--ordenes', r.ordenes, '--pantalla', r.pantalla, '--piloto', piloto,
            '--log', logJuego, '--idioma', idioma],
          cwd: r.datos,
          env: piloto === 'jev' ? { TYPESAFE_API_KEY: apiKey } : {},
        })
        for await (const { stream, text } of juego) {
          if (!corriendo || mia !== generacion) break
          if (stream !== 'stdout') continue
          resto += text
          const partes = resto.split('\n')
          resto = partes.pop() ?? ''
          for (const p of partes) {
            if (p.includes('"resumen_mapa"')) {
              try {
                resumen = (JSON.parse(p) as Frame).resumen_mapa ?? resumen
              } catch {
                // linea cortada: se espera la siguiente
              }
            }
          }
          const ultima = partes.filter(p => p.startsWith('{')).pop()
          if (!ultima || pintando) continue
          pintando = true
          try {
            const f = JSON.parse(ultima) as Frame
            await update($, frame, () => f)
          } catch {
            // linea incompleta o corrupta: se ignora
          } finally {
            pintando = false
          }
        }
      } catch (err) {
        $.ui.toast(`${T.crashed}: ${String(err).slice(0, 120)}`)
      }
      if (mia === generacion) {
        corriendo = false
        await update($, activo, () => false)
      }
    })()

    // Haiku: planea el rompecabezas del nivel (orden de metas) y narra, cada ~6 s.
    // Escala a Sonnet en los momentos dificiles: cambio en el rompecabezas (mapa, llave,
    // interruptor, muerte) o 60 s sin avances. Lo demas es revision de rutina con Haiku.
    let huella = ''
    let ultimoAvance = inicio
    void (async () => {
      while (corriendo && mia === generacion) {
        await $.clock.sleep(6000)
        const ahora = await $.clock.now()
        if (ahora - inicio > MAX_MS) {
          detener()
          await update($, activo, () => false)
          $.ui.toast(T.timeout, { timeoutMs: 8000 })
          break
        }
        const f = await read($, frame)
        if (!f || !corriendo || mia !== generacion) continue
        const jev = f.jev
          ? `\nJev (fast pilot) right now: tactic ${probsTexto(f.jev.probs)}, goal ${f.jev.meta ?? 'unsure'}, danger ${f.jev.peligro}.`
          : ''
        const nueva = [
          f.mapa ?? '',
          f.estado.match(/Llaves: ([^.]*)/)?.[1] ?? '',
          f.estado.match(/Interruptores usados: (\d+)/)?.[1] ?? '',
          f.estado.match(/muertes (\d+)/)?.[1] ?? '',
        ].join('|')
        let modelo = 'haiku'
        if (nueva !== huella) {
          modelo = 'sonnet'
          huella = nueva
          ultimoAvance = ahora
        } else if (ahora - ultimoAvance > 60000) {
          modelo = 'sonnet'
          ultimoAvance = ahora
        }
        const resp = await $.model.complete({
          model: modelo,
          system: planner,
          prompt: `--- Level state ---\n${resumen || f.estado}\nCurrent goal: ${f.meta ?? 'none'}. Current plan: ${(f.plan ?? []).join(', ') || 'none'}.\n${f.estado}${jev}`,
          maxTokens: 200,
          effort: 'low',
        })
        if (!resp.isAnswered) continue
        dichos.push({ t: Math.round((ahora - inicio) / 100) / 10, piloto, modelo, frame: f.n, estado: f.estado, respuesta: resp.text })
        await $.fs.write(logClaude, JSON.stringify(dichos, null, 1))
        const m = resp.text.match(/\{[\s\S]*\}/)
        if (!m) continue
        try {
          const d = JSON.parse(m[0]) as { plan?: string[]; comentario?: string }
          if (Array.isArray(d.plan)) await $.fs.write(r.ordenes, JSON.stringify({ plan: d.plan.slice(0, 5) }))
          await update($, bitacora, b => [...b, d.comentario ?? ''].slice(-4))
        } catch {
          // respuesta que no es JSON: se ignora
        }
      }
    })()

    const aviso = (!apiKey && !palabras.includes('claude') ? `\n${T.noKey}` : '') + `\n${T.log}: ${logJuego}`
    return { text: `v${v} | ` + (piloto === 'jev' ? T.okJev : T.okClaude) + aviso }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const T = TXT[idioma]
    const f = await read($, frame)
    const b = await read($, bitacora)
    const vivo = await read($, activo)
    const ancho = Math.max(10, (e.viewport?.columns ?? 80) - 2)
    const t = medir(e.viewport?.columns ?? 82, e.viewport?.rows ?? 40)
    const clave = `${t.cols}x${t.filas}`
    if (clave !== tamano) {
      tamano = clave
      const r = await rutas($)
      await $.fs.write(r.pantalla, JSON.stringify(t))
    }
    const piloto = f?.piloto === 'claude' ? 'Claude (Haiku)' : 'Jev'

    return (
      <Box flexDirection="column">
        <Text bold wrap="truncate">
          DOOM v{version || '?'} | {f?.mapa ?? '-'} | {T.pilot}: {piloto} | {T.narrates}: Claude | {T.mode}: {palabra(f?.modo)}
          {vivo ? '' : ` | ${T.stopped}`}
        </Text>
        {f?.jev && (
          <Text color="cyan" wrap="truncate">
            Jev {f.jev.ms} ms | {probsTexto(f.jev.probs)} | {T.goal} {nombreMeta(f.jev.meta)} | {T.danger} {f.jev.peligro} | {f.jev.llamadas} {T.decisions}
            {f.jev.errores ? ` | ${f.jev.errores} ${T.errors}: ${f.jev.ultimo_error}` : ''}
          </Text>
        )}
        <Text color="magenta" wrap="truncate">
          {T.goal}: {f?.meta_ui ?? nombreMeta(f?.meta)} | {T.plan}: {(f?.plan_ui ?? (f?.plan ?? []).map(nombreMeta)).join(' > ') || '-'}
        </Text>
        {f ? (
          f.filas.map(fila => (
            <Text wrap="truncate">
              {recortar(fila, ancho).map(([n, arriba, abajo]) => (
                <Text color={arriba} backgroundColor={abajo}>
                  {'▀'.repeat(n)}
                </Text>
              ))}
            </Text>
          ))
        ) : (
          <Text dimColor>{T.loading}</Text>
        )}
        <Text dimColor wrap="truncate">
          {f?.estado_ui ?? f?.estado ?? ''}
        </Text>
        {b.map(l => (
          <Text color="yellow">{l}</Text>
        ))}
      </Box>
    )
  })
}
