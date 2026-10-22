"""Puente Doom -> Claude Code.

Corre ViZDoom sin ventana, maneja al jugador con reflejos simples y obedece la
estrategia que Claude escribe en un archivo de ordenes. Por stdout manda una
linea JSON por frame: el dibujo en celdas de medio bloque y el estado del juego.

Uso: python -u doom_bridge.py --ordenes ordenes.json [--cols 80] [--filas 25] [--fps 9]
"""
import argparse
import json
import math
import os
import random
import sys
import threading
import time

import numpy as np
import vizdoom as vzd

MONSTRUOS = {
    "Zombieman", "ShotgunGuy", "ChaingunGuy", "DoomImp", "Demon", "Spectre",
    "LostSoul", "Cacodemon", "HellKnight", "BaronOfHell", "Arachnotron",
    "PainElemental", "Revenant", "Fatso", "Archvile", "Cyberdemon",
    "SpiderMastermind", "WolfensteinSS",
}
OBJETOS = {
    "Medikit": "botiquin", "Stimpack": "estimulante", "HealthBonus": "bonus de salud",
    "ArmorBonus": "bonus de armadura", "GreenArmor": "armadura verde", "BlueArmor": "armadura azul",
    "Clip": "cargador", "ClipBox": "caja de balas", "Shell": "cartuchos", "ShellBox": "caja de cartuchos",
    "Shotgun": "escopeta", "SuperShotgun": "escopeta doble", "Chaingun": "ametralladora",
    "RocketLauncher": "lanzacohetes", "RocketAmmo": "cohete", "Soulsphere": "esfera de alma",
    "Backpack": "mochila", "Berserk": "berserk",
}
MODOS = ("atacar", "explorar", "retirada", "recoger")

# Indices de botones
B = ["MOVE_FORWARD", "MOVE_BACKWARD", "TURN_LEFT", "TURN_RIGHT",
     "MOVE_LEFT", "MOVE_RIGHT", "ATTACK", "USE"]
IDX = {n: i for i, n in enumerate(B)}


def accion(*nombres):
    a = [0] * len(B)
    for n in nombres:
        a[IDX[n]] = 1
    return a


def crear_juego():
    g = vzd.DoomGame()
    base = os.path.dirname(vzd.__file__)
    g.set_doom_scenario_path(os.path.join(base, "freedoom2.wad"))
    g.set_doom_map("MAP01")
    g.set_doom_skill(2)
    g.set_screen_resolution(vzd.ScreenResolution.RES_320X240)
    g.set_screen_format(vzd.ScreenFormat.RGB24)
    g.set_window_visible(False)
    g.set_sound_enabled(False)
    g.set_labels_buffer_enabled(True)
    g.set_depth_buffer_enabled(True)
    g.set_render_hud(True)
    g.set_render_weapon(True)
    g.set_render_messages(False)
    g.set_episode_timeout(0)
    g.set_available_buttons([getattr(vzd.Button, n) for n in B])
    g.set_available_game_variables([
        vzd.GameVariable.HEALTH, vzd.GameVariable.ARMOR,
        vzd.GameVariable.SELECTED_WEAPON_AMMO, vzd.GameVariable.KILLCOUNT,
        vzd.GameVariable.POSITION_X, vzd.GameVariable.POSITION_Y,
        vzd.GameVariable.ANGLE,
    ])
    g.set_mode(vzd.Mode.PLAYER)
    g.init()
    return g


def a_celdas(img, cols, filas):
    """Reduce el frame a cols x (filas*2) pixeles y arma corridas de medio bloque."""
    h, w, _ = img.shape
    ph = filas * 2
    ys = (np.arange(ph) * h / ph).astype(int)
    xs = (np.arange(cols) * w / cols).astype(int)
    peq = img[ys][:, xs].astype(np.int32)
    # 8 niveles por canal (paleta de 512): corridas mas largas, frames mas ligeros
    q = np.clip((peq // 32) * 36, 0, 255)
    codigo = (q[..., 0] << 16) | (q[..., 1] << 8) | q[..., 2]
    hexes = [["#%06x" % v for v in fila] for fila in codigo.tolist()]
    renglones = []
    for f in range(filas):
        arriba, abajo = hexes[2 * f], hexes[2 * f + 1]
        corridas = []
        for c in range(cols):
            par = (arriba[c], abajo[c])
            if corridas and corridas[-1][1] == par[0] and corridas[-1][2] == par[1]:
                corridas[-1][0] += 1
            else:
                corridas.append([1, par[0], par[1]])
        renglones.append(corridas)
    return renglones


def lado(cx, ancho):
    rel = (cx - ancho / 2) / (ancho / 2)
    if rel < -0.35:
        return "a la izquierda"
    if rel > 0.35:
        return "a la derecha"
    return "al frente"


class Cerebro:
    """Reflejos: apuntar y disparar, esquivar paredes, abrir puertas, salir de atorones."""

    def __init__(self):
        self.modo = "explorar"
        self.historial = []
        self.giro_forzado = 0
        self.dir_giro = "TURN_LEFT"
        self.paso = 0

    def decidir(self, st, vars_, orden):
        self.paso += 1
        ancho = st.screen_buffer.shape[1]
        x, y = vars_[4], vars_[5]
        enemigos = [l for l in st.labels if l.object_name in MONSTRUOS]
        objetos = [l for l in st.labels if l.object_name in OBJETOS]
        prof = st.depth_buffer
        hcen = prof.shape[0] // 2
        franja = prof[hcen - 20:hcen + 20]
        izq = float(franja[:, : ancho // 3].mean())
        cen = float(franja[:, ancho // 3: 2 * ancho // 3].mean())
        der = float(franja[:, 2 * ancho // 3:].mean())

        # deteccion de atoron
        self.historial.append((x, y))
        self.historial = self.historial[-12:]
        atorado = False
        if len(self.historial) == 12:
            dx = self.historial[-1][0] - self.historial[0][0]
            dy = self.historial[-1][1] - self.historial[0][1]
            atorado = math.hypot(dx, dy) < 24

        modo = orden
        if modo == "explorar" and enemigos:
            modo = "atacar"
        if modo == "recoger" and not objetos:
            modo = "atacar" if enemigos else "explorar"
        if modo == "atacar" and not enemigos:
            modo = "explorar"
        self.modo = modo

        if self.giro_forzado > 0:
            self.giro_forzado -= 1
            return accion(self.dir_giro, "USE"), atorado

        def apuntar(l, extra):
            cx = l.x + l.width / 2
            err = cx - ancho / 2
            tol = max(6, l.width / 4)
            if err < -tol:
                return accion("TURN_LEFT", *extra)
            if err > tol:
                return accion("TURN_RIGHT", *extra)
            return None

        if modo == "atacar":
            obj = max(enemigos, key=lambda l: l.width * l.height)
            a = apuntar(obj, [])
            if a is None:
                lateral = "MOVE_LEFT" if (self.paso // 10) % 2 else "MOVE_RIGHT"
                return accion("ATTACK", lateral), atorado
            return a, atorado

        if modo == "retirada":
            if enemigos:
                obj = max(enemigos, key=lambda l: l.width * l.height)
                a = apuntar(obj, ["MOVE_BACKWARD"])
                return (a or accion("MOVE_BACKWARD", "ATTACK")), atorado
            return accion("MOVE_FORWARD", "TURN_LEFT" if izq > der else "TURN_RIGHT"), atorado

        if modo == "recoger":
            obj = max(objetos, key=lambda l: l.width * l.height)
            a = apuntar(obj, ["MOVE_FORWARD"])
            return (a or accion("MOVE_FORWARD")), atorado

        # explorar
        if atorado:
            self.dir_giro = random.choice(["TURN_LEFT", "TURN_RIGHT"])
            self.giro_forzado = random.randint(4, 10)
            self.historial.clear()
            return accion("MOVE_BACKWARD", "USE"), atorado
        if cen < 18:
            return accion("TURN_LEFT" if izq > der else "TURN_RIGHT", "USE"), atorado
        if izq > cen * 1.6 and self.paso % 40 < 6:
            return accion("MOVE_FORWARD", "TURN_LEFT"), atorado
        if der > cen * 1.6 and self.paso % 40 >= 34:
            return accion("MOVE_FORWARD", "TURN_RIGHT"), atorado
        return accion("MOVE_FORWARD", "USE") if self.paso % 8 == 0 else accion("MOVE_FORWARD"), atorado


def describir(st, vars_, atorado, muertes, ancho):
    enemigos = [l for l in st.labels if l.object_name in MONSTRUOS]
    objetos = [l for l in st.labels if l.object_name in OBJETOS]
    px, py = vars_[4], vars_[5]

    def dist(l):
        return int(math.hypot(l.object_position_x - px, l.object_position_y - py))

    e_txt = "; ".join(f"{l.object_name} a {dist(l)} {lado(l.x + l.width / 2, ancho)}"
                      for l in sorted(enemigos, key=dist)[:5]) or "ninguno"
    o_txt = "; ".join(f"{OBJETOS[l.object_name]} a {dist(l)} {lado(l.x + l.width / 2, ancho)}"
                      for l in sorted(objetos, key=dist)[:5]) or "ninguno"
    return (f"Salud {int(vars_[0])}, armadura {int(vars_[1])}, municion {int(vars_[2])}, "
            f"kills {int(vars_[3])}, muertes {muertes}. Enemigos visibles: {e_txt}. "
            f"Objetos visibles: {o_txt}. Atorado: {'si' if atorado else 'no'}.")


def leer_orden(ruta, actual):
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        m = d.get("modo")
        return m if m in MODOS else actual
    except (OSError, ValueError):
        return actual


class HiloJev:
    """Consulta a Jev en segundo plano con el frame mas reciente; el juego nunca lo espera."""

    def __init__(self):
        from jev_pilot import PilotoJev
        self.piloto = PilotoJev(con_imagen=True)
        self.lock = threading.Lock()
        self.entrada = None
        self.modo = "explorar"
        self.info = {"ms": 0, "probs": {}, "peligro": 0.0, "llamadas": 0, "errores": 0, "ultimo_error": ""}
        threading.Thread(target=self._bucle, daemon=True).start()

    def ofrecer(self, frame, estado, modo):
        with self.lock:
            self.entrada = (frame.copy(), estado, modo)

    def _bucle(self):
        while True:
            with self.lock:
                e, self.entrada = self.entrada, None
            if e is None:
                time.sleep(0.05)
                continue
            try:
                modo, probs, peligro, ms = self.piloto.decidir(*e)
                with self.lock:
                    self.modo = modo
                    self.info.update(ms=ms, probs=probs, peligro=round(peligro, 2),
                                     llamadas=self.info["llamadas"] + 1)
            except Exception as ex:
                with self.lock:
                    self.info["errores"] += 1
                    self.info["ultimo_error"] = str(ex)[:120]
                time.sleep(1)
            time.sleep(0.25)

    def leer(self):
        with self.lock:
            return self.modo, dict(self.info)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ordenes", required=True)
    ap.add_argument("--cols", type=int, default=80)
    ap.add_argument("--filas", type=int, default=25)
    ap.add_argument("--fps", type=float, default=9)
    ap.add_argument("--frames", type=int, default=0, help="0 = sin limite")
    ap.add_argument("--piloto", choices=["jev", "claude"], default="jev")
    ap.add_argument("--pantalla", default="", help="json {cols, filas} que el panel actualiza al redimensionar")
    a = ap.parse_args()

    g = crear_juego()
    jev = HiloJev() if a.piloto == "jev" else None
    cerebro = Cerebro()
    orden = "explorar"
    muertes = 0
    tics = max(1, round(35 / a.fps))
    n = 0
    ultimo_mtime = 0
    mtime_pantalla = 0
    while a.frames == 0 or n < a.frames:
        t0 = time.time()
        if g.is_episode_finished() or g.is_player_dead():
            if g.is_player_dead():
                muertes += 1
            g.new_episode()
        info_jev = None
        if jev:
            orden, info_jev = jev.leer()
        else:
            try:
                mt = os.path.getmtime(a.ordenes)
                if mt != ultimo_mtime:
                    ultimo_mtime = mt
                    orden = leer_orden(a.ordenes, orden)
            except OSError:
                pass
        if a.pantalla:
            try:
                mt = os.path.getmtime(a.pantalla)
                if mt != mtime_pantalla:
                    mtime_pantalla = mt
                    with open(a.pantalla, encoding="utf-8") as f:
                        d = json.load(f)
                    a.cols = max(16, min(240, int(d.get("cols", a.cols))))
                    a.filas = max(6, min(90, int(d.get("filas", a.filas))))
            except (OSError, ValueError):
                pass
        st = g.get_state()
        if st is None:
            g.advance_action(1)
            continue
        vars_ = st.game_variables
        act, atorado = cerebro.decidir(st, vars_, orden)
        estado = describir(st, vars_, atorado, muertes, st.screen_buffer.shape[1])
        if jev:
            jev.ofrecer(st.screen_buffer, estado, cerebro.modo)
        linea = {
            "t": "f",
            "n": n,
            "filas": a_celdas(st.screen_buffer, a.cols, a.filas),
            "modo": cerebro.modo,
            "orden": orden,
            "estado": estado,
            "piloto": a.piloto,
            "jev": info_jev,
        }
        sys.stdout.write(json.dumps(linea, separators=(",", ":")) + "\n")
        sys.stdout.flush()
        g.make_action(act, tics)
        n += 1
        espera = tics / 35 - (time.time() - t0)
        if espera > 0:
            time.sleep(espera)
    g.close()


if __name__ == "__main__":
    main()
