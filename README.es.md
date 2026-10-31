# Doom en Claude Code

[English](README.md) | **Español**

Doom corriendo dentro de un panel de Claude Code, sin nadie en los controles. Tres piezas, cada una
en el trabajo que mejor hace:

- **El código** camina, apunta, abre puertas, llama elevadores y esquiva bolas de fuego. Lee el mapa
  real del WAD (puertas, llaves, interruptores, elevadores, teletransportes, salida) y calcula rutas
  con A*.
- **Jev** ([TypeSafe](https://typesafe.ai)) ve la pantalla real unas 2.5 veces por segundo (~150 ms
  por llamada) y elige qué meta perseguir (llave, interruptor, salida). También califica la táctica
  (pelear / esquivar / avanzar), que se ve en el panel, pero desde la 0.5.0 la pelea la decide el
  código: con la táctica de Jev moría más (MAP02 terminado 1 de 6 contra 3 de 6 con Jev solo en la meta).
- **Claude** resuelve el rompecabezas del nivel (qué llave abre qué, qué interruptor mueve qué
  puerta) y narra en vivo como streamer. Haiku hace la rutina; Sonnet entra cuando se pone difícil
  (inicio de mapa, muerte, un minuto sin avanzar). Usa tu propia sesión de Claude Code: no necesita
  otra API key.

¿Sin key de TypeSafe? Claude planea y el código juega.

El juego es [ViZDoom](https://github.com/Farama-Foundation/ViZDoom) con
[Freedoom](https://freedoom.github.io/) (contenido libre, licencia BSD), así que no hacen falta los
archivos originales de Doom.

## Cómo va

Solo código, con un juego aleatorio distinto por semilla y por vida (0.6.0):

| Mapa | Terminado | Qué pide |
| --- | --- | --- |
| MAP01 | 18 de 18 | el primer nivel: puertas y la salida |
| MAP02 | 24 de 24 | llave azul -> interruptores -> llave roja -> interruptores -> llave amarilla -> teletransporte -> salida |
| MAP03 | 24 de 24 | tres llaves, un elevador que baja al pisarlo, un piso de ácido, una salida que se cruza caminando |
| MAP04 | 23 de 24 | tres aplastadores, un elevador que mueve un interruptor aparte, una manada de Demons |
| MAP05 | explorado en parte | |

Cada paso se mide y queda en el [changelog](CHANGELOG.md) (en inglés), con los datos crudos en el
repo. Lo que sigue está en el [roadmap](ROADMAP.md).

## Instalación

En una sesión de Claude Code en la terminal:

```
/plugin install doom-pane --marketplace abelardodiaz/doom-in-claude-code
```

Desde una terminal normal:

```
claude plugin install doom-pane --marketplace abelardodiaz/doom-in-claude-code
```

Contesta `y` para agregar el marketplace, elige el alcance, y la pantalla de opciones te pide:

- **API key de TypeSafe** (opcional): con ella entra Jev. Se consigue en [typesafe.ai](https://typesafe.ai).
- **Idioma de la narración**: `es` o `en`. Las dos se cambian después en `/config`.

Luego, una sola vez:

```
/doom-setup
```

Busca Python 3.9 o mayor e instala ViZDoom, numpy, pillow, requests y omgifol en
`~/.doom-pane/venv`. No toca tu Python global.

## Jugar (bueno, mirar)

| Comando | Qué hace |
| --- | --- |
| `/doom` | Arranca el juego en un panel. Jev decide si hay key; Claude planea y narra |
| `/doom claude` | Sin Jev: Claude planea y el código juega |
| `/doom en` / `/doom es` | Idioma de la narración para esta partida |
| `/doom-stop` o `Esc` | Detiene el juego y cierra el panel |

El panel muestra el juego, los números de Jev (latencia, probabilidades, la meta que pide), la meta
actual con el plan de Claude, y la narración. La imagen se ajusta al tamaño del panel y conserva la
proporción 4:3 de Doom. Necesitas una terminal con color de 24 bits (Windows Terminal, iTerm2,
kitty, Ghostty, casi todas las de Linux) y unas 110 columnas.

Cerrar el panel detiene el juego, y una partida se apaga sola a los 10 minutos: Jev y Claude cuestan
tokens, así que nada se queda corriendo sin que nadie mire.

## Cómo funciona

- `bridge/doom_bridge.py`: corre el juego, los reflejos de combate, la imagen y la bitácora.
- `bridge/navegacion.py`: el mapa del WAD (omgifol) en una cuadrícula de 16x16; puertas, puertas de
  llave, puertas remotas que abre un interruptor o una línea al pisarla, elevadores, teletransportes;
  arma la lista de metas con ruta y camina hacia la elegida; comprueba que un interruptor de verdad
  movió algo.
- `bridge/jev_pilot.py`: una llamada a Jev con el frame (JPEG 448x336; Jev rechaza imágenes de menos
  de 280 px) y el estado en texto. Decide por la probabilidad más alta, pide una distancia de 0.2
  entre las dos primeras opciones (si no, decide el script) y baraja las opciones en cada llamada,
  porque Jev favorece la primera.
- `prompts/planner.md`: el prompt de Claude como planificador y narrador. Edítalo para cambiar la
  lógica del plan o la personalidad.
- `hooks/register.tsx`: el mod de Claude Code (panel, comandos, ciclo de Claude, escalamiento de modelo).
- `bridge/bench_reparto.py`: benchmark por columnas (solo código / + Jev / + Jev + Haiku / + Sonnet).
- `bridge/escena.py`: pone al bot en cualquier punto de un mapa con las llaves que quieras (trucos de
  consola) para depurar un lugar en segundos en vez de repetir miles de frames.

El código está comentado en español; la documentación está en inglés y español.

## Bitácora

Cada partida escribe `~/.doom-pane/logs/match-<hora>.jsonl` (decisiones de Jev con probabilidades y
latencia, eventos de navegación, kills, muertes con lo que había cerca, posición cada segundo) y
`match-<hora>-claude.json` (lo que Claude planeó y dijo, y qué modelo respondió).

## Costo

Jev con imagen son ~700 tokens de entrada por decisión, unas 2.5 decisiones por segundo: alrededor de
6 millones de tokens por hora de juego. Revisa el precio actual de TypeSafe. Las llamadas a Claude
cuentan contra tu propio uso de Claude Code (unos cientos de tokens cada ~6 s, más cuando entra Sonnet).

## Límites conocidos

- El combate es el punto débil: el bot pelea hasta morir en vez de retirarse o curarse.
- Un panel grande son más celdas de color por frame. Si se traba, achica el panel.
- Probado en Windows 11 con Python 3.14. Linux y macOS deberían funcionar (ViZDoom tiene versiones
  para ambos), pero todavía no están probados.

## Recrearlo con Claude Code

[PROMPT.md](PROMPT.md) tiene los prompts con los que se construyó esto, en orden y en los dos idiomas.

## Licencia

MIT. Freedoom y ViZDoom conservan sus propias licencias.
