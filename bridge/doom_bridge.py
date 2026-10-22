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
MODOS = ("atacar", "explorar", "retirada", "recoger", "avanzar", "curarse")
# tactica de Jev -> modo del cerebro (None = Jev dudo: decide el script)
TACTICA_A_MODO = {"pelear": "atacar", "esquivar": "retirada", "avanzar": "avanzar", "curarse": "curarse",
                  None: "explorar"}
SALUD_CRITICA = 30  # regla de supervivencia del script: debajo de esto deja de pelear

# Indices de botones
B = ["MOVE_FORWARD", "MOVE_BACKWARD", "TURN_LEFT", "TURN_RIGHT",
     "MOVE_LEFT", "MOVE_RIGHT", "ATTACK", "USE",
     "SELECT_WEAPON2", "SELECT_WEAPON3", "SELECT_WEAPON4",
     "TURN_LEFT_RIGHT_DELTA"]  # el giro fino va al final: es el unico boton con valor
IDX = {n: i for i, n in enumerate(B)}
TICS = 4  # tics por accion (35 tics = 1 s); main lo ajusta segun los fps


def accion(*nombres, giro=0.0):
    """Botones del juego. giro: grados a girar en esta accion (positivo = izquierda).

    TURN_LEFT_RIGHT_DELTA gira esos grados POR TIC y positivo es a la derecha, de ahi el -giro/TICS.
    """
    a = [0.0] * len(B)
    for n in nombres:
        a[IDX[n]] = 1
    if giro:
        a[IDX["TURN_LEFT_RIGHT_DELTA"]] = -giro / TICS
    return a


def siguiente_mapa(mapa):
    n = int(mapa[3:]) + 1
    return f"MAP{n:02d}" if n <= 32 else "MAP01"


def crear_juego(mapa="MAP01"):
    g = vzd.DoomGame()
    base = os.path.dirname(vzd.__file__)
    g.set_doom_scenario_path(os.path.join(base, "freedoom2.wad"))
    g.set_doom_map(mapa)
    g.set_doom_skill(2)
    g.set_screen_resolution(vzd.ScreenResolution.RES_320X240)
    g.set_screen_format(vzd.ScreenFormat.RGB24)
    g.set_window_visible(False)
    g.set_sound_enabled(False)
    g.set_labels_buffer_enabled(True)
    g.set_depth_buffer_enabled(True)
    g.set_sectors_info_enabled(True)
    g.set_objects_info_enabled(True)  # para saber que llaves siguen en el mapa
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
        # armas que trae, por casillero (3 escopetas, 4 ametralladora, 5 cohetes, 6 plasma, 7 BFG)
        vzd.GameVariable.WEAPON3, vzd.GameVariable.WEAPON4, vzd.GameVariable.WEAPON5,
        vzd.GameVariable.WEAPON6, vzd.GameVariable.WEAPON7,
        vzd.GameVariable.SELECTED_WEAPON,
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


# proyectiles de monstruos que se pueden esquivar (los disparos de zombis y escopeteros son
# instantaneos: a esos no se les esquiva, se les mata primero)
PROYECTILES = {"DoomImpBall", "CacodemonBall", "BaronBall", "RevenantTracer", "FatShot",
               "ArachnotronPlasma", "Rocket", "BFGBall", "PlasmaBall"}
# a quien dispararle primero: arch-vile siempre; luego los de disparo instantaneo
PRIORIDAD = {"Archvile": 100, "ChaingunGuy": 60, "ShotgunGuy": 50, "WolfensteinSS": 40,
             "Zombieman": 30, "Revenant": 25, "DoomImp": 20}


def esquivar(objetos, x, y, angulo):
    """MOVE_LEFT/MOVE_RIGHT si un proyectil va a pasar a menos de 48 unidades en el proximo
    segundo; None si no hay peligro. Se mueve hacia el lado contrario al punto de paso."""
    a = math.radians(angulo)
    derecha = (math.sin(a), -math.cos(a))  # en Doom el angulo 0 mira al este y crece a la izquierda
    for o in objetos:
        if o.name not in PROYECTILES:
            continue
        px, py = o.position_x - x, o.position_y - y
        vx, vy = o.velocity_x, o.velocity_y
        v2 = vx * vx + vy * vy
        if v2 < 1:
            continue
        t = -(px * vx + py * vy) / v2  # tics hasta el punto mas cercano
        if not 0 < t < 35:
            continue
        cx, cy = px + vx * t, py + vy * t
        if math.hypot(cx, cy) < 48:
            # alejarse del punto por donde pasara
            lado = -(cx * derecha[0] + cy * derecha[1])
            return "MOVE_RIGHT" if lado > 0 else "MOVE_LEFT"
    return None


def peligro_barril(objetos, x, y, angulo, grados_objetivo):
    """(no_disparar, alejarse): MAP04 mataba al bot con salud 52 cada vida en el mismo punto,
    a 56 unidades de un barril al que le daba disparando a los enemigos de al lado.

    no_disparar: hay un barril a menos de 250 unidades cerca de la linea de tiro.
    alejarse: 'MOVE_LEFT'/'MOVE_RIGHT'/'MOVE_BACKWARD' si hay uno a menos de 100.
    """
    no_disparar, alejarse = False, None
    for o in objetos:
        if o.name != "ExplosiveBarrel":
            continue
        dx, dy = o.position_x - x, o.position_y - y
        d = math.hypot(dx, dy)
        if d > 250:
            continue
        # angulo del barril respecto a la mira (positivo = a la izquierda)
        rel = (math.degrees(math.atan2(dy, dx)) - angulo + 180) % 360 - 180
        if abs(rel - (-grados_objetivo)) < 12:
            no_disparar = True
        if d < 100:
            alejarse = "MOVE_BACKWARD" if abs(rel) < 45 else ("MOVE_RIGHT" if rel > 0 else "MOVE_LEFT")
    return no_disparar, alejarse


def elegir_objetivo(enemigos, x, y):
    def puntaje(l):
        d = math.hypot(l.object_position_x - x, l.object_position_y - y)
        return PRIORIDAD.get(l.object_name, 10) * 1000 - d
    return max(enemigos, key=puntaje)


def elegir_arma(obj, x, y, vars_):
    """Boton SELECT_WEAPONn a mandar, o None si el arma de ahora ya sirve.

    vars_[7:12] = casilleros 3..7 que trae, vars_[12] = arma seleccionada.
    Escopeta de cerca, ametralladora a media y larga distancia, pistola si no hay otra.
    """
    if len(vars_) < 13:
        return None
    tiene = {k for k, v in zip((3, 4, 5, 6, 7), vars_[7:12]) if v > 0}
    d = math.hypot(obj.object_position_x - x, obj.object_position_y - y)
    if 3 in tiene and (d < 450 or 4 not in tiene):
        quiero = 3
    elif 4 in tiene:
        quiero = 4
    else:
        quiero = 2
    return None if int(vars_[12]) == quiero else f"SELECT_WEAPON{quiero}"


class Cerebro:
    """Reflejos: apuntar y disparar, esquivar paredes, abrir puertas, salir de atorones."""

    def __init__(self, navegador=None):
        self.navegador = navegador
        self.modo = "explorar"
        self.historial = []
        self.giro_forzado = 0
        self.dir_giro = "TURN_LEFT"
        self.paso = 0
        # objetos a los que no se pudo llegar: clave de posicion -> paso hasta el que se ignoran
        self.ignorados = {}
        self.cesion = 0  # pasos en que el navegador manda aunque la orden diga otra cosa
        self.salud_prev = 100
        self.voltear = 0  # pasos girando hacia quien le pega sin que se vea en pantalla

    @staticmethod
    def clave(l):
        return (round(l.object_position_x / 32), round(l.object_position_y / 32))

    def alcanzables(self, labels):
        return [l for l in labels if l.object_name in OBJETOS
                and self.ignorados.get(self.clave(l), 0) < self.paso]

    def decidir(self, st, vars_, orden):
        self.paso += 1
        self.evento = None
        if self.navegador:
            # si este frame pelea, el navegador no corre: que no se reporte su evento viejo otra vez
            self.navegador.evento = None
        ancho = st.screen_buffer.shape[1]
        x, y = vars_[4], vars_[5]
        enemigos = [l for l in st.labels if l.object_name in MONSTRUOS]
        objetos = self.alcanzables(st.labels)
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
        # regla de supervivencia del script (cuando decide el script: orden "explorar" o Jev dudo).
        # Antes peleaba hasta morir con salud 1-7 (MAP02-04): con poca salud, ir por un botiquin
        # si hay uno con ruta; si no lo hay y lo rodean, retroceder disparando.
        if orden == "explorar" and vars_[0] < SALUD_CRITICA and self.navegador:
            # ir a curarse dandole la espalda a los enemigos mataba (18 muertes en "curarse"):
            # solo si no hay enemigos a la vista o el botiquin esta a menos de 300
            cerca_salud = self.navegador.distancia_salud()
            if cerca_salud is not None and (not enemigos or cerca_salud < 300):
                modo = "curarse"
            elif len(enemigos) >= 2:
                modo = "retirada"
        if modo == "curarse" and not (self.navegador and self.navegador.hay_salud()):
            modo = "atacar" if enemigos else "explorar"
        # atorado yendo por un objeto o retrocediendo: el objeto queda ignorado ~30 s y el
        # navegador toma el control un rato (si no, Jev lo sigue viendo y lo vuelve a elegir)
        if atorado and modo in ("recoger", "retirada") and self.navegador:
            if modo == "recoger" and objetos:
                obj = max(objetos, key=lambda l: l.width * l.height)
                self.ignorados[self.clave(obj)] = self.paso + 270
                self.evento = ("inalcanzable", obj.object_name,
                               [round(obj.object_position_x), round(obj.object_position_y)])
            self.cesion = 45
            self.historial.clear()
        if self.cesion > 0:
            self.cesion -= 1
            if modo in ("recoger", "retirada"):
                modo = "explorar"
        self.modo = modo

        if self.giro_forzado > 0:
            self.giro_forzado -= 1
            return accion(self.dir_giro, "USE"), atorado

        def apuntar(l, extra):
            # FOV horizontal de 90 grados: el borde de la pantalla esta a 45
            cx = l.x + l.width / 2
            grados = math.degrees(math.atan((cx - ancho / 2) / (ancho / 2)))
            if abs(grados) < 3:
                return None
            return accion(*extra, giro=-grados)

        # reflejo de supervivencia, en cualquier modo: esquivar un proyectil que viene directo
        esquive = esquivar(st.objects, x, y, vars_[6])

        # le pegan sin que se vea a nadie: voltear hacia el monstruo mas cercano (puede estar
        # detras). MAP04: 33 de 48 muertes en "explorar" con imps a 30-110 unidades, fuera de cuadro
        perdio_salud = vars_[0] < self.salud_prev
        self.salud_prev = vars_[0]
        if perdio_salud and not enemigos:
            self.voltear = 6
        if self.voltear > 0 and not enemigos:
            self.voltear -= 1
            cercanos = [o for o in st.objects if o.name in MONSTRUOS
                        and math.hypot(o.position_x - x, o.position_y - y) < 500]
            if cercanos:
                o = min(cercanos, key=lambda o: math.hypot(o.position_x - x, o.position_y - y))
                dif = (math.degrees(math.atan2(o.position_y - y, o.position_x - x)) - vars_[6] + 180) % 360 - 180
                if self.voltear == 5:  # un evento por reflejo, no uno por cada paso del giro
                    self.evento = ("voltear", o.name, round(dif))
                return accion(esquive, giro=max(-45, min(45, dif))) if esquive else \
                    accion(giro=max(-45, min(45, dif))), atorado
        elif enemigos:
            self.voltear = 0

        if modo == "atacar":
            obj = elegir_objetivo(enemigos, x, y)
            cx = obj.x + obj.width / 2
            grados = math.degrees(math.atan((cx - ancho / 2) / (ancho / 2)))
            lateral = esquive or ("MOVE_LEFT" if (self.paso // 10) % 2 else "MOVE_RIGHT")
            arma = elegir_arma(obj, x, y, vars_)
            extra = [arma] if arma else []
            no_disparar, alejarse = peligro_barril(st.objects, x, y, vars_[6], grados)
            if alejarse:
                lateral = alejarse
            # gira justo lo que falta y dispara en el mismo paso si ya casi esta centrado
            if abs(grados) < 8 and not no_disparar:
                return accion("ATTACK", lateral, *extra, giro=-grados), atorado
            return accion(lateral, *extra, giro=-grados), atorado
        if esquive and enemigos:
            # fuera de pelea pero con un proyectil encima: hacerse a un lado sin perder el rumbo
            return accion(esquive, "MOVE_FORWARD"), atorado

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

        # explorar / avanzar / curarse: con mapa, el navegador decide; sin mapa, reflejos a ciegas
        if self.navegador:
            self.navegador.forzar = "salud" if modo == "curarse" else None
            a = self.navegador.decidir(x, y, vars_[6], st.sectors, accion, st.objects,
                                       salud=vars_[0], municion=vars_[2],
                                       armas={k for k, val in zip((3, 4, 5, 6, 7), vars_[7:12]) if val > 0},
                                       arma_actual=int(vars_[12]) if len(vars_) > 12 else None)
            # avanzar ignora a los enemigos, pero si uno queda justo enfrente se le dispara al pasar
            if modo == "avanzar" and enemigos:
                obj = max(enemigos, key=lambda l: l.width * l.height)
                cx = obj.x + obj.width / 2
                if abs(math.degrees(math.atan((cx - ancho / 2) / (ancho / 2)))) < 5:
                    a[IDX["ATTACK"]] = 1
            return a, atorado
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


def describir(st, vars_, atorado, muertes, ancho, cerebro=None):
    enemigos = [l for l in st.labels if l.object_name in MONSTRUOS]
    # sin los objetos ya marcados como inalcanzables, para que Jev no los vuelva a elegir
    objetos = cerebro.alcanzables(st.labels) if cerebro else [l for l in st.labels if l.object_name in OBJETOS]
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


OBJETOS_EN = {
    "Medikit": "medikit", "Stimpack": "stimpack", "HealthBonus": "health bonus",
    "ArmorBonus": "armor bonus", "GreenArmor": "green armor", "BlueArmor": "blue armor",
    "Clip": "clip", "ClipBox": "box of bullets", "Shell": "shells", "ShellBox": "box of shells",
    "Shotgun": "shotgun", "SuperShotgun": "super shotgun", "Chaingun": "chaingun",
    "RocketLauncher": "rocket launcher", "RocketAmmo": "rocket", "Soulsphere": "soulsphere",
    "Backpack": "backpack", "Berserk": "berserk",
}
COLOR_EN = {"roja": "red", "azul": "blue", "amarilla": "yellow"}


def nombre_meta(id_, idioma="es"):
    """Id interno de meta -> texto corto para el panel (llave_roja -> 'llave roja' / 'red key')."""
    if not id_:
        return "-"
    base = id_.split("_")[0]
    resto = id_.split("_")[1] if "_" in id_ else ""
    if idioma == "en":
        return {"llave": f"{COLOR_EN.get(resto, resto)} key", "interruptor": f"switch {resto}",
                "pisar": f"walk-over line {resto}", "municion": "ammo", "salud": "health",
                "arma": "weapon", "frontera": "unexplored area", "salida": "exit"}.get(base, id_)
    return {"llave": f"llave {resto}", "interruptor": f"interruptor {resto}",
            "pisar": f"linea {resto} al pisar", "municion": "municion", "salud": "salud",
            "arma": "arma", "frontera": "zona sin explorar", "salida": "salida"}.get(base, id_)


def estado_panel(st, vars_, muertes, ancho, cerebro, mapa, niveles, idioma):
    """Linea de estado que se ve en el panel, en el idioma de la partida.

    Jev sigue recibiendo la version en espanol de describir(): sus preguntas estan probadas asi.
    """
    nav = cerebro.navegador
    if idioma != "en":
        return (f"Mapa {mapa}, niveles terminados {niveles}. "
                + describir(st, vars_, False, muertes, ancho, cerebro) + " " + nav.resumen())
    enemigos = [l for l in st.labels if l.object_name in MONSTRUOS]
    objetos = cerebro.alcanzables(st.labels)
    px, py = vars_[4], vars_[5]

    def dist(l):
        return int(math.hypot(l.object_position_x - px, l.object_position_y - py))

    def donde(l):
        rel = (l.x + l.width / 2 - ancho / 2) / (ancho / 2)
        return "left" if rel < -0.35 else ("right" if rel > 0.35 else "ahead")

    e_txt = "; ".join(f"{l.object_name} {dist(l)} {donde(l)}" for l in sorted(enemigos, key=dist)[:5]) or "none"
    o_txt = "; ".join(f"{OBJETOS_EN.get(l.object_name, l.object_name)} {dist(l)} {donde(l)}"
                      for l in sorted(objetos, key=dist)[:5]) or "none"
    llaves = ", ".join(COLOR_EN.get(c, c) for c in sorted(nav.mapa.llaves)) or "none"
    meta = nombre_meta(nav.meta["id"], "en") if nav.meta else "none"
    return (f"Map {mapa}, levels done {niveles}. Health {int(vars_[0])}, armor {int(vars_[1])}, "
            f"ammo {int(vars_[2])}, kills {int(vars_[3])}, deaths {muertes}. Enemies: {e_txt}. "
            f"Items: {o_txt}. Goal: {meta}, {len(nav.camino)} steps. "
            f"Switches used: {len(nav.mapa.presionados)}. Keys: {llaves}.")


def leer_plan(ruta):
    """Lista de ids de metas que escribio el planificador, o None si no hay plan nuevo."""
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        p = d.get("plan")
        return [str(x) for x in p][:5] if isinstance(p, list) else None
    except (OSError, ValueError):
        return None


def leer_orden(ruta, actual):
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        m = d.get("modo")
        return m if m in MODOS else actual
    except (OSError, ValueError):
        return actual


class Bitacora:
    """Una linea JSON por evento en el archivo de la partida, para depurar decisiones."""

    def __init__(self, ruta):
        if ruta:
            os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        self.f = open(ruta, "a", encoding="utf-8") if ruta else None
        self.lock = threading.Lock()
        self.t0 = time.time()

    def __call__(self, evento, **datos):
        if not self.f:
            return
        datos = {"t": round(time.time() - self.t0, 2), "ev": evento, **datos}
        with self.lock:
            self.f.write(json.dumps(datos, ensure_ascii=False) + "\n")
            self.f.flush()


class HiloJev:
    """Consulta a Jev en segundo plano con el frame mas reciente; el juego nunca lo espera."""

    def __init__(self, log):
        from jev_pilot import PilotoJev
        self.log = log
        self.piloto = PilotoJev(con_imagen=True)
        self.lock = threading.Lock()
        self.entrada = None
        self.modo = "explorar"   # tactica traducida a modo del cerebro
        self.meta = None         # id de meta que Jev pidio con confianza (None = dudo)
        self.info = {"ms": 0, "probs": {}, "probs_meta": {}, "meta": None, "peligro": 0.0,
                     "llamadas": 0, "dudas": 0, "errores": 0, "ultimo_error": ""}
        threading.Thread(target=self._bucle, daemon=True).start()

    def ofrecer(self, frame, estado, metas, n=0):
        with self.lock:
            self.entrada = (frame.copy(), estado, list(metas), n)

    def _bucle(self):
        while True:
            with self.lock:
                e, self.entrada = self.entrada, None
            if e is None:
                time.sleep(0.05)
                continue
            try:
                d = self.piloto.decidir(e[0], e[1], e[2])
                self.log("jev", frame=e[3], estado=e[1], tactica=d["tactica"], cruda=d["tactica_cruda"],
                         brecha=d["brecha_tactica"], probs=d["probs"], meta=d["meta"],
                         brecha_meta=d["brecha_meta"], probs_meta=d["probs_meta"],
                         peligro=round(d["peligro"], 2), ms=d["ms"])
                with self.lock:
                    self.modo = TACTICA_A_MODO[d["tactica"]]
                    self.meta = d["meta"]
                    self.info.update(ms=d["ms"], probs=d["probs"], probs_meta=d["probs_meta"] or {},
                                     meta=d["meta"], peligro=round(d["peligro"], 2),
                                     llamadas=self.info["llamadas"] + 1,
                                     dudas=self.info["dudas"] + (d["tactica"] is None))
            except Exception as ex:
                # 403/429/499 son fallas, no decisiones: el script decide mientras tanto
                self.log("jev_error", error=str(ex)[:200])
                with self.lock:
                    self.modo, self.meta = "explorar", None
                    self.info["errores"] += 1
                    self.info["ultimo_error"] = str(ex)[:120]
                time.sleep(2 if "429" in str(ex) else 1)
            time.sleep(0.25)

    def leer(self):
        with self.lock:
            return self.modo, self.meta, dict(self.info)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ordenes", required=True)
    ap.add_argument("--cols", type=int, default=80)
    ap.add_argument("--filas", type=int, default=25)
    ap.add_argument("--fps", type=float, default=9)
    ap.add_argument("--frames", type=int, default=0, help="0 = sin limite")
    ap.add_argument("--log", default="", help="archivo .jsonl con las decisiones de la partida")
    ap.add_argument("--piloto", choices=["jev", "claude"], default="jev")
    ap.add_argument("--pantalla", default="", help="json {cols, filas} que el panel actualiza al redimensionar")
    ap.add_argument("--mapa", default="MAP01")
    ap.add_argument("--idioma", choices=["es", "en"], default="es", help="idioma de lo que se ve en el panel")
    a = ap.parse_args()

    import navegacion
    mapa = a.mapa.upper()
    g = crear_juego(mapa)
    log = Bitacora(a.log)
    log("inicio", piloto=a.piloto, mapa=mapa, cols=a.cols, filas=a.filas)
    jev = HiloJev(log) if a.piloto == "jev" else None
    previo = {"modo": None, "orden": None, "kills": 0, "atorado": False}
    cerebro = Cerebro(navegacion.Navegador(navegacion.cargar(mapa)))
    niveles = 0
    orden = "explorar"
    muertes = 0
    tics = max(1, round(35 / a.fps))
    global TICS
    TICS = tics
    n = 0
    ultimo_mtime = 0
    mtime_pantalla = 0
    while a.frames == 0 or n < a.frames:
        t0 = time.time()
        if g.is_episode_finished() and not g.is_player_dead():
            # nivel terminado: al siguiente mapa, con su propio navegador
            niveles += 1
            log("nivel_terminado", frame=n, mapa=mapa, niveles=niveles)
            mapa = siguiente_mapa(mapa)
            g.set_doom_map(mapa)
            g.new_episode()
            cerebro = Cerebro(navegacion.Navegador(navegacion.cargar(mapa)))
            previo["kills"] = 0
            log("mapa", frame=n, mapa=mapa)
        elif g.is_player_dead():
            muertes += 1
            log("muerte", frame=n, muertes=muertes, mapa=mapa)
            g.new_episode()
            cerebro = Cerebro(navegacion.Navegador(navegacion.cargar(mapa)))
            previo["kills"] = 0
        # plan de Haiku (lo escribe el mod en el archivo de ordenes); vale con o sin Jev
        try:
            mt = os.path.getmtime(a.ordenes)
            if mt != ultimo_mtime:
                ultimo_mtime = mt
                plan = leer_plan(a.ordenes)
                if plan is not None:
                    cerebro.navegador.plan = plan
                    log("plan_claude", frame=n, plan=plan)
        except OSError:
            pass
        info_jev = None
        if jev:
            orden, cerebro.navegador.pedido_jev, info_jev = jev.leer()
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
        nav = cerebro.navegador
        estado = (f"Mapa {mapa}, niveles terminados {niveles}. "
                  + describir(st, vars_, atorado, muertes, st.screen_buffer.shape[1], cerebro)
                  + " " + nav.resumen())
        if nav.evento:
            log("nav", frame=n, que=list(nav.evento), pos=[round(vars_[4]), round(vars_[5])])
        if cerebro.evento:
            log("cerebro", frame=n, que=list(cerebro.evento), orden=orden, pos=[round(vars_[4]), round(vars_[5])])
        if jev:
            metas = [(c["id"], f"{c['desc']}, a {c['dist']} unidades") for c in nav.cands][:8]
            jev.ofrecer(st.screen_buffer, estado, metas, n)
        pos = [round(vars_[4]), round(vars_[5])]
        if cerebro.modo != previo["modo"]:
            log("modo", frame=n, de=previo["modo"], a=cerebro.modo, orden=orden, pos=pos, estado=estado)
        if int(vars_[3]) > previo["kills"]:
            log("kill", frame=n, kills=int(vars_[3]), pos=pos)
        if atorado and not previo["atorado"]:
            log("atorado", frame=n, pos=pos, angulo=round(vars_[6]))
        previo.update(modo=cerebro.modo, kills=int(vars_[3]), atorado=atorado)
        if n % 35 == 0:
            log("pos", frame=n, pos=pos, angulo=round(vars_[6]), salud=int(vars_[0]))
        linea = {
            "t": "f",
            "n": n,
            "filas": a_celdas(st.screen_buffer, a.cols, a.filas),
            "modo": cerebro.modo,
            "orden": orden,
            "mapa": mapa,
            "niveles": niveles,
            "estado": estado,
            "estado_ui": estado_panel(st, vars_, muertes, st.screen_buffer.shape[1], cerebro, mapa,
                                      niveles, a.idioma),
            "meta_ui": nombre_meta(nav.meta["id"], a.idioma) if nav.meta else None,
            "plan_ui": [nombre_meta(p, a.idioma) for p in nav.plan],
            "piloto": a.piloto,
            "jev": info_jev,
            "meta": nav.meta["id"] if nav.meta else None,
            "plan": nav.plan,
        }
        # el rompecabezas del nivel para el planificador (Haiku), cada ~5 s
        if n % 45 == 0 and nav.cands:
            linea["resumen_mapa"] = nav.resumen_mapa(vars_[4], vars_[5])
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
