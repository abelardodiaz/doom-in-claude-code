"""Mide que tanto explora el bot: celdas distintas del mapa visitadas en N frames.

Uso: python bench_explore.py [--frames 1500] [--semillas 3]
Sin Jev ni Claude: estrategia fija "explorar" (los reflejos atacan solos si ven enemigos).
"""
import argparse
import random

import doom_bridge as db

CELDA = 128


def correr(frames, semilla):
    random.seed(semilla)
    g = db.crear_juego()
    g.set_seed(semilla)
    g.new_episode()
    cerebro = db.Cerebro()
    celdas = set()
    muertes = 0
    for _ in range(frames):
        if g.is_episode_finished() or g.is_player_dead():
            muertes += 1
            g.new_episode()
        st = g.get_state()
        if st is None:
            g.advance_action(1)
            continue
        v = st.game_variables
        celdas.add((int(v[4] // CELDA), int(v[5] // CELDA)))
        act, _ = cerebro.decidir(st, v, "explorar")
        g.make_action(act, 4)
    kills = int(g.get_game_variable(db.vzd.GameVariable.KILLCOUNT))
    g.close()
    return len(celdas), kills, muertes


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=1500)
    ap.add_argument("--semillas", type=int, default=3)
    a = ap.parse_args()
    tot = 0
    for s in range(a.semillas):
        c, k, m = correr(a.frames, s + 1)
        tot += c
        print(f"semilla {s + 1}: celdas {c}, kills {k}, muertes {m}")
    print(f"promedio celdas: {tot / a.semillas:.1f}")
