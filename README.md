# Doom in Claude Code

Doom running inside a Claude Code pane, and nobody holding the controls:

- **Jev** ([TypeSafe](https://typesafe.ai)) looks at the actual game screen and picks the strategy about 2.5 times per second (~140 ms per decision).
- **Claude** (Haiku) narrates the match live, like a streamer, in Spanish or English.
- **Python reflexes** aim and shoot, and a **navigator** reads the real map from the WAD (doors, switches, exit) and finds the path with A*. It finishes MAP01 by itself; later maps are the next stage (see the [changelog](CHANGELOG.md)).

No TypeSafe key? Claude pilots instead (one decision every 2.5 s).

The game is [ViZDoom](https://github.com/Farama-Foundation/ViZDoom) with [Freedoom](https://freedoom.github.io/) (free content, BSD license), so no original Doom files are needed.

*Versión en español abajo.*

## Install

At the prompt of a Claude Code terminal session:

```
/plugin install doom-pane --marketplace abelardodiaz/doom-in-claude-code
```

From a shell:

```
claude plugin install doom-pane --marketplace abelardodiaz/doom-in-claude-code
```

Answer `y` to add the marketplace, pick a scope, then the options screen asks for:

- **TypeSafe API key** (optional): with it, Jev pilots. Get one at [typesafe.ai](https://typesafe.ai).
- **Narration language**: `es` or `en`. You can change both later in `/config`.

Then, one time:

```
/doom-setup
```

It finds Python 3.9+ and installs ViZDoom, numpy, pillow, requests and omgifol into `~/.doom-pane/venv`. Nothing is installed globally.

## Play (well, watch)

| Command | What it does |
| --- | --- |
| `/doom` | Starts the game in a pane. Jev pilots if there is a key, Claude narrates |
| `/doom claude` | Claude (Haiku) pilots instead of Jev, handy for an A/B |
| `/doom en` / `/doom es` | Narration language for this match |
| `/doom-stop` or `Esc` | Stops the game and closes the pane |

The picture follows the pane size and keeps Doom's 4:3 ratio. Use a terminal with 24-bit color (Windows Terminal, iTerm2, kitty, Ghostty, most Linux terminals) and give it at least ~110 columns.

## How it works

```
 ViZDoom (headless)  --frame + labels + depth-->  bridge/doom_bridge.py
        ^                                           |  reflexes: aim, shoot, dodge, doors
        |  actions every 4 tics                      |  one JSON line per frame (half-block cells)
        +-------------------------------------------+
                                                     v
 Jev (jev-preview, image + state) <-- thread --  bridge/jev_pilot.py   choice: strategy, noul: danger
                                                     |
 Claude Code pane (hooks/register.tsx)  <-- stdout --+
        |  draws ▀ cells with fg/bg color, Jev stats, narration
        +--> Haiku via the session ($.model.complete): narrator, or pilot with "/doom claude"
```

- `bridge/doom_bridge.py`: runs the game, the reflexes and the frame encoding. Strategy comes from Jev (thread) or from `orders.json` (Claude).
- `bridge/navegacion.py`: map from the WAD, 16x16 grid, A* to exit / switches / unexplored areas, door opening.
- `bridge/bench_explore.py`: `--mapa MAP02` measures cells explored and whether the level gets finished.
- `bridge/jev_pilot.py`: one Jev call with the frame (JPEG 448x336; smaller sizes are rejected with "Invalid image dimensions") plus the state as text. Two typed questions: a `choice` among `atacar / explorar / retirada / recoger`, and a `noul` for "in immediate danger".
- `prompts/pilot.md` and `prompts/narrator.md`: Claude's prompts. Edit them to change the personality.
- `hooks/register.tsx`: the Claude Code mod (pane, commands, Haiku loop).

Haiku runs through your own Claude Code session, so it needs no extra API key.

## Cost

Jev with an image is ~700 input tokens per decision, ~2.5 decisions per second: around 6M tokens per hour of play. Check TypeSafe's current pricing. Haiku narrates every 4 s with a few hundred tokens per call.

## Known limits

- Only MAP01 is finished reliably. Keys, lifts and remote switches (MAP02 onward) are the next stage.
- Big panes mean more color cells per frame. If it stutters, make the pane smaller.
- Tested on Windows 11 with Python 3.14. Linux and macOS should work (ViZDoom has wheels), but are not tested yet.

## Recreate it with Claude Code

[PROMPT.md](PROMPT.md) has the prompts that built this, in order.

---

# Doom en Claude Code (español)

Doom corriendo dentro de un panel de Claude Code, sin nadie en los controles:

- **Jev** ([TypeSafe](https://typesafe.ai)) ve la pantalla real del juego y decide la estrategia unas 2.5 veces por segundo (~140 ms por decisión).
- **Claude** (Haiku) narra la partida en vivo, como streamer, en español o inglés.
- **Reflejos en Python** apuntan y disparan, y un **navegador** lee el mapa real del WAD (puertas, interruptores, salida) y calcula la ruta con A*. Ya termina MAP01 solo; los siguientes mapas son la próxima etapa.

¿Sin key de TypeSafe? Pilota Claude (una decisión cada 2.5 s).

## Instalación

En Claude Code:

```
/plugin install doom-pane --marketplace abelardodiaz/doom-in-claude-code
```

Al instalar te pide la **API key de TypeSafe** (opcional) y el **idioma de la narración** (`es` o `en`). Las dos se cambian después en `/config`. Luego, una sola vez:

```
/doom-setup
```

Instala ViZDoom en `~/.doom-pane/venv`, sin tocar tu Python global.

## Comandos

| Comando | Qué hace |
| --- | --- |
| `/doom` | Arranca el juego. Pilota Jev si hay key, narra Claude |
| `/doom claude` | Pilota Claude (Haiku) en vez de Jev |
| `/doom en` / `/doom es` | Idioma de la narración para esta partida |
| `/doom-stop` o `Esc` | Detiene el juego y cierra el panel |

La imagen se ajusta al tamaño del panel. Necesitas una terminal con color de 24 bits y unas 110 columnas.

## License

MIT. Freedoom and ViZDoom keep their own licenses.
