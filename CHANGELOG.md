# Changelog

How this went from a forum joke to a playable mod, one step at a time.

The challenge: someone in a forum listed the AI fads (personal finance apps, reverse engineering,
TV launchers) and asked what was missing. "Running Doom in Claude." Challenge accepted.

## [Unreleased] - seeds that really vary, crushers, and a route bug that cost half the time

### The seeds were not seeds
ViZDoom ignores `set_seed()` after `init()`. Up to 0.5.0 every benchmark seed played the same game:
with fixed actions, seeds 3, 4, 6 and 99 gave identical monsters and damage. The seed now goes in
before `init()`; 8 seeds give 6 different games (1, 4 and 6 still coincide). **Every number before
this section was measured on one game repeated**, so the 0.5.0 tables are not comparable with these.

### Navigation
- **Corners**: a route cell was only dropped when the bot passed within 24 units of it. Cutting a
  corner 35-50 units away, it kept aiming at a point already behind it and went back and forth.
  Now it takes the closest of the next 8 cells and drops the ones before. This one change is most
  of the table below.
- **Crushers** (MAP04 has three): their trigger lines were walk-on goals, so the bot stepped on them
  on purpose and then stood under the ceiling turning toward an off-screen monster (6 of 11 deaths
  with bonuses, at 82-86 health). Now it waits outside while the ceiling comes down and walks out
  if it is already under one, before any fighting. Walking out alone came too late: with the
  ceiling under 56, Doom does not let the player move anywhere that still touches the sector.
- **Teleports**: crossing a teleport from the second route cell went undetected; the bot replanned
  back to the teleporter, which sent it to the same spot. MAP02 seed 2 spent 2400 frames like that.
- **Switch retries**: a switch that did nothing gets a second try where the bot first walks back to
  the front of the line and aims. Doing it on every press changed MAP02's switch order (6/6 -> 2/6),
  so only retries do it. MAP04 switch 7 (the red key cage) failed 3 of 3 before.
- **Never without a goal**: with nothing left, it retries switches given up as useless and explores
  visited cells again (MAP04: 2300 frames standing still).

### Measured (code alone, real seeds, 6 per map; MAP01 2000 frames, MAP02 and MAP04 6000)
| | Real seeds, before these fixes | Now |
| --- | --- | --- |
| MAP01 | 6/6, 573-1082 frames | **6/6, 336-509** |
| MAP02 | 6/6, 3301-5602 frames, 1 death | **6/6, 1814-2777, 0 deaths** |
| MAP04 | 0/6, 26 deaths, red key 2/6 | 0/6, **4 deaths**, red key 6/6, switch 5 6/6 |

Switch 5 was pressed once in the 48 earlier MAP04 games.

### Experiments, off by default (`bench_reparto.py --barriles --bonus`)
- Shooting barrels from afar and picking up health/armor bonuses under 75 health.
- Before the route fix they helped MAP04 (26 -> 11 deaths, red key 6/6). After it they do not:
  bonuses take MAP02 from 6/6 to 2/6, MAP04 stays 0/6 with 3 deaths. Barrels change nothing in MAP02.
- `--pelea`: ask Jev "fight or follow the goal" with the numbers the code computes. MAP02 2/6, MAP04
  0/3, measured before the seed fix. Jev said "don't fight" in 8% of 2093 calls but in 48 of the 98 calls before a death: it
  says it with low health, when it is already late.

### MAP04: what is left
Switches 5 and 1 move the same lift (tag 3). The bot presses 5 standing on the lift, rides it down
and loses the route to 1 while the lift moves. After that it explores until the frames run out.

## [0.5.0] - 2026-10-25 - Jev measured against code alone, and code won the fight

0.4.1 ended with "surviving is the next stage, and where Jev should earn its place". This version
measured exactly that, with the same maps and seeds for every column. The short answer: in these
maps Jev does not earn its place in combat. Code alone finishes more and dies less. Jev keeps the
goal choice, where it hurts least, and the fighting goes back to the code.

### Combat (code)
- **Heal only when it is safe**: go for a medkit with no enemies in view, or one under 300 units;
  otherwise retreat first.
- **Barrels**: no shooting with a barrel in line under 250 units, step away under 100.
- **Turn toward unseen attackers**: losing health with nobody on screen turns toward the nearest
  monster for about a second. Fires 27-40 times per MAP04 run; imps sniping from off-screen were
  a big share of the deaths.

### Navigation
- **Caged keys and moving pillars**: thin sectors that a switch lowers count as walls only while
  closed (the red key cage in MAP04, opened by switch 7).
- **Narrow-corridor fallback**: when no goal has a route, retry once with 14 units of wall clearance
  instead of 20. Using 14 everywhere was tried and dropped: MAP02 fell to 1 of 3.
- **The opening between two sectors**: a lift room whose floor sits at the next corridor's ceiling
  left a zero-height gap the grid treated as walkable. Going down a lift now waits until it is down.
- Keys count as a goal when a cell within ~32 units has a route (was ~64).

### Jev and code: who decides what
- Jev is no longer offered "explore" while a key, switch, exit or trigger line has a route. With it,
  Jev picked "explore" 446-626 times per game and never finished MAP02.
- A new weapon, health under 50 or ammo under 10 is decided by the code. Without that, Jev went
  straight for the blue key without the shotgun: 20 deaths in 3 games, 9 of them with 0 ammo.
- **Jev's tactic is logged and shown, not obeyed.** Pelear / esquivar was what killed it: it backed
  away from Demons, which catch up with a player walking backwards, and fought them up close.

### Measured (6000 frames per game; finished / deaths per seed)
| MAP02 | Finished | Deaths |
| --- | --- | --- |
| Code alone (6 seeds) | **6/6** | 1 1 0 0 0 0 |
| Jev tactic + goal, "explore" offered (3) | 0/3 | 0 1 1 |
| Jev, no "explore" (3) | 0/3 | 7 5 8 |
| Jev, code owns supplies (6) | 1/6 | 0 2 2 3 2 3 |
| **Jev goal only, code fights (6)** | **3/6** | 1 2 0 0 1 0 |

| MAP04 | Finished | Deaths |
| --- | --- | --- |
| Code alone, start of this version | 0 | 14-16 per game, stuck at the red key cage |
| Code alone now (6 seeds) | 0/6 | 3 0 1 3 7 6; red key every time |
| Jev tactic + goal (3) | 0/3 | 12 10 5 |
| Code alone, no monsters (scene tool) | **finished**, 1095 frames | - |

MAP01: code alone 3/3. Jev+Haiku only got one full MAP04 game (7 deaths) before Windows killed the
run for low memory; it is not in the tables.

Honest caveats:
- Code alone barely varies with the seed: MAP02 seeds 3, 4 and 6 are the same game frame by frame.
  Its 6/6 is closer to "one good route, repeated" than to six independent runs. Jev's games do vary
  (shuffled options, live API).
- The three Jev-goal games that did not finish each had one death, which resets the level, and ran
  out of frames near the end. Jev's goals are also slower: 3547 and 5095 frames vs 3323.
- In ViZDoom the code knows every monster's position and the whole map. Jev sees a 448x336 frame
  plus a text built by that same code, so its edge, understanding the picture, adds nothing here.

### MAP04: what is left
The puzzle is solved: without monsters it goes switches 5, 1, 10 -> blue key -> blue switches 3/4 ->
switches 6, 2 -> exit. With monsters, most runs end in an ambush ~110 frames after the red key,
arriving with ~20 health and the pistol in hand.

### Tools
- `escena.py --semilla N --sin-monstruos`: debug a puzzle without monsters changing the path.
- `bench_reparto.py --solo-meta` (Jev picks the goal, code fights) and `--desde N` (add seeds).
- Benchmark kills now add up every life; before, a 7-death game reported 0.
- Deaths are logged with what was around, plus combat events and a snapshot every 200 frames.

### Next
Ask Jev the kind of question it is calibrated for: yes/no with numbers the code computes ("with a
shotgun and 40 health, fight a Demon at 200 units?"), instead of picking a control mode out of four.
Longer term, a pure-pixels mode where the code does not get coordinates, so Jev is the only one who
can read the screen.

## [0.4.1] - 2026-10-22 - MAP03 and MAP05 open up; the pane speaks English too

### Navigation
- **Walk-over triggers** (Doom's W1/WR lines): lines that open a door, lower or raise a floor when
  you cross them. MAP03 has a door that only opens this way (action 109). They are a new goal type
  ("walk over line N"), reachable from either side of the line, and the sectors they move count as
  closed until they really open.
- **Ammo for every weapon you carry**, not only the one in hand: with the pistol in hand it only
  looked for bullets, so the shotgun ran dry and it fought imps with the pistol (MAP02: 3 deaths).
- **Supplies it cannot take** (ammo at max, item on a ledge): reaching one counts as done. MAP03
  circled a box of bullets it could not pick up for 13,000 frames.
- **Switches pressed from closer** (walks up to ~24 units while pressing) and **three tries** before
  giving up on one. MAP03's switch 12 failed twice from ~40 units and was dropped, which blocked the
  rest of the map; MAP05's switch 14 retried forever before the cap.
- Combat log line: a snapshot every 200 frames (position, health, ammo, goal), so a stall without
  events shows up.

### Measured (code only, 1 seed each)
| Map | 0.4.0 | 0.4.1 |
| --- | --- | --- |
| MAP01 | finished | finished (479-884 frames) |
| MAP02 | finished 2/2, 0 deaths | finished in 1 of 2 runs (1 death); the other died 4 times |
| MAP03 | two keys, then stuck | **all three keys and 8+ switches**; died ~100 steps from the exit |
| MAP05 | 49 cells, stuck on one switch | **197 cells**, blue key, ~8 switches |

The puzzle side of MAP02 and MAP03 is solved. Whether a run finishes now depends on surviving: each
death resets keys and switches, and the bot fights to the death instead of retreating or healing.
That is the next stage, and where Jev should earn its place.

### The pane in English
- With `/doom en` (or the English option) everything in the pane is in English, not only the
  narration: the status line (health, ammo, levels done, enemies, items, keys), the mode, Jev's
  tactics, the goal and Claude's plan (`red key > switch 3 > exit`). Jev still gets its state in
  Spanish, the language its questions were tested in.

### Docs
- README in English (`README.md`) and Spanish (`README.es.md`), rewritten for 0.4: what each piece
  does, where each map stands, tools, logs, cost and limits.

## [0.4.0] - 2026-10-22 - MAP02 finished: keys, switches, lifts, teleporter, and staying alive

First level with keys solved end to end, by code alone: **MAP02 finished 2/2, 0 deaths, 43 kills**
(4073 and 4942 frames). The full chain, both seeds: blue key -> switches 5, 1, 3 -> red key ->
switches 4, 2 -> yellow key -> teleporter -> exit. MAP01 still 2/2 and faster (952 and 672 frames).

| MAP02, code only | Result |
| --- | --- |
| 0.3.0 | not finished, 129-151 cells |
| + teleporters, remote doors | all three keys once, stuck crossing the teleporter back |
| + single-press doors, owned weapons | stuck 36 steps from the yellow key (switch "used" but not hit) |
| + switch verification | puzzle fine, but 5 deaths: each one resets keys and switches |
| **+ combat reflexes** | **finished 2/2, 0 deaths** |

### Navigation
- **Teleporters as shortcuts:** entry cells in front of the line jump to the destination thing
  (type 14) in the tagged sector. The entry cell is not dropped from the route until the line is
  crossed (dropping it made the bot turn toward the far-away destination and loop for 300 frames).
- **Remote doors:** sectors moved by a switch tag. They only count as passable when they are really
  open (live height); "the switch was pressed" is not enough.
- **Key switches (99, 133-137) open remote doors, not the door you face:** MAP02's red door opens
  from a red switch elsewhere. They are handled as remote doors, offered only with the key.
- **Switch verification:** ~8 s after pressing a switch, if none of its sectors moved, it is
  unmarked and retried (`interruptor_sin_efecto` in the log). A USE that misses no longer leaves
  the planner believing a door is open.
- **Doors get one USE:** a second USE on an opening door sends it back down. The old three pulses
  opened and closed it, which is why the bot got stuck at MAP02's yellow door in the first live run.
- **No detours for weapons it already has** (ViZDoom reports owned weapon slots).
- Thin impassable sectors, lifts called and waited for, teleporter lines as walls (from 0.3.0).

### Combat reflexes (code)
- **Dodge projectiles:** ViZDoom gives position and velocity of every object; if a fireball will pass
  within 48 units in the next second, strafe away from that point.
- **Target priority:** arch-vile first, then hitscanners (chaingunners, shotgun guys, zombiemen; their
  shots cannot be dodged), then the closest.
- **Weapon by distance:** shotgun close, chaingun mid/long, pistol if nothing else.

### Tools
- `bridge/escena.py`: drops the bot anywhere on a map with chosen keys and switches (console cheats:
  give, god, warp) and traces each step. Found the door and teleporter bugs in minutes instead of
  waiting 10,000 frames per try.
- Deaths are logged with position, health, ammo, weapon and the monsters/projectiles nearby.
- `bench_reparto.py`: `--pregunta v1|v2` for Jev's goal question, and `jev_haiku_sonnet` mode
  (Sonnet on map start, key or switch, death, ~60 s without progress; Haiku for routine checks).

### Next
- MAP03-MAP05 with code only, then the Jev / Haiku / Sonnet columns again on this navigator, with
  more seeds. With code finishing MAP01-02, the question for Jev and Claude becomes: do they finish
  faster, die less, or finish maps code alone cannot?

## [0.3.0] - 2026-10-22 - Who does what: code moves, Jev chooses, Claude plans

The question that started this release: "if the code solves everything, what is Jev for?" Fair:
in 0.2.x the navigator did almost everything and Jev answered "explore 0.99" most of the time.
So the work was split the way the Jev game agents that work do it (Minecraft: Astra plans, Jev
controls; Pokemon LeafGreen: Haiku plans, Jev fights):

| Piece | Job |
| --- | --- |
| Code | builds the list of goals that have a route right now (exit, each key, each switch, weapons, health, ammo, unexplored area), walks routes, aims, opens doors, calls lifts |
| Jev (~1-2.5/s, image + state) | picks the tactic (fight / dodge / advance) and which goal to chase |
| Claude Haiku (every few s) | reads a summary of the level puzzle (keys, key doors, what each switch moves, lifts) and returns the plan: an ordered list of goal ids. Also narrates |

Jev calls follow what other builders learned (relayed by our jev-117 session): pinned model
`jev-1.14.0` (calibration changed from 1.13), decide by argmax of probabilities instead of the
`choice` field, confidence = gap between the top two (under 0.2 the script decides), and options
shuffled every call because `choice` favors the first one.

### Three-column benchmark (`bench_reparto.py`, synchronous: the game waits for each call)

| | MAP01 | MAP02 |
| --- | --- | --- |
| Code only (3 seeds / 2 seeds) | **finished 3/3** (1170-1628 frames) | not finished, 129-151 cells, 1 death |
| + Jev (1 seed) | **not finished**, 80 cells | not finished, 138 cells, 2 deaths |
| + Jev + Haiku (1 seed) | **finished at frame 631, the fastest** | not finished, 143 cells, **10 deaths** |

What it says (with one seed for the Jev columns, so read it as a first signal, not a verdict):
- **Jev alone wanders.** On MAP01 it asked for "frontera" (nearest unexplored area) 152 times out
  of 223 and for "salida" 7 times, even with a route to the exit. It has no notion of "finish the
  level"; the question ("which goal helps you advance without dying?") and the frontier listed at
  "0 units" push it to explore.
- **Haiku fixes that.** On MAP01 one call ("plan: salida") was enough, and it finished faster than
  code alone because Jev skipped detours. On MAP02 Haiku worked out most of the puzzle by itself:
  "switch 3 first, then switch 4 lowers the lift for the red key, then the exit".
- **But MAP02 still fails, and dies more.** The red key area is reached through a teleporter the
  navigator does not model yet; Haiku kept sending it to the blue key (52 goal picks) and Jev doubted
  a lot (273 goal doubts out of 667). 10 deaths vs 1-2: chasing the plan through enemies with
  "advance" (ignore enemies) is dangerous.
- Cost: 667 Jev calls ~150 ms each, 0 errors. 16 Haiku calls ~12 s each through `claude -p`.

### Navigator fixes found by the benchmark
- Thin sectors with no room to pass (bars, windows, 16 units wide) were invisible to the 16x16
  grid; their edges are walls now.
- Doors were pressed from ~70 units (USE reaches 64): it now walks up while pressing.
- The exit could be dropped for good after 3 failures; exit and keys are never dropped now, other
  goals only for ~30 s, and the penalty on the blocked route grows.
- Ammo detours only under 10 rounds and close by (shells were always "low").
- Key switches (133-137) are not offered without the key.
- Teleporter lines are walls for now (stepping on one sends you elsewhere and breaks the route).

### In the pane
- Haiku is planner + narrator in one call every ~6 s; the plan goes to the bridge, which follows it.
- New line: current goal and Claude's plan (`meta: llave_azul | plan Claude: llave_azul > interruptor_5 > salida`).
- Jev line shows the goal Jev asks for.

### Next
- Model teleporters as edges (needed for the MAP02 red key).
- Jev question v2 ("which goal gets you closer to finishing the level?") as a fourth column.
- Why more deaths with the plan: when to fight vs. advance.

## [0.2.2] - 2026-10-21

### Fixed
- Stuck forever chasing an item it could not reach. Seen live: Jev saw an ammo clip 104 units
  ahead (behind a ledge), chose "pick up" with 0.65, the bot walked into the wall, and since the
  pick-up mode had no stuck detection nor navigator it stayed there. Jev kept seeing the clip and
  kept choosing it. Haiku noticed before the code did: "ni asi suelta el cargador de 104, que
  terquedad".
- Now, stuck while picking up or retreating marks that item as unreachable for ~30 s, hides it
  from the state Jev reads, and hands control to the navigator for ~5 s. Logged as a `cerebro`
  event with the item and its position.

### Measured
- New benchmark mode `--orden recoger` (a stubborn pilot that always wants items): MAP01 finished
  3/3 (523, 683, 1194 frames). Normal mode unchanged: 3/3, ~700 frames.

## [0.2.1] - 2026-10-21

### Added
- The version shows in the pane header (`DOOM v0.2.1 | MAP01 | ...`) and in the start message,
  read from the installed `plugin.json`. After `claude plugin update`, a session keeps running the
  old copy until `/reload-plugins` or a restart; now you can tell at a glance.

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
