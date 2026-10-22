# Doom in Claude Code

**English** | [Español](README.es.md)

Doom running inside a Claude Code pane, and nobody holding the controls. Three pieces, each doing
the job it is good at:

- **Code** walks, aims, opens doors, calls lifts and dodges fireballs. It reads the real map from the
  WAD (doors, keys, switches, lifts, teleporters, exit) and finds routes with A*.
- **Jev** ([TypeSafe](https://typesafe.ai)) looks at the actual screen ~2.5 times per second
  (~150 ms per call) and picks the tactic (fight / dodge / advance) and which goal to chase.
- **Claude** plans the level puzzle (which key opens what, which switch moves which door) and
  narrates live like a streamer. Haiku does the routine; Sonnet steps in when it gets hard (map start,
  death, a minute without progress). It runs through your own Claude Code session: no extra API key.

No TypeSafe key? Claude plans and code plays.

The game is [ViZDoom](https://github.com/Farama-Foundation/ViZDoom) with
[Freedoom](https://freedoom.github.io/) (free content, BSD license), so no original Doom files are needed.

## Where it stands

| Map | Code alone |
| --- | --- |
| MAP01 | finished |
| MAP02 | finished, 0 deaths: blue key -> switches -> red key -> switches -> yellow key -> teleporter -> exit |
| MAP03 | gets all three keys and most switches; deaths cost it the time to reach the exit |
| MAP04 | dies to packs of imps: this is where Jev should earn its place |
| MAP05 | partially explored |

Every step is measured and written up in the [changelog](CHANGELOG.md), with the raw data in the repo.
What comes next is in the [roadmap](ROADMAP.md).

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

- **TypeSafe API key** (optional): with it, Jev joins. Get one at [typesafe.ai](https://typesafe.ai).
- **Narration language**: `es` or `en`. Both can be changed later in `/config`.

Then, one time:

```
/doom-setup
```

It finds Python 3.9+ and installs ViZDoom, numpy, pillow, requests and omgifol into
`~/.doom-pane/venv`. Nothing is installed globally.

## Play (well, watch)

| Command | What it does |
| --- | --- |
| `/doom` | Starts the game in a pane. Jev decides if there is a key; Claude plans and narrates |
| `/doom claude` | Without Jev: Claude plans, code plays |
| `/doom en` / `/doom es` | Narration language for this match |
| `/doom-stop` or `Esc` | Stops the game and closes the pane |

The pane shows the game, Jev's numbers (latency, probabilities, the goal it asks for), the current
goal and Claude's plan, and the narration. The picture follows the pane size and keeps Doom's 4:3
ratio. Use a terminal with 24-bit color (Windows Terminal, iTerm2, kitty, Ghostty, most Linux
terminals) and at least ~110 columns.

Closing the pane stops the game, and a match stops by itself after 10 minutes: Jev and Claude cost
tokens, so nothing keeps running unwatched.

## How it works

```
 ViZDoom (headless) --frame, labels, depth, sectors, objects--> bridge/doom_bridge.py
        ^                                                          | reflexes: aim, dodge, weapon
        | actions every 4 tics                                     | bridge/navegacion.py: WAD map,
        +----------------------------------------------------------+ goals with a route, A*, doors
                                                                    |
 Jev (jev-1.14.0, image + state) <-- own thread -- bridge/jev_pilot.py: tactic + goal
                                                                    |
 Claude Code pane (hooks/register.tsx) <-- one JSON line per frame -+
        | draws half-block cells, Jev numbers, goal and plan, narration
        +--> Haiku / Sonnet via the session ($.model.complete): plan + narration every ~6 s
```

- `bridge/doom_bridge.py`: runs the game, combat reflexes, frame encoding, decision log.
- `bridge/navegacion.py`: the map from the WAD (omgifol) on a 16x16 grid; doors, key doors, remote
  doors opened by switches or by walking over a line, lifts, teleporters; lists every goal that has a
  route and walks to the chosen one; checks that a pressed switch really moved something.
- `bridge/jev_pilot.py`: one Jev call with the frame (JPEG 448x336; Jev rejects images under 280 px)
  plus the state as text. Decides by the highest probability, needs a gap of 0.2 between the top two
  (otherwise the script decides) and shuffles the options every call, because Jev favors the first one.
- `prompts/planner.md`: Claude's prompt as planner and narrator. Edit it to change the plan logic or
  the personality.
- `hooks/register.tsx`: the Claude Code mod (pane, commands, Claude loop, model escalation).
- `bridge/bench_reparto.py`: benchmark by columns (code only / + Jev / + Jev + Haiku / + Sonnet).
- `bridge/escena.py`: drops the bot anywhere on a map with chosen keys (console cheats) to debug a
  spot in seconds instead of replaying thousands of frames.

The code is commented in Spanish; the docs are in English and Spanish.

## Logs

Each match writes `~/.doom-pane/logs/match-<time>.jsonl` (Jev decisions with probabilities and
latency, navigation events, kills, deaths with what was nearby, position every second) and
`match-<time>-claude.json` (what Claude planned and said, and which model answered).

## Cost

Jev with an image is ~700 input tokens per decision, ~2.5 decisions per second: around 6M tokens per
hour of play. Check TypeSafe's current pricing. Claude's calls count against your own Claude Code
usage (a few hundred tokens every ~6 s, more when Sonnet steps in).

## Known limits

- Combat is the weak spot: the bot fights to the death instead of retreating or healing.
- Big panes mean more color cells per frame. If it stutters, make the pane smaller.
- Tested on Windows 11 with Python 3.14. Linux and macOS should work (ViZDoom has wheels), but are
  not tested yet.

## Recreate it with Claude Code

[PROMPT.md](PROMPT.md) has the prompts that built this, in order.

## License

MIT. Freedoom and ViZDoom keep their own licenses.
