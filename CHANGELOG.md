# Changelog

How this went from a forum joke to a playable mod, one step at a time.

The challenge: someone in a forum listed the AI fads (personal finance apps, reverse engineering,
TV launchers) and asked what was missing. "Running Doom in Claude." Challenge accepted.

## [0.2.0] - 2026-10-21 - Stage 1-2: it finishes MAP01

### Added
- `bridge/navegacion.py`: the bot now reads the real map from the WAD (omgifol): walls, steps,
  low ceilings, doors that open with USE, switches and the exit. It rasterizes the map into
  16x16 cells and runs A* to a goal: the exit if there is a path, else the closest unpressed
  switch, else the closest unexplored area. Floor and ceiling heights come live from ViZDoom, so
  it sees doors and lifts move. Closed doors on the path get faced and opened with USE pulses.
- Level progression: finishing a map loads the next one with its own navigator.
- Navigation events (goal, door, switch, stuck) go to the decision log; the state that Jev and
  Haiku read now includes the map, levels finished and the current navigation goal.

### Fixed
- Aiming oscillated left-right forever: a 4-tic turn overshoots by ~14 degrees, so it never
  centered and never shot. Turning now uses `TURN_LEFT_RIGHT_DELTA` with the exact angle
  (degrees per tic, positive = right).

### Measured (`bench_explore.py`, no Jev, fixed "explore" strategy)
| Map | Before (blind reflexes) | Now |
| --- | --- | --- |
| MAP01 | 10.3 cells, never finished | **finished 3/3**, ~700 frames (~80 s), 8 kills, 0 deaths |
| MAP02 | - | 21.5 cells, not finished |
| MAP03 | - | 22 cells, not finished |
| MAP04 | - | 73 cells, 5-9 deaths, not finished |
| MAP05 | - | 23 cells, not finished |

With Jev piloting: MAP01 finished in 89 s and it moved on to MAP02 (245 Jev decisions, 12 kills).

### Learned
- Others hit the same wall. In a 2026 ViZDoom project, Claude finished E1M1 1/5 times from the
  screen only and 4/5 with an automap (https://github.com/lucas-moont/doom-player). The fix is the
  same idea: give the agent a map, let code navigate and the AI choose goals.
- ViZDoom map coordinates and sector ids match the WAD exactly, so the WAD can be used as-is.

### Next (stage 3)
- Keys and locked doors, lifts, switches that open remote doors; MAP02-MAP05 as the benchmark.
- Jev chooses between navigation goals (exit now vs. clear the room vs. go for health).

## [0.1.1] - 2026-10-21

### Fixed
- Closing the pane with its X or `Esc` only hid it: the game, Jev and Haiku kept running and
  spending tokens. Closing the pane now stops the game.
- Each match stops by itself after 10 minutes.

### Added
- Decision log per match in `~/.doom-pane/logs/`: `match-<time>.jsonl` (start, mode changes with
  the full state, Jev decisions with probabilities and latency, stuck events, kills, deaths, position
  every second) and `match-<time>-claude.json` (what Haiku said and when).
- `bridge/bench_explore.py`: measures exploration as distinct 128x128 map cells visited in N frames.
  Baseline of the current reflexes: **10.3 cells in 1500 frames** (3 seeds). It loops in the first
  rooms and never opens doors.

### Learned
- Doom opens a door on the USE *press*, not while held, and only within 64 units. The reflexes
  turned away from walls at ~120 units, so they never reached a door.
- A quick fix (walk up to walls, pulse USE, steer to least visited cells) scored worse (7.0 cells),
  so it was not shipped. Next step is real navigation: read the map from the WAD (doors, switches,
  exits) and path to them.

## [0.1.0] - 2026-10-21

### Step 1: Doom without a window
- ViZDoom with Freedoom 2 (MAP01) runs headless from Python and hands over each frame, plus the
  objects on screen (labels buffer) and the distance to the walls (depth buffer).
- First proof: one frame drawn as ASCII in the terminal.

### Step 2: Reflexes
- A small rule-based brain: turn toward the biggest enemy and shoot when centered, strafe while
  shooting, steer toward the deeper side when a wall is close, press USE to open doors, back off and
  turn when stuck.
- Strategy (attack, explore, retreat, pick up) comes from outside through a JSON file.

### Step 3: The pane
- A Claude Code mod spawns the bridge and draws each frame with half-block characters (`▀`):
  top pixel as foreground color, bottom pixel as background, runs of equal cells merged.
- Haiku (through the session) gets the game state every 2.5 s, picks the strategy and narrates.
- Measured: ~7.5 fps from the bridge, ~1500 color runs per frame. Palette reduced to 512 colors.

### Step 4: Resizing
- `Esc` closes the pane, `/doom-stop` stops the game and closes it.
- Rows are cropped to the pane width instead of wrapping.
- The game resolution follows the pane size live, keeping 4:3.

### Step 5: Jev takes the wheel
- Jev (`jev-preview`) gets the real frame plus the state and answers a `choice` (strategy) and a
  `noul` (danger). Smaller images are rejected; 448x336 works.
- Measured: ~140 ms per decision with the image, ~2.5 decisions per second, 0 errors in 150 frames,
  first kill in that run. Text only (`jev-latest`): ~120 ms.
- Jev runs on its own thread: the game never waits for it.
- Haiku moves to narrator and can cheer Jev on or roast it. `/doom claude` keeps Haiku as pilot.

### Step 6: Anyone can run it
- Python code ships inside the plugin; `/doom-setup` builds `~/.doom-pane/venv` on Windows, Linux
  or macOS.
- The TypeSafe key is an optional, sensitive plugin option; without it Claude pilots.
- Narration in Spanish or English (install option, `/config`, or `/doom en` / `/doom es`).
- Prompts live in `prompts/` so anyone can change the narrator's personality.
