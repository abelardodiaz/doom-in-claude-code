"""Mide que tanto explora el bot: celdas distintas del mapa visitadas en N frames.

Uso: python bench_explore.py [--frames 1500] [--semillas 3]
Sin Jev ni Claude: estrategia fija "explorar" (los reflejos atacan solos si ven enemigos).
"""
import argparse
import random

import doom_bridge as db
import navegacion as nv

CELDA = 128


def correr(frames, semilla, con_mapa, mapa="MAP01", orden="explorar"):
    random.seed(semilla)
    g = db.crear_juego(mapa)
    g.set_seed(semilla)
    g.new_episode()
    cerebro = db.Cerebro(nv.Navegador(nv.cargar(mapa)) if con_mapa else None)
    terminado = None
    celdas = set()
    muertes = 0
    for n in range(frames):
        if g.is_episode_finished() and not g.is_player_dead():
            terminado = n
            break
        if g.is_player_dead():
            muertes += 1
            g.new_episode()
        st = g.get_state()
        if st is None:
            g.advance_action(1)
            continue
        v = st.game_variables
        celdas.add((int(v[4] // CELDA), int(v[5] // CELDA)))
        act, _ = cerebro.decidir(st, v, orden)
        g.make_action(act, 4)
    kills = int(g.get_game_variable(db.vzd.GameVariable.KILLCOUNT))
    g.close()
    return len(celdas), kills, muertes, terminado


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=1500)
    ap.add_argument("--semillas", type=int, default=3)
    ap.add_argument("--mapa", default="MAP01")
    ap.add_argument("--orden", default="explorar", choices=["explorar", "atacar", "retirada", "recoger"],
                    help="estrategia fija; 'recoger' simula a un piloto terco que va por todo objeto")
    ap.add_argument("--sin-mapa", action="store_true", help="reflejos a ciegas (linea base)")
    a = ap.parse_args()
    tot = 0
    for s in range(a.semillas):
        c, k, m, fin = correr(a.frames, s + 1, not a.sin_mapa, a.mapa.upper(), a.orden)
        tot += c
        nivel = f"NIVEL TERMINADO en frame {fin}" if fin is not None else "no termino"
        print(f"semilla {s + 1}: celdas {c}, kills {k}, muertes {m}, {nivel}", flush=True)
    print(f"promedio celdas: {tot / a.semillas:.1f}")
