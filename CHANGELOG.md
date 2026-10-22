# Changelog

How this went from a forum joke to a playable mod, one step at a time.

The challenge: someone in a forum listed the AI fads (personal finance apps, reverse engineering,
TV launchers) and asked what was missing. "Running Doom in Claude." Challenge accepted.

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
