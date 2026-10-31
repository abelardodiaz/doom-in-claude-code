# Roadmap

What comes next, in order. The rule: first it has to play well, then it can look good.
Every step gets measured with `bridge/bench_reparto.py` and written up in the [changelog](CHANGELOG.md).

## Now

1. ~~MAP02 with code only~~ **done in 0.4.0.** ~~MAP03 and MAP04~~ **done in 0.6.0** (24/24 and
   23/24 over 24 seeds). Next: MAP05 onwards, and the last MAP04 seed.
2. **Re-run the columns on the new navigator:** code / + Jev (question v1 and v2) / + Jev + Haiku /
   + Jev + Haiku with Sonnet escalation (start of map, key or switch, death, ~60 s without progress).
   More seeds per column so the Jev numbers mean something.

## Next

3. **Combat with Jev.** Deaths are what costs MAP02 the most (each death resets keys and switches),
   and later maps bring imps, demons, cacodemons, revenants, mancubi, arch-viles.
   - Code: dodge projectiles (ViZDoom objects give position and velocity), pick the weapon from a
     table (shotgun close, chaingun mid range, never rockets point blank).
   - Jev, with the image: which enemy to shoot first (arch-vile always), fight / dodge / take cover /
     run past, is this room worth clearing.
   - Measure deaths and kills per map, with and without Jev.
4. **Groq as a fast replanner.** Between Jev (~150 ms, picks among options) and Claude (seconds,
   plans the puzzle): an LLM answering in under a second for "I'm stuck, what now?". A benchmark
   column against Haiku.

## Later (when it finishes levels consistently)

5. **Voice narration.** Parked on purpose: no point narrating a bot that does not finish.
   - The system voice is for short event alerts only (key picked, level finished, death, boss in
     sight), not narration: on Windows, PowerShell with `System.Speech` (`SpeechSynthesizer.Speak`),
     already used by one of the author's projects for Claude Code notifications; on macOS, `say`.
   - Nicer option later: Deepgram TTS. Notes so nobody rediscovers them:
   - The mod API can play base64 audio (`$.audio.play`), but its docs say a Windows or Linux
     terminal plays nothing (no player); only macOS. So the Python bridge plays it: Deepgram TTS as
     WAV, `winsound` on Windows (built in), `afplay` on macOS, `aplay` on Linux, in its own thread,
     skipping a line if the previous one is still playing.
   - The key goes in as an optional, sensitive plugin option, like the TypeSafe key.
6. **A video for the forum** of a full run: pane, Jev numbers, Claude's plan and narration.
7. **Spend cap that survives restarts** (idea from olivier-motium/jev-doom): reserve the worst-case
   cost before each call, settle it with the real one, keep the ledger in a file.
8. **Check every Jev prediction** against the next state (met / not met / unknown) to measure how
   often it is right.
9. **"Pure" mode without the WAD:** Jev and Claude navigate from the screen and the depth buffer
   only. The hard version of the challenge. Reference: Claude cleared E1M1 1/5 from the screen and
   4/5 with an automap (lucas-moont/doom-player).
10. **Another game with the same recipe:** the Mario AI Benchmark ("Infinite Mario"), an open Mario
    clone built for AI agents (2009-2012 competitions). Code moves, Jev decides fast, Claude plans.
    After Doom.
11. **Real-time advisor for a human player** (idea, 2026-10-22). Same brain, but a person plays and
    the bot only talks. ViZDoom's `Mode.ASYNC_SPECTATOR` lets a human play with keyboard and mouse
    in a normal window while the API still reads position, angle, health, monsters, door and lift
    heights and keys every tic. The navigator already knows the next goal and route, so it can say
    "blue door ahead", "press the switch on your left, then ride the lift", "imp behind you".
    Limit: this works inside ViZDoom only; reading GZDoom or the Steam version would need engine
    hooks or screen reading.
12. **Minecraft challenge with the same method** (idea, 2026-10-22). rmalde/minecraft-agent killed
    the Ender Dragon in 8:43 for under $1 (Astra plans, Jev controls). We do not know how long it
    took them to build, so the comparison is on results, measured our way: fixed world seeds,
    success rate over N seeds, deaths with context, time and cost, and the three columns (code
    only, code + Jev, code + Jev + Claude).
    - Recipe: Mineflayer bot (`mineflayer-pathfinder` for routes, crafting tree in code), Jev for
      fast calls (fight or flee, eat, shelter), Claude for phases (wood, stone, iron, diamond,
      Nether, eyes of Ender, stronghold, dragon). Debug scenes with `/tp`, `/give` and no mobs.
    - No WAD here: the world is generated, so the bot builds its own map while exploring.
    - First measurable goal: a diamond pickaxe from scratch.
    - Cost: Minecraft is not open source, but the official server jar is free (accept the EULA).
      A local server with `online-mode=false` lets the bot join without an account, and
      `prismarine-viewer` shows the bot's view in a browser for streaming (OBS or Discord). A
      licence (~30 USD) is only needed to watch with the real client.
    - Licensed players can join an offline-mode server too, but it does not check identities:
      keep it private (WireGuard or whitelist, port 25565 closed). If it goes public, switch to
      `online-mode=true` and give the bot its own licensed account (Mineflayer supports Microsoft
      login).
    - Its own repo, after Doom 0.5.0.
