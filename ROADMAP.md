# Roadmap

What comes next, in order. The rule: first it has to play well, then it can look good.
Every step gets measured with `bridge/bench_reparto.py` and written up in the [changelog](CHANGELOG.md).

## Now

1. **MAP02 with code only.** The navigator already collects all three keys and uses all five
   switches in the right order (blue -> switches 5, 1, 3 -> red -> switches 4, 2 -> yellow). Last
   blocker: crossing the teleporter back toward the exit (fixed, being measured).
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
   - Free option first: the system voice, no key, no network. On Windows, PowerShell with
     `System.Speech` (`SpeechSynthesizer.Speak`), already used by one of the author's projects to
     speak Claude Code notifications; on macOS, `say` (or the mod's `$.audio.speak`). Speak only in
     specific moments (key picked, level finished, death, boss in sight), not every line.
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
