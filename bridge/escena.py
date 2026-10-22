"""Escena de depuracion: pone al bot en un punto del mapa, con llaves e interruptores, y traza.

Para no esperar miles de frames hasta el momento que falla. Usa trucos de consola de ZDoom
(sv_cheats: give, god, warp), asi que el resultado no cuenta como partida real.

Uso:
  python escena.py --mapa MAP02 --x 540 --y -800 --llaves azul,roja,amarilla --presionados 1,2,3,4,5
"""
import argparse
import os

import vizdoom as vzd

import doom_bridge as db
import navegacion as nv

DAR = {"azul": "bluecard", "amarilla": "yellowcard", "roja": "redcard"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapa", default="MAP01")
    ap.add_argument("--x", type=float, required=True)
    ap.add_argument("--y", type=float, required=True)
    ap.add_argument("--llaves", default="")
    ap.add_argument("--presionados", default="", help="indices de metas_uso ya usados")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--orden", default="avanzar")
    ap.add_argument("--cada", type=int, default=4, help="imprimir cada N frames")
    a = ap.parse_args()

    g = vzd.DoomGame()
    g.set_doom_scenario_path(os.path.join(os.path.dirname(vzd.__file__), "freedoom2.wad"))
    g.set_doom_map(a.mapa)
    g.set_doom_skill(2)
    g.set_window_visible(False)
    g.set_screen_resolution(vzd.ScreenResolution.RES_320X240)
    g.set_labels_buffer_enabled(True)
    g.set_depth_buffer_enabled(True)
    g.set_sectors_info_enabled(True)
    g.set_objects_info_enabled(True)
    g.set_available_buttons([getattr(vzd.Button, n) for n in db.B])
    g.set_available_game_variables([
        vzd.GameVariable.HEALTH, vzd.GameVariable.ARMOR, vzd.GameVariable.SELECTED_WEAPON_AMMO,
        vzd.GameVariable.KILLCOUNT, vzd.GameVariable.POSITION_X, vzd.GameVariable.POSITION_Y,
        vzd.GameVariable.ANGLE, vzd.GameVariable.WEAPON3, vzd.GameVariable.WEAPON4,
        vzd.GameVariable.WEAPON5, vzd.GameVariable.WEAPON6, vzd.GameVariable.WEAPON7,
        vzd.GameVariable.SELECTED_WEAPON])
    g.add_game_args("+sv_cheats 1")
    g.init()
    g.make_action([0] * len(db.B), 10)
    llaves = {k for k in a.llaves.split(",") if k}
    for k in llaves:
        g.send_game_command(f"give {DAR[k]}")
    g.send_game_command("god")
    g.send_game_command(f"warp {a.x} {a.y}")
    g.make_action([0] * len(db.B), 4)

    m = nv.cargar(a.mapa)
    m.llaves = set(llaves)
    m.presionados = {int(i) for i in a.presionados.split(",") if i}
    nav = nv.Navegador(m)
    cerebro = db.Cerebro(nav)
    for n in range(a.frames):
        if g.is_episode_finished():
            print(n, "FIN:", "nivel terminado" if not g.is_player_dead() else "muerto")
            break
        st = g.get_state()
        v = st.game_variables
        act, _ = cerebro.decidir(st, v, a.orden)
        if n % a.cada == 0 or nav.evento:
            botones = [db.B[i] for i, b in enumerate(act) if b and i < len(db.B) - 1]
            print(n, (round(v[4]), round(v[5])), round(v[6]), cerebro.modo, botones,
                  round(act[-1], 1), "meta", nav.meta["id"] if nav.meta else None, nav.evento)
        g.make_action(act, 4)
    g.close()


if __name__ == "__main__":
    main()
