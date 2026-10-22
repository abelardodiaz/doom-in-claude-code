# How to recreate this with Claude Code

These are the prompts that built this repo, in order, cleaned up a little.
They were written in Spanish; the English version comes first.

Claude Code had the `plugin-authoring` skill available (mods with panes) and a TypeSafe key.

## English

1. "In the forums the joke is that the only thing left is running Doom in Claude. Challenge accepted."
   (Claude offered three takes: Doom in a claude.ai artifact, Doom inside the Claude Code interface,
   or Claude playing Doom.)
2. "The second and the third together: not only running in Claude Code, but playing by itself."
3. "Would Rust help?" (Answer: no. The engine is already C++; the bottleneck is the pane redraw.)
4. "I resized the screen and it looks ugly, how do I close it to try again?"
5. "OK, make it adapt to the size."
6. "Would Jev help it play and make decisions?" / "Go ahead, Jev gives me credits."
7. "Meanwhile, prepare a public repo. Fully reproducible, prompts included,
   the only thing missing will be your Jev API key."
8. "It should let you pick English or Spanish. The changelog should show the progress, with separate
   commits to show the history."

## Español

1. "En los foros el chiste es que solo falta correr Doom en Claude. Reto aceptado."
2. "La 2 y la 3 juntas: que no solo corra en Claude Code, sino que se maneje solo."
3. "¿Rust ayudaría?"
4. "Redimensioné la pantalla y se ve feo, ¿cómo lo cierro para volver a intentar?"
5. "Ok, que se adapte."
6. "¿Ayudaría Jev IA a jugar y tomar decisiones?" / "Adelante, Jev me da créditos."
7. "Mientras, preparemos un repo público. Replicable totalmente, con prompts incluidos,
   solo faltará su Jev API key."
8. "Debería permitir elegir entre inglés y español. El changelog debe mostrar los progresos, con
   commits independientes para mostrar avances históricos."

## Tips if you build your own

- Ask for ViZDoom: it ships Freedoom and exposes labels (what is on screen) and depth (walls),
  which is what makes a text-only AI able to "see".
- Keep the fast loop (reflexes) in code and the AI on the slow loop (strategy). No API answers
  10 times per second.
- Measure the bridge alone before blaming the pane, and the pane before blaming the model.
