"""Navegacion con el mapa real: lee el WAD (paredes, puertas, interruptores, salida) y
calcula rutas con A* sobre una cuadricula.

Metas, en orden:
1. la salida, si hay ruta;
2. el interruptor sin presionar mas cercano con ruta (abren puertas remotas, bajan elevadores);
3. la zona sin visitar mas cercana (frontera).

Las puertas que se abren con USE cuentan como paso; al llegar a una cerrada, el bot la abre.
Las alturas de piso y techo se actualizan con los sectores que reporta ViZDoom en vivo.
"""
import heapq
import math
import os

import numpy as np
import omg
from omg.mapedit import MapEditor

CEL = 16          # lado de la celda, en unidades del mapa
RADIO = 20        # holgura contra paredes (el jugador mide 16 de radio)
# holgura de ultimo recurso, cuando ya no queda ninguna meta con ruta: con 20 la cuadricula cierra
# en las esquinas pasillos de 60 unidades (MAP04, jaula de la llave roja), pero usar 14 siempre
# rozaba paredes y se atoraba (MAP02: de 3/3 a 1/3 terminados)
RADIO_FINO = 14
PASO_MAX = 24     # escalon mas alto que se puede subir
ALTO_MIN = 56     # hueco minimo entre piso y techo

PUERTAS_USE = {1, 26, 27, 28, 31, 32, 33, 34, 117, 118}
# puertas con llave: accion -> color (las de USE directo y las de interruptor con llave)
LLAVE_DE_ACCION = {26: "azul", 32: "azul", 99: "azul", 133: "azul",
                   27: "amarilla", 34: "amarilla", 136: "amarilla", 137: "amarilla",
                   28: "roja", 33: "roja", 134: "roja", 135: "roja"}
# cosas del WAD que son llaves: tipo -> (color, nombre en ViZDoom)
LLAVES = {5: ("azul", "BlueCard"), 40: ("azul", "BlueSkull"),
          6: ("amarilla", "YellowCard"), 39: ("amarilla", "YellowSkull"),
          13: ("roja", "RedCard"), 38: ("roja", "RedSkull")}
INTERRUPTORES = {7, 9, 11, 14, 15, 18, 20, 21, 23, 29, 41, 49, 50, 51, 55, 60, 61, 62, 63, 64, 65,
                 66, 67, 68, 69, 70, 71, 99, 101, 102, 103, 111, 112, 113, 114, 115, 116, 122, 123,
                 127, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140}
SALIDAS = {11, 52, 197}
SALIDAS_PISAR = {52}  # las que se cruzan caminando; las otras se presionan con USE
# elevadores (bajan, esperan y suben): por interruptor/USE o al pisar una linea
ELEVADORES_USE = {21, 62, 122, 123}
ELEVADORES_PISAR = {10, 88, 120, 121}
TELEPORTES = {39, 97}  # los del jugador; 125 y 126 solo mueven monstruos y se pueden cruzar
# disparadores al pisar (lineas W1/WR de Doom) que mueven sectores con tag: puertas que abren,
# pisos que bajan o suben. MAP03 tiene la puerta de un tramo detras de uno (accion 109).
# Fuera: teletransportes, salidas, elevadores (ya modelados) y los de solo monstruos.
PISAR = {2, 3, 4, 5, 6, 8, 16, 19, 22, 25, 30, 36, 37, 38, 40, 44, 53, 54, 56, 57, 58, 59, 72, 73,
         74, 75, 76, 77, 79, 80, 81, 82, 83, 84, 86, 87, 89, 90, 91, 92, 93, 94, 95, 96, 98, 100, 104,
         105, 106, 107, 108, 109, 110, 119, 128, 129, 130, 141}
# aplastadores: techos que bajan hasta 8 del piso y vuelven a subir. No se pisan a proposito.
# MAP04: el bot pisaba la linea 25 junto al interruptor 5 (estaba en PISAR) y luego se quedaba
# debajo volteando hacia un monstruo: 6 de 11 muertes con barriles+bonus, con salud 82-86
APLASTADORES = {6, 25, 44, 49, 73, 77, 141}
PISAR -= APLASTADORES
APLASTA_ALTO = 64      # hueco bajo el que el techo ya pega (el jugador mide 56)
APLASTA_BAJANDO = 100  # si va bajando, ya no se entra con este hueco o menos
APLASTA_COSTO = 3      # costo extra por celda bajo un aplastador al planear rutas
APLASTA_MARGEN = 64    # unidades extra alrededor del aplastador para frenar a tiempo (inercia corriendo)
PISOS_DANIO = {4, 5, 7, 11, 16}  # tipos de sector con piso que quita salud
DANIO_COSTO = 4        # costo extra por celda de piso con dano al planear rutas
POZO_ORILLA = 256      # a esta distancia de un pozo con dano se camina en vez de correr
POZO_COSTO = 10        # costo extra por celda a 2 o menos de un pozo
COSAS_SOLIDAS = {"ExplosiveBarrel"}  # objetos que no se mueven y tapan el paso
COSA_HOLGURA = 26      # radio del barril (10) + el del jugador (16)
COSA_TOPE = 48         # atorado con una de esas cosas a esta distancia: pasa a ser obstaculo
DESTINO_TELEPORT = 14  # tipo de cosa que marca a donde llega un teletransporte

# abastecimiento: nombres de objetos de ViZDoom por necesidad
ARMAS = {"Shotgun", "SuperShotgun", "Chaingun", "RocketLauncher", "PlasmaRifle", "BFG9000"}
# casillero de cada arma (la doble comparte el 3 con la escopeta, pero es mejora: no se mapea)
CASILLERO = {"Shotgun": 3, "Chaingun": 4, "RocketLauncher": 5, "PlasmaRifle": 6, "BFG9000": 7}
SALUD = {"Stimpack", "Medikit", "Soulsphere", "Megasphere"}
# MAP04: ~30 HealthBonus y ~40 ArmorBonus en filas junto a la emboscada de la llave roja, y el bot
# llegaba con salud 8-20 sin armadura porque solo contaba botiquines
ARMADURA = {"GreenArmor", "BlueArmor"}
BONUS = {"HealthBonus", "ArmorBonus"}
BONUS_DIST = 400  # unidades de camino: los bonus solo valen un desvio corto
# y solo con la salud ya gastada: tomarlos siempre hizo MAP01 un 60% mas lento (749-1440 frames
# contra 479-884) y MAP02 de 3323 a 3953-4689
BONUS_SALUD = 75
SALUD_ANTES_LLAVE = 70  # bajo esto, curarse antes de ir por una llave o la salida
CUBIERTA_MAX = 20       # costo de ruta (celdas) hasta donde se busca donde cubrirse
CUBIERTA_PASOS = 40     # pasos que se sostiene la ruta a la cubierta antes de replantear
CORRER_CELDAS = 10      # tramo de ruta (celdas) que debe ir casi recto para correr
CORRER_FRENO = 160      # a menos de esto de un interruptor, salida o linea de pisar, caminar
BONUS_ACTIVO = False  # experimento apagado por defecto, igual que los barriles de doom_bridge
MUNICION = {"Clip", "ClipBox", "Shell", "ShellBox", "RocketAmmo", "RocketBox", "Cell", "CellPack", "Backpack"}
# municion que sirve para el arma en mano (casillero). La mochila sirve para todas.
# MAP03: con 5 cartuchos iba por un cargador de balas que no podia recoger (balas al maximo)
MUNICION_DE = {1: set(), 2: {"Clip", "ClipBox"}, 4: {"Clip", "ClipBox"}, 3: {"Shell", "ShellBox"},
               5: {"RocketAmmo", "RocketBox"}, 6: {"Cell", "CellPack"}, 7: {"Cell", "CellPack"}}
DESVIO_MAX = 90  # celdas de ruta (~1400 unidades) que vale la pena desviarse por provisiones


class Mapa:
    def __init__(self, wad_path, nombre):
        m = MapEditor(omg.WAD(wad_path).maps[nombre])
        self.nombre = nombre
        v = m.vertexes
        xs = [p.x for p in v]
        ys = [p.y for p in v]
        self.x0, self.y0 = min(xs) - 64, min(ys) - 64
        self.W = int((max(xs) - self.x0 + 64) // CEL) + 1
        self.H = int((max(ys) - self.y0 + 64) // CEL) + 1
        self.piso = np.array([s.z_floor for s in m.sectors], dtype=np.float32)
        self.techo = np.array([s.z_ceil for s in m.sectors], dtype=np.float32)
        self.sector_pozo = set()  # se calcula al final; transitable ya lo consulta antes
        self.celdas_cosas = set()  # celdas tapadas por cosas solidas en vivo (barriles)
        self.cosas_tope = set()    # ids de las cosas solidas contra las que se atoro

        lineas = []
        for ld in m.linedefs:
            a, b = v[ld.vx_a], v[ld.vx_b]
            fr = m.sidedefs[ld.front].sector if ld.front != 0xFFFF else -1
            bk = m.sidedefs[ld.back].sector if ld.back not in (0xFFFF, -1) else -1
            lineas.append((a.x, a.y, b.x, b.y, fr, bk, ld.action, ld.tag, ld.flags))
        self.lineas = lineas

        # sector de cada celda: paridad de cruces de un rayo horizontal (numpy, una pasada por linea)
        cx = self.x0 + (np.arange(self.W) + 0.5) * CEL
        cy = self.y0 + (np.arange(self.H) + 0.5) * CEL
        X, Y = np.meshgrid(cx, cy)  # (H, W)
        paridad = np.zeros((len(m.sectors), self.H, self.W), dtype=bool)
        for (x1, y1, x2, y2, fr, bk, *_r) in lineas:
            if fr == bk:
                continue
            if y1 == y2:
                continue
            cond = (Y >= min(y1, y2)) & (Y < max(y1, y2))
            xi = x1 + (Y - y1) * (x2 - x1) / (y2 - y1)
            cruza = cond & (X < xi)
            for s in (fr, bk):
                if s >= 0:
                    paridad[s] ^= cruza
        self.sector = np.full((self.H, self.W), -1, dtype=np.int32)
        for s in range(len(m.sectors)):
            self.sector[paridad[s]] = s

        # paredes macizas: lineas de un solo lado o marcadas como bloqueantes, con holgura
        def hacer_disco(radio):
            r = int(math.ceil(radio / CEL))
            return [(dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                    if (dx * CEL) ** 2 + (dy * CEL) ** 2 <= (radio + CEL / 2) ** 2]
        disco, disco_fino = hacer_disco(RADIO), hacer_disco(RADIO_FINO)
        self.pared_gruesa = np.zeros((self.H, self.W), dtype=bool)
        self.pared_fina = np.zeros((self.H, self.W), dtype=bool)
        self.pared = self.pared_gruesa
        self.fino = False
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            # los teletransportes cuentan como pared: pisarlos te manda a otro lado y rompe la ruta
            if bk >= 0 and not (flags & 1) and act not in TELEPORTES:
                continue
            self._marcar_pared(x1, y1, x2, y2, disco)
            self._marcar_pared(x1, y1, x2, y2, disco_fino, self.pared_fina)

        # muros que tapan la vista (lineas de un solo lado, sin holgura): para buscar donde cubrirse
        self.muro = np.zeros((self.H, self.W), dtype=bool)
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if bk < 0:
                self._marcar_pared(x1, y1, x2, y2, [(0, 0)], self.muro)

        # puertas que se abren con USE: el sector de atras de la linea
        self.sector_puerta = set()
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if act in PUERTAS_USE and bk >= 0:
                self.sector_puerta.add(bk)
        # sectores que necesitan llave: el de atras (puerta directa) o los del tag (interruptor)
        self.sector_llave = {}
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if act in LLAVE_DE_ACCION:
                color = LLAVE_DE_ACCION[act]
                # con tag es un interruptor de llave (99, 133-137): su puerta no se abre con USE
                # sobre ella sino con el interruptor; la maneja sector_remoto, no esta tabla.
                # (MAP02: la puerta roja 122 se abre con el interruptor rojo en (720,504).)
                if not tag and bk >= 0:
                    self.sector_llave[bk] = color
        # barrotes: postes de puerta de 16 con huecos de 16 entre ellos, donde el jugador (32) no
        # cabe. La celda del hueco entre dos celdas de la misma puerta es parte de la puerta; si no,
        # la ruta pasa por el hueco, nunca pisa la puerta y nadie presiona USE (MAP02: los barrotes
        # amarillos 128 frente a la salida, miles de frames empujando el hueco)
        puertas = self.sector_puerta | set(self.sector_llave)
        sec = self.sector.copy()
        for j in range(1, self.H - 1):
            for i in range(1, self.W - 1):
                s = sec[j, i]
                if s < 0 or s in puertas:
                    continue
                for a, b in ((sec[j, i - 1], sec[j, i + 1]), (sec[j - 1, i], sec[j + 1, i])):
                    # tambien el hueco entre el ultimo poste y la pared
                    if a in puertas and b in (a, -1) or b in puertas and a == -1:
                        d = a if a in puertas else b
                        if self.piso[d] == self.piso[s]:
                            self.sector[j, i] = d
                            break
        # elevadores: sectores con el tag de una linea de elevador. Las lineas de USE sin tag
        # (estilo "presiona el costado del elevador") apuntan a su propio sector de atras.
        self.sector_elevador = set()
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if act in ELEVADORES_USE or act in ELEVADORES_PISAR:
                if tag:
                    self.sector_elevador |= {s for s, sec in enumerate(m.sectors) if sec.tag == tag}
                elif bk >= 0:
                    self.sector_elevador.add(bk)
        # los que se llaman con USE sobre su propio costado (con o sin tag); los demas solo con un
        # interruptor aparte. Tratar los de costado como "interruptor aparte" en MAP02 los hacia
        # esperar cada vez que el elevador se movia: semillas 7-12 de 2774 a 3826 frames
        self.lado_elevador = {bk for (*_c, fr, bk, act, tag, _f) in lineas
                              if act in ELEVADORES_USE and bk in self.sector_elevador}
        # un elevador baja al piso mas bajo de sus vecinos y regresa a su altura original
        self.piso_alto = {s: float(self.piso[s]) for s in self.sector_elevador}
        self.piso_bajo = {s: float(self.piso[s]) for s in self.sector_elevador}
        for (*_c, fr, bk, act, tag, _f) in lineas:
            for a, b in ((fr, bk), (bk, fr)):
                if a in self.piso_bajo and b >= 0:
                    self.piso_bajo[a] = min(self.piso_bajo[a], float(self.piso[b]))
        # aplastadores: sus sectores y las celdas a menos de RADIO de ellos (el techo pega a todo lo
        # que toque el sector, y el jugador mide 16 de radio: MAP04 murio en x=749, 13 fuera del borde)
        tags_apl = {tag for (*_c, act, tag, _f) in lineas if act in APLASTADORES and tag}
        self.sector_aplastador = {s for s, sec in enumerate(m.sectors) if sec.tag in tags_apl}
        self.baja = set()  # aplastadores cuyo techo va bajando ahora
        self.zona_aplastador = np.full((self.H, self.W), -1, dtype=np.int32)
        for s in self.sector_aplastador:
            for j, i in zip(*np.nonzero(self.sector == s)):
                for dx, dy in disco:
                    if 0 <= j + dy < self.H and 0 <= i + dx < self.W:
                        self.zona_aplastador[j + dy, i + dx] = s
        # zona con margen, para decidir si esperar: corriendo, la inercia mete al bot ~50 unidades mas
        # alla de donde frena (MAP04: iba por municion a 24 del 22 y quedo dentro con el techo bajando)
        disco_margen = hacer_disco(RADIO + APLASTA_MARGEN)
        self.zona_margen = np.full((self.H, self.W), -1, dtype=np.int32)
        for s in self.sector_aplastador:
            for j, i in zip(*np.nonzero(self.sector == s)):
                for dx, dy in disco_margen:
                    if 0 <= j + dy < self.H and 0 <= i + dx < self.W:
                        self.zona_margen[j + dy, i + dx] = s
        # llaves tiradas en el mapa (se omiten las que solo salen en multijugador)
        self.llaves_mapa = [(LLAVES[t.type][0], LLAVES[t.type][1], t.x, t.y)
                            for t in m.things if t.type in LLAVES and not (t.flags & 16)]
        self.llaves = set()  # colores que ya trae el jugador

        # sectores delgados sin hueco para pasar (rejas, ventanas): la cuadricula de 16 no los ve,
        # asi que sus orillas se dibujan como pared. Solo los que no se mueven (sin tag, ni puerta
        # ni elevador): una puerta cerrada tambien tiene hueco 0 y si se puede pasar.
        moviles = self.sector_puerta | set(self.sector_llave) | self.sector_elevador | \
            {s for s, sec in enumerate(m.sectors) if sec.tag}
        solidos = {s for s in range(len(m.sectors))
                   if self.techo[s] - self.piso[s] < ALTO_MIN and s not in moviles}
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if bk >= 0 and (fr in solidos or bk in solidos):
                self._marcar_pared(x1, y1, x2, y2, disco)
                self._marcar_pared(x1, y1, x2, y2, disco_fino, self.pared_fina)
        # lo mismo para los delgados que si se mueven (pilares que baja un interruptor), pero como
        # pared condicional: solo mientras sigan cerrados en vivo. Las puertas de USE no, porque
        # hay que llegar hasta ellas. (MAP04: la llave roja esta en una jaula de pilares con huecos
        # de 18 unidades; la cuadricula los veia pasables y empujaba ahi 4000 frames.)
        self.pared_movil = np.full((self.H, self.W), -1, dtype=np.int32)
        # disco chico: basta para tapar huecos menores al jugador sin comerse el pasillo de 60
        # unidades que rodea la jaula (con el disco normal quedaba cortado en las esquinas)
        disco_chico = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
        cerrados = {s for s in moviles - self.sector_puerta - set(self.sector_llave) - self.sector_elevador
                    if self.techo[s] - self.piso[s] < ALTO_MIN}
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            s = fr if fr in cerrados else bk if bk in cerrados else None
            if bk >= 0 and s is not None:
                largo = math.hypot(x2 - x1, y2 - y1)
                for k in range(int(largo // 6) + 1):
                    t = k * 6 / largo if largo else 0
                    i, j = self.celda(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
                    for dx, dy in disco_chico:
                        if 0 <= j + dy < self.H and 0 <= i + dx < self.W:
                            self.pared_movil[j + dy, i + dx] = s

        # interruptores y salidas: punto de llegada del lado de enfrente, a 32 unidades de la linea
        self.metas_uso = []   # (x, y, mira_x, mira_y, accion, es_salida)
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if act in INTERRUPTORES or act in SALIDAS:
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                # normal hacia el lado de enfrente (derecha de a->b en Doom)
                nx, ny = (y2 - y1), -(x2 - x1)
                n = math.hypot(nx, ny) or 1
                px, py = mx + nx / n * 32, my + ny / n * 32
                self.metas_uso.append((px, py, mx, my, act, act in SALIDAS, tag))
        # interruptores que mueven cada elevador (por su tag)
        tag_de = {s: sec.tag for s, sec in enumerate(m.sectors)}
        self.disparo_elevador = {}
        for idx, t in enumerate(self.metas_uso):
            if t[4] in ELEVADORES_USE and t[6]:
                for s in self.sector_elevador:
                    if tag_de[s] == t[6]:
                        self.disparo_elevador.setdefault(s, []).append(idx)
        # los que se pueden bajar desde arriba: con un interruptor encima o al nivel de arriba.
        # MAP04: el 73 solo lo bajan el 8 y el 10, los dos abajo; planear "bajarlo" desde arriba
        # mandaba al bot a un interruptor al que solo se llega bajando el otro elevador
        self.baja_desde_arriba = set()
        for s, idxs in self.disparo_elevador.items():
            for idx in idxs:
                i, j = self.celda(*self.metas_uso[idx][:2])
                st = self.sector[j, i] if 0 <= i < self.W and 0 <= j < self.H else -1
                if st == s or (st >= 0 and self.piso[st] >= self.piso_alto[s] - PASO_MAX):
                    self.baja_desde_arriba.add(s)
        # o con una linea de pisar en su borde desde arriba: baja solo al subirse. MAP03: el 282
        # baja al sector 15 de la salida al cruzar su orilla desde el 30; el bot nunca planeaba
        # bajar ahi y daba vueltas 6000 frames con las tres llaves
        for (*_c, fr, bk, act, tag, _f) in lineas:
            if act in ELEVADORES_PISAR:
                for s in self.sector_elevador & {fr, bk}:
                    otro = bk if fr == s else fr
                    if otro >= 0 and self.piso[otro] >= self.piso_alto[s] - PASO_MAX:
                        self.baja_desde_arriba.add(s)
        # que mueve cada tag: centro de los sectores con ese tag (para explicarle el mapa a Haiku)
        self.tags = {}
        for s, sec in enumerate(m.sectors):
            if sec.tag:
                js, is_ = np.nonzero(self.sector == s)
                if len(is_):
                    cx, cy = self.centro(int(is_.mean()), int(js.mean()))
                    self.tags.setdefault(sec.tag, []).append((s, round(cx), round(cy)))
        self.presionados = set()
        # puertas remotas: sectores con tag que un interruptor mueve (abrir puerta, bajar piso).
        # Se planea a traves de ellos solo cuando de verdad estan abiertos (altura en vivo).
        self.sector_remoto = {}  # sector -> indices de metas_uso que lo mueven
        for idx, t in enumerate(self.metas_uso):
            if t[6] and not t[5]:
                for s, sec in enumerate(m.sectors):
                    if sec.tag == t[6] and s not in self.sector_elevador:
                        self.sector_remoto.setdefault(s, []).append(idx)
        # disparadores al pisar: (x1, y1, x2, y2, accion, tag); sus sectores cuentan como remotos
        self.disparadores = [(x1, y1, x2, y2, act, tag) for (x1, y1, x2, y2, fr, bk, act, tag, flags)
                             in lineas if act in PISAR and tag]
        for k, (_x1, _y1, _x2, _y2, _act, tag) in enumerate(self.disparadores):
            for s, sec in enumerate(m.sectors):
                if sec.tag == tag and s not in self.sector_elevador:
                    self.sector_remoto.setdefault(s, []).append(("pisar", k))
        self.pisados = set()

        # teletransportes como atajos: celdas de entrada frente a la linea -> celda del destino.
        # La linea es pared (cruzarla sin querer rompe la ruta); el A* la "salta" a proposito.
        self.saltos = {}  # celda de entrada -> (celda destino, punto para cruzar la linea)
        destinos = {}
        for t in m.things:
            if t.type == DESTINO_TELEPORT:
                i, j = self.celda(t.x, t.y)
                s = self.sector[j, i] if 0 <= j < self.H and 0 <= i < self.W else -1
                if s >= 0 and m.sectors[s].tag:
                    destinos.setdefault(m.sectors[s].tag, (t.x, t.y))
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if act not in TELEPORTES or tag not in destinos:
                continue
            dest = self.celda_libre_cerca(*destinos[tag], radio=4)
            if not dest:
                continue
            nx, ny = (y2 - y1), -(x2 - x1)  # se activa al cruzar desde el lado de enfrente
            n = math.hypot(nx, ny) or 1
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            cruce = (mx - nx / n * 12, my - ny / n * 12)  # un poco pasando la linea
            for k in range(5):
                t = (k + 0.5) / 5
                px = x1 + (x2 - x1) * t + nx / n * 40
                py = y1 + (y2 - y1) * t + ny / n * 40
                c = self.celda(px, py)
                if self.transitable(*c):
                    self.saltos[c] = (dest, cruce)

        # pisos que hacen dano (acido, lava): cuestan al planear. Los que no tienen salida son pozos
        # y no se pisan: MAP03, el acido 242 esta 32 abajo de su orilla y su unico otro vecino es
        # una isla; explorando la frontera el bot caia ahi y moria con salud 92-100 (8 de 12 muertes).
        # Pozo = sector con dano desde el que no se puede volver al inicio subiendo escalones de 24
        # o menos (los sectores que se mueven y los teletransportes cuentan como paso).
        self.sector_danio = {s for s, sec in enumerate(m.sectors) if sec.type in PISOS_DANIO}
        self.sector_pozo = set()
        inicio = next((t for t in m.things if t.type == 1), None)
        if self.sector_danio and inicio is not None:
            i, j = self.celda(inicio.x, inicio.y)
            s0 = self.sector[j, i] if 0 <= j < self.H and 0 <= i < self.W else -1
            moviles_todos = moviles | self.sector_remoto.keys()
            llega = {}  # sector -> sectores desde los que se llega a el (grafo al reves)
            for (_x1, _y1, _x2, _y2, fr, bk, act, tag, _f) in lineas:
                if fr < 0 or bk < 0:
                    continue
                hueco = min(self.techo[fr], self.techo[bk]) - max(self.piso[fr], self.piso[bk])
                for a, b in ((fr, bk), (bk, fr)):
                    movil = a in moviles_todos or b in moviles_todos
                    if movil or (hueco >= ALTO_MIN and self.piso[b] - self.piso[a] <= PASO_MAX):
                        llega.setdefault(b, set()).add(a)
            for (_x1, _y1, _x2, _y2, fr, bk, act, tag, _f) in lineas:
                if act in TELEPORTES and tag in destinos and fr >= 0:
                    di, dj = self.celda(*destinos[tag])
                    llega.setdefault(int(self.sector[dj, di]), set()).add(fr)
            vuelve, pila = {s0}, [s0]
            while pila:
                for a in llega.get(pila.pop(), ()):
                    if a not in vuelve:
                        vuelve.add(a)
                        pila.append(a)
            if s0 >= 0:
                self.sector_pozo = {s for s in self.sector_danio - vuelve if s not in moviles_todos}
        self.celda_danio = np.isin(self.sector, list(self.sector_danio)) if self.sector_danio else \
            np.zeros((self.H, self.W), dtype=bool)
        # orilla de los pozos: ahi se camina. MAP03: al acido 242 lo rodea una cornisa de 32 unidades
        # (el ancho del jugador) que lleva al interruptor 16; corriendo, la inercia lo tiraba al pozo
        # La ruta ademas rodea el borde (2 celdas) si hay por donde: alli el cuarto 204 de al lado esta
        # al mismo nivel y la cornisa solo era el camino mas corto.
        self.zona_pozo = np.zeros((self.H, self.W), dtype=bool)
        self.borde_pozo = np.zeros((self.H, self.W), dtype=bool)
        r = POZO_ORILLA // CEL
        for s in self.sector_pozo:
            for j, i in zip(*np.nonzero(self.sector == s)):
                self.zona_pozo[max(0, j - r):j + r + 1, max(0, i - r):i + r + 1] = True
                self.borde_pozo[max(0, j - 2):j + 3, max(0, i - 2):i + 3] = True

    def _marcar_pared(self, x1, y1, x2, y2, disco, capa=None):
        capa = self.pared_gruesa if capa is None else capa
        largo = math.hypot(x2 - x1, y2 - y1)
        for k in range(int(largo // 6) + 1):
            t = k * 6 / largo if largo else 0
            i, j = self.celda(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            for dx, dy in disco:
                if 0 <= j + dy < self.H and 0 <= i + dx < self.W:
                    capa[j + dy, i + dx] = True

    def usar_holgura_fina(self):
        """Ultimo recurso: pasillos estrechos que la holgura normal cierra. No tiene vuelta atras."""
        if self.fino:
            return False
        self.fino = True
        self.pared = self.pared_fina
        return True

    def celda(self, x, y):
        return int((x - self.x0) // CEL), int((y - self.y0) // CEL)

    def se_ve(self, x1, y1, x2, y2):
        """Linea de vista entre dos puntos: ningun muro en medio (aproximado, cada 8 unidades)."""
        n = int(math.hypot(x2 - x1, y2 - y1) // 8) + 1
        for k in range(1, n):
            t = k / n
            i, j = self.celda(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            if 0 <= i < self.W and 0 <= j < self.H and self.muro[j, i]:
                return False
        return True

    def recta_ok(self, x1, y1, x2, y2):
        """Se puede caminar en linea recta: ningun muro ni escalon alto en medio.
        se_ve solo mira muros; un pilar de 48 no es muro (MAP01: el del interruptor de salida).
        No exige transitable: la holgura junto a la pared no estorba al cortar una esquina, y
        exigirla apuntaba recto y se pasaba de largo frente a un pasillo de una celda (MAP03 s27)."""
        n = int(math.hypot(x2 - x1, y2 - y1) // 8) + 1
        prev = self.celda(x1, y1)
        for k in range(1, n + 1):
            t = k / n
            c = self.celda(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            if c != prev:
                if not (0 <= c[0] < self.W and 0 <= c[1] < self.H) or self.muro[c[1], c[0]] \
                        or not self.paso_ok(prev, c):
                    return False
                prev = c
        return True

    def centro(self, i, j):
        return self.x0 + (i + 0.5) * CEL, self.y0 + (j + 0.5) * CEL

    def actualizar_alturas(self, sectores):
        for s in sectores:
            if 0 <= s.id < len(self.piso):
                if s.id in self.sector_aplastador:
                    if s.ceiling_height < self.techo[s.id] - 0.1:
                        self.baja.add(s.id)
                    elif s.ceiling_height > self.techo[s.id] + 0.1:
                        self.baja.discard(s.id)
                self.piso[s.id] = s.floor_height
                self.techo[s.id] = s.ceiling_height

    def aplasta(self, i, j, margen=False):
        """La celda esta bajo (o junto a) un aplastador que pega o que ya viene bajando. Con margen,
        tambien a unas APLASTA_MARGEN unidades mas (para frenar a tiempo corriendo)."""
        if not (0 <= i < self.W and 0 <= j < self.H):
            return False
        s = (self.zona_margen if margen else self.zona_aplastador)[j, i]
        if s < 0:
            return False
        hueco = self.techo[s] - self.piso[s]
        if margen and self.zona_aplastador[j, i] < 0:
            # en el margen solo importa un techo que viene bajando: uno abajo y quieto no alcanza a
            # quien pasa por fuera (MAP04: el 82 cerrado dejaba al bot esperando para siempre)
            return s in self.baja and hueco <= APLASTA_BAJANDO
        return hueco < APLASTA_ALTO or (s in self.baja and hueco <= APLASTA_BAJANDO)

    def puerta_cerrada(self, s):
        return (s in self.sector_puerta or s in self.sector_llave) and self.techo[s] - self.piso[s] < ALTO_MIN

    def transitable(self, i, j):
        if not (0 <= i < self.W and 0 <= j < self.H) or self.pared[j, i] or (i, j) in self.celdas_cosas:
            return False
        pm = self.pared_movil[j, i]
        if pm >= 0 and self.techo[pm] - self.piso[pm] < ALTO_MIN:
            return False
        s = self.sector[j, i]
        if s < 0 or s in self.sector_pozo:
            return False
        if self.techo[s] - self.piso[s] >= ALTO_MIN:
            return True
        # cerrada: se puede pasar si se abre con USE y, si pide llave, ya se trae
        if s in self.sector_llave and self.sector_llave[s] not in self.llaves:
            return False
        # una puerta remota cerrada no se cruza aunque su interruptor "se haya usado": si el USE no
        # le pego, seguiria cerrada (MAP02: empujaba la puerta azul 124 el resto de la partida).
        # Cuando abre de verdad, la altura en vivo la deja pasar arriba de esta funcion.
        if s in self.sector_remoto:
            return False
        return s in self.sector_puerta or s in self.sector_llave

    def orilla_pozo(self, x, y):
        i, j = self.celda(x, y)
        return 0 <= i < self.W and 0 <= j < self.H and bool(self.zona_pozo[j, i])

    def actualizar_cosas(self, objetos):
        """Tapa las celdas de las cosas solidas contra las que ya se atoro (cosas_tope) y que siguen
        en el mundo. Devuelve True si cambiaron. MAP04 s12: un barril junto al interruptor 5, arriba
        del elevador 69; la ruta pasaba por encima y el bot lo empujo 10000 frames. Taparlos todos
        desde el principio cambiaba rutas y retiradas en los cuartos llenos de barriles (MAP04 de
        23/24 a 11/24, 54 muertes en la sala de los Demons): solo los que ya estorbaron."""
        celdas = set()
        for o in objetos:
            if o.name not in COSAS_SOLIDAS or o.id not in self.cosas_tope:
                continue
            ci, cj = self.celda(o.position_x, o.position_y)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    cx, cy = self.centro(ci + dx, cj + dy)
                    if math.hypot(cx - o.position_x, cy - o.position_y) <= COSA_HOLGURA:
                        celdas.add((ci + dx, cj + dy))
        if celdas == self.celdas_cosas:
            return False
        self.celdas_cosas = celdas
        return True

    def actualizar_llaves(self, objetos):
        """Una llave que ya no esta en el mundo es una llave que el jugador recogio."""
        en_mundo = {o.name for o in objetos}
        nuevas = set()
        for color, nombre, _x, _y in self.llaves_mapa:
            if nombre not in en_mundo and color not in self.llaves:
                nuevas.add(color)
        self.llaves |= nuevas
        return nuevas

    def paso_ok(self, a, b):
        sa, sb = self.sector[a[1], a[0]], self.sector[b[1], b[0]]
        # el hueco ENTRE los dos sectores, no el de cada uno: MAP04, el cuarto-elevador 69 arriba
        # (piso -32) junto al pasillo 103 (techo -32) deja 0 unidades, y se estrellaba ahi.
        # Puertas y sectores remotos se mueven: los maneja transitable. Un elevador solo cuenta como
        # paso si hay que SUBIR (llamarlo o esperar encima); bajar de el con hueco 0 no se puede
        # hasta que baje de verdad, y entonces la altura en vivo abre el paso.
        if sa != sb and min(self.techo[sa], self.techo[sb]) - max(self.piso[sa], self.piso[sb]) < ALTO_MIN:
            puerta = ({sa, sb} & self.sector_puerta or sa in self.sector_llave or sb in self.sector_llave
                      or sa in self.sector_remoto or sb in self.sector_remoto)
            sube_en_elevador = self.piso[sb] > self.piso[sa] and {sa, sb} & self.sector_elevador
            # bajar de un elevador que esta arriba: se puede si un interruptor lo baja y abajo abre
            # el hueco (MAP04: del 69 al 103 hay 0 unidades hasta que el interruptor 5 lo baja)
            baja_en_elevador = (self.piso[sb] < self.piso[sa] and sa in self.baja_desde_arriba
                                and min(self.techo[sa], self.techo[sb])
                                - max(self.piso_bajo[sa], self.piso[sb]) >= ALTO_MIN)
            if not (puerta or sube_en_elevador or baja_en_elevador):
                return False
        if self.piso[sb] - self.piso[sa] <= PASO_MAX:
            return True
        # un elevador baja hasta el piso de al lado: se puede subir a el, y desde el (arriba) salir
        return sb in self.sector_elevador or sa in self.sector_elevador

    def bloqueo_elevador(self, a, b):
        """Si el paso a->b necesita un elevador que ahora no esta a la altura, devuelve su sector."""
        sa, sb = self.sector[a[1], a[0]], self.sector[b[1], b[0]]
        if sa in self.sector_elevador and self.piso[sb] < self.piso[sa] and \
                min(self.techo[sa], self.techo[sb]) - max(self.piso[sa], self.piso[sb]) < ALTO_MIN:
            return ("bajar", sa)    # vamos encima y abajo no hay hueco: hacer que baje
        if self.piso[sb] - self.piso[sa] <= PASO_MAX:
            return None
        if sb in self.sector_elevador:
            return ("llamar", sb)   # el elevador esta arriba: activarlo para que baje
        if sa in self.sector_elevador:
            return ("esperar", sa)  # vamos encima: esperar a que suba
        return None

    def vecinos(self, c):
        i, j = c
        for dx, dy, costo in ((1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1),
                              (1, 1, 1.41), (1, -1, 1.41), (-1, 1, 1.41), (-1, -1, 1.41)):
            n = (i + dx, j + dy)
            if self.transitable(*n) and self.paso_ok(c, n):
                if dx and dy and not (self.transitable(i + dx, j) and self.transitable(i, j + dy)):
                    continue
                # bajo un aplastador se puede pasar (en MAP04 el 22 es el pasillo al interruptor 5),
                # pero cuesta: se rodea si hay por donde. Esperar y huir lo hacen en decidir
                yield n, costo + (APLASTA_COSTO if self.zona_aplastador[n[1], n[0]] >= 0 else 0) \
                    + (DANIO_COSTO if self.celda_danio[n[1], n[0]] else 0) \
                    + (POZO_COSTO if self.borde_pozo[n[1], n[0]] else 0)
        if c in self.saltos:
            yield self.saltos[c][0], 3

    def ruta(self, inicio, metas, castigo=None, limite=60000):
        """A* (o Dijkstra si hay varias metas) de la celda inicio a la meta mas cercana."""
        metas = set(metas)
        if not metas:
            return None
        if len(metas) == 1:
            (gi, gj), = metas
            h = lambda c: math.hypot(c[0] - gi, c[1] - gj)
        else:
            h = lambda c: 0
        abiertos = [(h(inicio), 0.0, inicio)]
        previo = {inicio: None}
        costo = {inicio: 0.0}
        n = 0
        while abiertos and n < limite:
            _, g, c = heapq.heappop(abiertos)
            n += 1
            if c in metas:
                camino = []
                while c is not None:
                    camino.append(c)
                    c = previo[c]
                return camino[::-1]
            if g > costo.get(c, 1e18):
                continue
            for nb, k in self.vecinos(c):
                ng = g + k + (castigo.get(nb, 0) if castigo else 0)
                if ng < costo.get(nb, 1e18):
                    costo[nb] = ng
                    previo[nb] = c
                    heapq.heappush(abiertos, (ng + h(nb), ng, nb))
        return None

    def celda_libre_cerca(self, x, y, radio=4):
        i, j = self.celda(x, y)
        mejor = None
        for dx in range(-radio, radio + 1):
            for dy in range(-radio, radio + 1):
                if self.transitable(i + dx, j + dy):
                    d = dx * dx + dy * dy
                    if mejor is None or d < mejor[0]:
                        mejor = (d, (i + dx, j + dy))
        return mejor[1] if mejor else None


class Navegador:
    """Las piernas del bot: arma la lista de metas posibles con su ruta y camina hacia la elegida.

    Quien elige la meta depende del modo:
    - codigo: prioridad fija (provision urgente, salida, llave, interruptor, frontera);
    - jev: Jev escoge entre las metas (self.pedido_jev); si duda, la prioridad fija;
    - jev_haiku: el plan de Haiku fija el objetivo (self.plan); Jev decide si desviarse por provisiones.
    """

    def __init__(self, mapa):
        self.mapa = mapa
        self.visitado = np.zeros((mapa.H, mapa.W), dtype=bool)
        self.camino = []
        self.meta = None          # candidato elegido (dict)
        self.cands = []           # metas posibles en el ultimo replanteo
        self.replan = 0
        self.castigo = {}
        self.ultimo_avance = (0, None)
        self.uso = 0
        self.uso_tope = 0         # paso hasta el que acomodarse antes de un USE no gasta pulsos
        self.mirar = None
        self.pararse = None       # punto frente al interruptor desde donde se presiona
        self.paso = 0
        self.evento = None        # ultimo evento para la bitacora
        self.salud, self.municion, self.armadura, self.objetos = 100, 50, 0, []
        self.armas, self.arma_actual = set(), None
        self.descartados = {}  # id -> paso hasta el que se ignora (no se pudo llegar)
        self.fallos = {}          # id -> veces que se atoro yendo ahi
        self.plan = []            # ids en orden, de Haiku
        self.pedido_jev = None    # id que pidio Jev con confianza
        self.cambio_meta = 0
        self.espera_elevador = 0
        self.uso_puerta = {}      # sector -> paso del ultimo USE (para no volver a presionarla)
        self.por_verificar = {}   # interruptor -> (paso, alturas de sus sectores al presionarlo)
        self.sin_efecto = {}      # interruptor -> veces que se presiono sin que se moviera nada
        self.forzar = None        # "salud": ir por un botiquin antes que cualquier otra meta
        self.huyendo = False      # saliendo de debajo de un aplastador
        self.espera_apl = -9      # ultimo paso esperando a que un aplastador suba
        self.acosado = False      # monstruos encima (lo fija el cerebro): no frenar por el margen

    def huir_aplastador(self, x, y, sectores, angulo, accion):
        """Debajo de un aplastador que pega o baja: salir a la celda segura mas cercana, sin girar
        (adelante, atras o de lado segun donde quede). Manda sobre todo lo demas, pelea incluida."""
        m = self.mapa
        if sectores is not None:
            m.actualizar_alturas(sectores)
        aqui = m.celda(x, y)
        if not m.aplasta(*aqui):
            self.huyendo = False
            return None
        i0, j0 = aqui
        libres = [(dx * dx + dy * dy, (i0 + dx, j0 + dy)) for dx in range(-8, 9) for dy in range(-8, 9)
                  if m.transitable(i0 + dx, j0 + dy) and not m.aplasta(i0 + dx, j0 + dy)]
        if not libres:
            return None
        libre = min(libres)[1]
        if not self.huyendo:
            self.huyendo = True
            self.evento = ("aplastador", int(m.zona_aplastador[aqui[1], aqui[0]]))
        self.camino, self.uso = [], 0
        dif = self._dif(x, y, angulo, *m.centro(*libre))
        if abs(dif) < 60:
            return accion("MOVE_FORWARD")
        if abs(dif) > 120:
            return accion("MOVE_BACKWARD")
        return accion("MOVE_LEFT" if dif > 0 else "MOVE_RIGHT")

    # ---------- metas posibles ----------

    def marcar_visto(self, x, y):
        i, j = self.mapa.celda(x, y)
        r = 6  # ~96 unidades
        self.visitado[max(0, j - r):j + r + 1, max(0, i - r):i + r + 1] = True

    def _dijkstra(self, inicio, limite=60000):
        m = self.mapa
        dist = {inicio: 0.0}
        prev = {inicio: None}
        abiertos = [(0.0, inicio)]
        n = 0
        while abiertos and n < limite:
            g, c = heapq.heappop(abiertos)
            n += 1
            if g > dist.get(c, 1e18):
                continue
            for nb, k in m.vecinos(c):
                ng = g + k + self.castigo.get(nb, 0)
                if ng < dist.get(nb, 1e18):
                    dist[nb] = ng
                    prev[nb] = c
                    heapq.heappush(abiertos, (ng, nb))
        return dist, prev

    @staticmethod
    def _camino(prev, fin):
        out = []
        while fin is not None:
            out.append(fin)
            fin = prev[fin]
        return out[::-1]

    def candidatos(self, inicio):
        """Todas las metas a las que hoy hay ruta, con su descripcion en texto."""
        m = self.mapa
        dist, prev = self._dijkstra(inicio)
        cands = []

        def agregar(id_, tipo, desc, celda, datos=None):
            if self.descartados.get(id_, 0) > self.paso or not celda or celda not in dist:
                return
            cands.append({"id": id_, "tipo": tipo, "desc": desc, "celda": celda, "datos": datos,
                          "dist": round(dist[celda] * CEL)})

        for t in m.metas_uso:
            if t[5]:
                if t[4] in SALIDAS_PISAR:
                    # la de pisar se cuenta del otro lado de la linea: en MAP03 adentro hay un bloque
                    # 128 unidades mas alto que baja el interruptor 16, y contada desde afuera la
                    # salida tapaba a ese interruptor (la salida va primero)
                    celda = m.celda_libre_cerca(t[2] - (t[0] - t[2]) * 0.75, t[3] - (t[1] - t[3]) * 0.75, 2)
                else:
                    celda = m.celda_libre_cerca(t[0], t[1])
                agregar("salida", "salida", "la salida del nivel", celda, t)
        for color, _n, x, y in m.llaves_mapa:
            if color not in m.llaves:
                # radio 2 (~32 unidades, lo que alcanza para recogerla): con 4 una celda afuera de
                # la jaula de MAP04 contaba como "llegar a la llave"
                agregar(f"llave_{color}", "llave", f"la llave {color}", m.celda_libre_cerca(x, y, 2))
        for i, t in enumerate(m.metas_uso):
            if not t[5] and i not in m.presionados:
                if LLAVE_DE_ACCION.get(t[4]) and LLAVE_DE_ACCION[t[4]] not in m.llaves:
                    continue  # interruptor de llave sin la llave: no hace nada
                agregar(f"interruptor_{i}", "interruptor", self._desc_interruptor(i, t),
                        m.celda_libre_cerca(t[0], t[1]), t)
        # disparadores al pisar que aun no se activan (cerrar puertas, accion 3, no sirve de nada)
        for k, (x1, y1, x2, y2, act, tag) in enumerate(m.disparadores):
            if k in m.pisados or act == 3:
                continue
            # el punto medio puede caer dentro de la puerta que abre (cerrada = pared): se prueba
            # tambien a 24 unidades de cada lado de la linea y se usa el que tenga ruta
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            nx, ny = (y2 - y1), -(x2 - x1)
            n = math.hypot(nx, ny) or 1
            opciones = [m.celda_libre_cerca(mx, my, 2),
                        m.celda_libre_cerca(mx + nx / n * 24, my + ny / n * 24, 2),
                        m.celda_libre_cerca(mx - nx / n * 24, my - ny / n * 24, 2)]
            celda = next((c for c in opciones if c in dist), None)
            agregar(f"pisar_{k}", "pisar", self._desc_disparador(k), celda, k)
        # provisiones: la mas cercana de cada clase
        # municion de cualquier arma que trae (pistola siempre), no solo la de la mano: con la pistola
        # en mano solo buscaba balas y la escopeta se quedaba sin cartuchos (MAP02: 3 muertes)
        utiles = {"Backpack"}
        for casillero in {2} | self.armas:
            utiles |= MUNICION_DE.get(casillero, set())
        clases = (("arma", ARMAS, "un arma nueva"), ("salud", SALUD, "salud"),
                  ("municion", utiles, "municion para el arma en mano"))
        if BONUS_ACTIVO:
            clases += (("armadura", ARMADURA, "armadura"), ("bonus", BONUS, "un bonus de salud o armadura"))
        for clase, nombres, texto in clases:
            mejor = None
            for o in self.objetos:
                if o.name in nombres:
                    if clase == "arma" and CASILLERO.get(o.name) in self.armas:
                        continue  # ya trae un arma de ese casillero: no vale el desvio
                    c = m.celda_libre_cerca(o.position_x, o.position_y, 2)
                    if c in dist and (mejor is None or dist[c] < dist[mejor[1]]):
                        mejor = (o, c)
            if mejor and dist[mejor[1]] <= DESVIO_MAX:
                o, c = mejor
                agregar(f"{clase}_{round(o.position_x)}_{round(o.position_y)}", "provision",
                        f"{texto} ({o.name})", c, clase)
        # frontera: la zona sin visitar mas cercana
        js, is_ = np.nonzero(~self.visitado & (m.sector >= 0) & ~m.pared)
        front = [(int(i), int(j)) for i, j in zip(is_, js) if (int(i), int(j)) in dist]
        if front:
            c = min(front, key=lambda c: dist[c])
            agregar("frontera", "frontera", "explorar la zona nueva mas cercana", c)
        for cnd in cands:
            cnd["camino"] = self._camino(prev, cnd["celda"])
        self.cands = cands
        return cands

    def _desc_interruptor(self, i, t):
        sectores = self.mapa.tags.get(t[6], []) if t[6] else []
        llave = LLAVE_DE_ACCION.get(t[4])
        extra = f", requiere llave {llave}" if llave else ""
        if sectores:
            s, cx, cy = sectores[0]
            return f"el interruptor {i} en ({round(t[2])},{round(t[3])}), mueve el sector cerca de ({cx},{cy}){extra}"
        return f"el interruptor {i} en ({round(t[2])},{round(t[3])}){extra}"

    def _desc_disparador(self, k):
        x1, y1, x2, y2, act, tag = self.mapa.disparadores[k]
        sectores = self.mapa.tags.get(tag, [])
        donde = f", mueve el sector cerca de ({sectores[0][1]},{sectores[0][2]})" if sectores else ""
        return f"la linea {k} que se activa al pisarla en ({round((x1 + x2) / 2)},{round((y1 + y2) / 2)}){donde}"

    def prioridad_fija(self, cands):
        """La regla del modo 'codigo' y el respaldo cuando Jev duda."""
        por_tipo = {}
        for c in cands:
            por_tipo.setdefault(c["tipo"], []).append(c)
        # antes de abrir camino (llave, salida, interruptor, linea de pisar) se llega curado: detras
        # suele estar la sala mas peligrosa. MAP04: pisaba la linea 3, que abre la sala de la llave
        # azul, con 55 de salud y un botiquin a la mano, y ahi murieron 11 de 21 veces. Solo con
        # llave y salida no cambiaba nada: la llave azul no tiene ruta hasta pisar esa linea
        antes_de_llave = (self.salud < SALUD_ANTES_LLAVE
                          and any(por_tipo.get(t) for t in ("llave", "salida", "interruptor", "pisar")))
        prov = [c for c in por_tipo.get("provision", [])
                if c["datos"] == "arma" or (c["datos"] == "armadura" and BONUS_ACTIVO and self.armadura < 100)
                or (c["datos"] == "salud" and (self.salud < 50 or antes_de_llave))
                or (c["datos"] == "bonus" and BONUS_ACTIVO and self.salud < BONUS_SALUD
                    and c["dist"] < BONUS_DIST)
                or (c["datos"] == "municion" and self.municion < 10 and c["dist"] < 800)]
        for grupo in (prov, por_tipo.get("salida", []), por_tipo.get("llave", []),
                      por_tipo.get("interruptor", []), por_tipo.get("pisar", []), por_tipo.get("frontera", [])):
            if grupo:
                return min(grupo, key=lambda c: c["dist"])
        return None

    def metas_jev(self):
        """Las metas que se le ofrecen a Jev. Sin la frontera mientras haya salida, llave, interruptor
        o linea con ruta: con ella en la lista Jev exploraba 446-626 veces por partida y no termino
        MAP02 en 0 de 3 (solo codigo, 3 de 3), aunque la pregunta dice que explorar es el ultimo recurso."""
        avanzar = {"salida", "llave", "interruptor", "pisar"}
        hay = any(c["tipo"] in avanzar for c in self.cands)
        return [(c["id"], f"{c['desc']}, a {c['dist']} unidades") for c in self.cands
                if not (hay and c["tipo"] == "frontera")][:8]

    def hay_salud(self):
        """Hay un botiquin (o similar) con ruta en el ultimo replanteo."""
        return any(c["tipo"] == "provision" and c["datos"] == "salud" for c in self.cands)

    def distancia_salud(self):
        """Distancia por ruta al botiquin mas cercano, o None si no hay."""
        d = [c["dist"] for c in self.cands if c["tipo"] == "provision" and c["datos"] == "salud"]
        return min(d) if d else None

    def elegir(self, cands):
        por_id = {c["id"]: c for c in cands}
        # curarse (lo pide Jev o la regla de supervivencia): el botiquin mas cercano, antes que nada
        if self.forzar == "salud":
            salud = [c for c in cands if c["tipo"] == "provision" and c["datos"] == "salud"]
            if salud:
                return min(salud, key=lambda c: c["dist"]), "curarse"
        # arma nueva, salud o municion que hacen falta: las decide el codigo. Sin esto Jev iba por la
        # llave azul de MAP02 sin la escopeta y sin balas (20 muertes en 3 partidas, 9 con 0 balas)
        fija = self.prioridad_fija(cands)
        if fija and fija["tipo"] == "provision":
            return fija, "codigo"
        # plan de Haiku: el primer paso del plan que hoy tenga ruta
        objetivo = next((por_id[i] for i in self.plan if i in por_id), None)
        if self.pedido_jev in por_id:
            pedido = por_id[self.pedido_jev]
            # con plan, Jev solo puede desviarse por provisiones o explorar si el plan no tiene ruta
            if not self.plan or pedido["tipo"] == "provision" or objetivo is None:
                return pedido, "jev"
        if objetivo:
            return objetivo, "haiku"
        return self.prioridad_fija(cands), "codigo"

    # ---------- caminar ----------

    def decidir(self, x, y, angulo, sectores, accion, objetos=None, salud=100, municion=50, armas=None,
                arma_actual=None, armadura=0):
        """accion(*botones) arma el vector de botones del juego."""
        m = self.mapa
        self.paso += 1
        self.evento = None
        self.salud, self.municion, self.armadura = salud, municion, armadura
        self.armas = armas or set()  # casilleros de arma que ya trae
        self.arma_actual = arma_actual
        self.objetos = objetos or []
        huir = self.huir_aplastador(x, y, sectores, angulo, accion)
        if huir:
            return huir
        if objetos is not None:
            if m.actualizar_cosas(objetos) and any(c in m.celdas_cosas for c in self.camino):
                self.camino = []
            nuevas = m.actualizar_llaves(objetos)
            if nuevas:
                # con llave nueva cambian las rutas posibles: replanear ya
                self.evento = ("llave_recogida", sorted(nuevas))
                self.camino = []
                self.castigo = {}
                self.descartados = {}
        # interruptores presionados hace ~8 s sin que se moviera nada: el USE no le pego
        for idx, (paso, antes) in list(self.por_verificar.items()):
            if any((m.piso[s], m.techo[s]) != alt for s, alt in antes.items()):
                del self.por_verificar[idx]
            elif self.paso - paso > 70:
                del self.por_verificar[idx]
                self.sin_efecto[idx] = self.sin_efecto.get(idx, 0) + 1
                if self.sin_efecto[idx] < 3:
                    m.presionados.discard(idx)  # se reintenta hasta tres veces en total
                    self.evento = ("interruptor_sin_efecto", idx)
                else:
                    # tres veces sin mover nada: se da por inutil (MAP05: el 14 se reintentaba sin fin)
                    self.evento = ("interruptor_inutil", idx)
        self.marcar_visto(x, y)
        aqui = m.celda(x, y)

        # pulsos de USE en curso (abrir puerta, presionar interruptor, llamar elevador)
        if self.uso > 0:
            # reintento de un interruptor: acomodarse no gasta pulsos. Llegaba con impulso, se pasaba
            # ~45 unidades de lado y los pulsos se iban girando. MAP04: el 7 (el de la llave roja)
            # fallo 3 de 3 mirando el canto de una columna, se dio por inutil y el bot se quedo sin
            # metas 2300 frames. Solo en el reintento: hacerlo siempre cambio el orden de los
            # interruptores de MAP02 y abrio antes la sala de los Demons (6/6 -> 2/6)
            if self.paso < self.uso_tope:
                if self.pararse and math.hypot(self.pararse[0] - x, self.pararse[1] - y) > 20:
                    dif = self._dif(x, y, angulo, *self.pararse)
                    giro = max(-45, min(45, dif))
                    return accion("MOVE_FORWARD", giro=giro) if abs(dif) < 30 else accion(giro=giro)
                dif = self._dif(x, y, angulo, *self.mirar)
                if abs(dif) > 6:
                    return accion(giro=max(-45, min(45, dif)))
            self.uso -= 1
            extra = []
            if self.mirar:
                dif = self._dif(x, y, angulo, *self.mirar)
                if abs(dif) > 6:
                    return accion(giro=max(-45, min(45, dif)))
                # USE alcanza 64 unidades pero falla de lado o en huecos: acercarse hasta pegarse
                # (MAP03: el interruptor 12 fallo dos veces desde ~40 y se dio por inutil)
                if math.hypot(self.mirar[0] - x, self.mirar[1] - y) > 24:
                    extra = ["MOVE_FORWARD"]
            return accion("USE", *extra) if self.uso % 2 else accion(*extra)

        # atoron: sin avance en ~2 s (esperar un elevador no cuenta)
        if self.espera_elevador > 0:
            self.ultimo_avance = (self.paso, (x, y))
        if self.ultimo_avance[1] is None or math.hypot(x - self.ultimo_avance[1][0], y - self.ultimo_avance[1][1]) > 24:
            self.ultimo_avance = (self.paso, (x, y))
        elif self.paso - self.ultimo_avance[0] > 18:
            self.evento = ("atorado", aqui, self.meta["id"] if self.meta else None)
            for o in self.objetos:
                if o.name in COSAS_SOLIDAS and math.hypot(o.position_x - x, o.position_y - y) < COSA_TOPE:
                    m.cosas_tope.add(o.id)
            if self.meta:
                mid = self.meta["id"]
                self.fallos[mid] = self.fallos.get(mid, 0) + 1
                # salida y llaves nunca se descartan: solo se castiga la ruta para que busque otra.
                # Lo demas se descarta un rato (~30 s), no para siempre.
                if self.meta["tipo"] not in ("salida", "llave") and \
                        (self.meta["tipo"] == "provision" or self.fallos[mid] >= 3):
                    self.descartados[mid] = self.paso + 270
            castigo = 30 * (1 + self.fallos.get(self.meta["id"], 0) if self.meta else 1)
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    if self.camino:
                        k = min(3, len(self.camino) - 1)
                        c = (self.camino[k][0] + dx, self.camino[k][1] + dy)
                        self.castigo[c] = self.castigo.get(c, 0) + castigo
            self.camino = []
            self.meta = None
            self.ultimo_avance = (self.paso, (x, y))
            self.uso, self.uso_tope = 4, 0
            self.mirar = self.pararse = None
            return accion("MOVE_BACKWARD", "USE")

        # replantear: sin ruta, cada ~8 s, al alejarse de la ruta, o si el controlador pide otra meta
        pide_otra = (self.paso - self.cambio_meta > 18 and self.meta is not None
                     and ((self.pedido_jev and self.pedido_jev != self.meta["id"])
                          or (self.plan and self.plan[0] != self.meta["id"])))
        # curarse no espera: si se pide y la meta no es salud, replantear ya
        # ...salvo que vaya al interruptor de un elevador o a cubrirse, que son el camino para llegar:
        # MAP04 s8 iba y venia entre el botiquin de abajo y el interruptor 5 que baja el elevador 69,
        # cada ~7 frames, durante 10000 frames con 28 de salud
        de_paso = self.meta and self.meta["id"].startswith(("elevador_", "cubierta"))
        if self.forzar == "salud" and self.hay_salud() and not de_paso and \
                not (self.meta and self.meta["tipo"] == "provision" and self.meta["datos"] == "salud"):
            pide_otra = True
        if not self.camino or self.paso >= self.replan or not self._cerca_de_ruta(aqui) or pide_otra:
            inicio = aqui if m.transitable(*aqui) else (m.celda_libre_cerca(x, y, 3) or aqui)
            cands = self.candidatos(inicio)
            elegido, quien = self.elegir(cands) if cands else (None, None)
            # nada que elegir (a lo mas provisiones que no hacen falta), ni zonas sin visitar:
            # probar los pasillos estrechos, una sola vez (MAP04 s2: solo quedaba municion de sobra)
            # la llave recien recogida se reporta antes que el replanteo: en MAP03 "sin_metas" la
            # tapaba y el benchmark contaba la llave roja como no recogida
            llave = self.evento if self.evento and self.evento[0] == "llave_recogida" else None
            if elegido is None and m.usar_holgura_fina():
                self.evento = llave or ("holgura_fina",)
                self.castigo, self.descartados = {}, {}
                inicio = aqui if m.transitable(*aqui) else (m.celda_libre_cerca(x, y, 3) or aqui)
                cands = self.candidatos(inicio)
                elegido, quien = self.elegir(cands) if cands else (None, None)
            # nunca quedarse sin meta (MAP04 s3: 2300 frames quieto girando): reintentar los
            # interruptores dados por inutiles, olvidar descartes y volver a recorrer lo ya visto
            if elegido is None:
                self.evento = llave or ("sin_metas",)
                for idx, veces in self.sin_efecto.items():
                    if veces >= 3:
                        m.presionados.discard(idx)
                self.sin_efecto, self.castigo, self.descartados = {}, {}, {}
                self.visitado[:] = False
                self.marcar_visto(x, y)
                inicio = aqui if m.transitable(*aqui) else (m.celda_libre_cerca(x, y, 3) or aqui)
                cands = self.candidatos(inicio)
                elegido, quien = self.elegir(cands) if cands else (None, None)
            if elegido is None or self.meta is None or elegido["id"] != self.meta["id"]:
                self.cambio_meta = self.paso
                self.evento = self.evento or ("meta", elegido["id"] if elegido else None, quien,
                                              len(elegido["camino"]) if elegido else 0)
            self.meta = elegido
            self.camino = list(elegido["camino"]) if elegido else []
            self.replan = self.paso + 72
            if not self.camino:
                return accion("USE", giro=30) if self.paso % 2 else accion(giro=30)

        # avanzar el indice de la ruta
        # ya cruzo: aparecio junto al destino del teletransporte, la entrada queda atras. La entrada
        # puede no ser la primera celda: cortando la esquina cruza la linea antes de pasar la anterior
        # (MAP02 s2 con bonus: no lo detectaba, replanteaba de vuelta al teletransporte, que lo
        # regresaba al mismo punto; 2400 frames en ese circulo con las tres llaves)
        for k in range(min(4, len(self.camino) - 1)):
            a, b = self.camino[k], self.camino[k + 1]
            if a in m.saltos and m.saltos[a][0] == b and math.hypot(*(np.subtract(m.centro(*b), (x, y)))) < 64:
                del self.camino[:k + 1]
                self.evento = ("teletransportado", self.camino[0])
                break
        while len(self.camino) > 1 and math.hypot(*(np.subtract(m.centro(*self.camino[0]), (x, y)))) < 24:
            # una entrada de teletransporte no se da por pasada hasta cruzar la linea: si se quita,
            # lo siguiente es el destino (lejos) y el bot se da la vuelta (MAP02: 300 frames asi)
            a = self.camino[0]
            if a in m.saltos and m.saltos[a][0] == self.camino[1]:
                break
            self.camino.pop(0)
        # cortando una esquina puede no pasar nunca a menos de 24 de la primera celda: ubicarse en la
        # mas cercana de las siguientes y dar por pasadas las anteriores. MAP04: tras la llave roja
        # iba y venia en el pasillo de y=1400 apuntando a una celda que ya habia dejado atras, a
        # 35-50 unidades, y nunca llegaba al interruptor 5 (1 vez en 48 partidas)
        n = min(8, len(self.camino) - 1)
        if n > 0:
            dist = [math.hypot(*(np.subtract(m.centro(*c), (x, y)))) for c in self.camino[:n + 1]]
            k = min(range(n + 1), key=dist.__getitem__)
            saltos_antes = any(c in m.saltos and m.saltos[c][0] == d
                               for c, d in zip(self.camino[:k], self.camino[1:k + 1]))
            if k > 0 and dist[k] < 48 and not saltos_antes:
                del self.camino[:k]

        # elevador en la ruta: llamarlo si esta arriba, esperar encima mientras sube. Para bajar se
        # revisa tambien desde la celda actual: la primera de la ruta ya puede estar del otro lado
        # del borde (MAP04: empujaba el hueco del 69 al 103). Para llamar y esperar no: en MAP02 la
        # celda redondeada caia sobre el 165 estando al lado y esperaba 80 frames a que subiera.
        # Llamar si: si la celda de antes del elevador ya se recorto de la ruta, el unico paso al 165
        # es desde aqui (MAP02 s24: 9000 frames deslizandose junto al 165 sin presionar USE)
        for k, (a, b) in enumerate(zip([aqui] + self.camino[:5], self.camino[:6])):
            bloqueo = m.bloqueo_elevador(a, b)
            if bloqueo and k == 0 and bloqueo[0] == "esperar":
                continue
            if bloqueo:
                que, s = bloqueo
                bx, by = m.centro(*b)
                # elevador que solo mueve un interruptor aparte (MAP04, el 69 con los interruptores
                # 5 y 1). En movimiento se espera; quieto en su altura, se va a presionar uno.
                # La ruta pudo planearse con el elevador abajo: tras una pelea subio y el bot
                # empujaba un hueco de 0 unidades hasta que se daba por atorado
                if que == "bajar" or (que == "llamar" and s not in m.lado_elevador):
                    if self.meta and self.meta["id"].startswith("elevador_"):
                        break  # ya va al interruptor
                    quieto = m.piso[s] in (m.piso_alto[s], m.piso_bajo[s])
                    if not quieto:
                        if math.hypot(bx - x, by - y) < 80:
                            self.espera_elevador = 1
                            self.evento = ("elevador", int(s), "esperar")
                            return accion()
                        break
                    meta = self._interruptor_elevador(aqui, s)
                    if meta:
                        self.meta, self.camino = meta, list(meta["camino"])
                        self.cambio_meta = self.paso
                        self.replan = self.paso + 72
                        self.evento = ("elevador", int(s), que, meta["id"])
                    break
                if que == "llamar" and math.hypot(bx - x, by - y) < 80:
                    self.espera_elevador = 1
                    self.mirar = (bx, by)
                    self.uso, self.uso_tope = 4, 0
                    self.evento = ("elevador", int(s), "llamar")
                    return accion("USE")
                if que == "esperar" and m.sector[aqui[1], aqui[0]] == s:
                    self.espera_elevador = 1
                    self.evento = ("elevador", int(s), "esperar")
                    return accion()
                break
        self.espera_elevador = 0

        # aplastador en los proximos pasos: esperar afuera. Huir ya debajo llega tarde: con el techo
        # bajo 56 Doom no deja moverse a ningun punto que aun toque el sector (MAP04 s1: entro 10
        # unidades por la orilla del 82 con el techo bajando y se quedo trabado de 35 a 0)
        # el margen (frenar a tiempo por la inercia) no aplica con monstruos encima: detenerse ahi con
        # Demons detras lo mataba (MAP04: 16 muertes junto al 62 huyendo a curarse)
        for c in self.camino[:5]:
            if m.aplasta(*c) or (not self.acosado and m.aplasta(*c, margen=True)):
                if self.paso - self.espera_apl > 1:  # un evento por espera, no uno por paso
                    self.evento = ("espera_aplastador", int(m.zona_margen[c[1], c[0]]))
                self.espera_apl = self.paso
                self.ultimo_avance = (self.paso, (x, y))  # esperar no es atorarse
                return accion()

        # puerta cerrada en los proximos pasos: mirarla y presionar USE UNA vez. Un segundo USE
        # sobre una puerta que va abriendo la regresa (MAP02: tres pulsos la abrian y la cerraban).
        # Mientras se mueve, se sigue caminando hacia ella y se espera.
        for c in self.camino[:6]:
            s = int(m.sector[c[1], c[0]])
            if m.puerta_cerrada(s):
                cx, cy = m.centro(*c)
                quieta = m.techo[s] - m.piso[s] < 4
                if math.hypot(cx - x, cy - y) < 72 and quieta and \
                        self.paso - self.uso_puerta.get(s, -999) > 45:
                    dif = self._dif(x, y, angulo, cx, cy)
                    if abs(dif) > 8:
                        return accion(giro=max(-45, min(45, dif)))
                    self.uso_puerta[s] = self.paso
                    self.evento = ("puerta", s)
                    self.ultimo_avance = (self.paso, (x, y))  # esperar la puerta no es atorarse
                    return accion("USE")
                break

        # llego junto a una provision: se da por cumplida aunque no se la haya podido llevar
        # (municion al maximo, objeto en una repisa): si no, la rondaria para siempre
        if self.meta and self.meta["tipo"] == "provision" and len(self.camino) <= 2:
            cx, cy = m.centro(*self.meta["celda"])
            if math.hypot(cx - x, cy - y) < 40:
                self.descartados[self.meta["id"]] = self.paso + 600
                self.evento = ("provision_alcanzada", self.meta["id"])
                self.meta, self.camino = None, []
                # un paso encima del objeto; replantea el siguiente frame. Salvo que ese paso caiga
                # bajo un aplastador: corriendo avanza ~40 unidades y la municion de (628,1627) esta a
                # 24 del 22 de MAP04; el paso lo metia con el techo bajando (22 de 52 muertes)
                a = math.radians(angulo)
                for d in (16, 32, 48):
                    i, j = m.celda(x + math.cos(a) * d, y + math.sin(a) * d)
                    if 0 <= i < m.W and 0 <= j < m.H and m.zona_aplastador[j, i] >= 0:
                        return accion()
                return accion("MOVE_FORWARD")

        # disparador al pisar: al llegar a la linea se da por activado y se sigue de frente para cruzarla
        if self.meta and self.meta["tipo"] == "pisar" and len(self.camino) <= 2:
            x1, y1, x2, y2, _act, _tag = m.disparadores[self.meta["datos"]]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if math.hypot(mx - x, my - y) < 24:
                m.pisados.add(self.meta["datos"])
                self.evento = ("pisado", self.meta["datos"])
                self.meta, self.camino = None, []
                return accion("MOVE_FORWARD")
            # la meta quedo a un lado de la linea: caminar derecho hasta pisarla
            return accion("MOVE_FORWARD", giro=max(-45, min(45, self._dif(x, y, angulo, mx, my))))

        # salida al pisar (accion 52): no se presiona, se cruza la linea caminando. MAP03 y MAP04
        # terminan asi; en MAP03 llegaba y presionaba USE frente a ella 6000 frames
        if len(self.camino) <= 2 and self.meta and self.meta["tipo"] == "salida" and \
                self.meta["datos"][4] in SALIDAS_PISAR:
            t = self.meta["datos"]
            if math.hypot(t[0] - x, t[1] - y) < 64:
                # un punto 24 unidades pasando la linea, del lado contrario al de llegada
                tx, ty = t[2] - (t[0] - t[2]) * 0.75, t[3] - (t[1] - t[3]) * 0.75
                return accion("MOVE_FORWARD", giro=max(-45, min(45, self._dif(x, y, angulo, tx, ty))))

        # al final de la ruta: presionar el interruptor o la salida
        if len(self.camino) <= 2 and self.meta and self.meta["tipo"] in ("salida", "interruptor"):
            t = self.meta["datos"]
            if math.hypot(t[0] - x, t[1] - y) < 40:
                self.mirar, self.pararse = (t[2], t[3]), (t[0], t[1])
                self.uso = 8
                idx = m.metas_uso.index(t)
                self.uso_tope = self.paso + 40 if self.sin_efecto.get(idx, 0) >= 1 else 0
                m.presionados.add(idx)
                # verificar despues que algo se movio; si no, se desmarca y se reintenta
                sectores = [s for s, _cx, _cy in m.tags.get(t[6], [])] if t[6] else []
                if sectores:
                    self.por_verificar[idx] = (self.paso, {s: (m.piso[s], m.techo[s]) for s in sectores})
                self.evento = (self.meta["tipo"], idx)
                self.camino = []
                self.meta = None
                return accion("USE")

        # seguir la ruta: apuntar a un punto ~3 celdas adelante; si en ese tramo hay un salto de
        # teletransporte, apuntar a cruzar su linea (al aparecer en el destino se replantea solo)
        # junto a un pozo, a la celda siguiente: 3 adelante corta la esquina de la cornisa por encima
        k = min(1 if m.orilla_pozo(x, y) else 3, len(self.camino) - 1)
        tx, ty = m.centro(*self.camino[k])
        # si la recta cruza un escalon alto, apuntar mas cerca. MAP01 s3: 2400 frames empujando el
        # pilar del interruptor de salida, con la ruta rodeandolo y la mira atravesandolo
        while k > 0 and not m.recta_ok(x, y, tx, ty):
            k -= 1
            tx, ty = m.centro(*self.camino[k])
        for a, b in zip(self.camino[:4], self.camino[1:5]):
            if a in m.saltos and m.saltos[a][0] == b:
                tx, ty = m.saltos[a][1]
                if self.evento is None:
                    self.evento = ("teletransporte", a)
                break
        dif = self._dif(x, y, angulo, tx, ty)
        if abs(dif) > 45:
            return accion(giro=max(-45, min(45, dif)))
        return accion("MOVE_FORWARD", giro=dif)

    def tramo_libre(self, x, y):
        """Se puede correr: la ruta sigue casi recta un buen tramo y no hay cerca nada que presionar,
        ni puerta, elevador o teletransporte. Corriendo se pasaba de largo frente a interruptores
        y esquinas (MAP01 de 389 a 470 frames, MAP03 de 2569 a 3688)."""
        m = self.mapa
        if self.uso > 0 or self.espera_elevador or len(self.camino) < CORRER_CELDAS:
            return False
        tramo = self.camino[:CORRER_CELDAS]
        fx, fy = m.centro(*tramo[-1])
        largo = math.hypot(fx - x, fy - y)
        if largo < CORRER_CELDAS * CEL * 0.7:
            return False  # la ruta da vueltas
        for c in tramo:
            cx, cy = m.centro(*c)
            # distancia del punto a la recta bot -> final del tramo: mas de ~1.5 celdas es una curva
            if abs((fx - x) * (y - cy) - (x - cx) * (fy - y)) / largo > CEL * 1.5:
                return False
            s = int(m.sector[c[1], c[0]])
            if c in m.saltos or s in m.sector_elevador or s in m.sector_puerta or s in m.sector_llave \
                    or s in m.sector_remoto:
                return False
        if self.meta and self.meta["tipo"] in ("interruptor", "salida", "pisar"):
            cx, cy = m.centro(*self.meta["celda"])
            if math.hypot(cx - x, cy - y) < CORRER_FRENO:
                return False
        return True

    def cubrirse(self, x, y, amenazas, maximo=CUBIERTA_MAX):
        """Pone como ruta el camino a la celda mas cercana (hasta `maximo` de costo) que ninguna
        amenaza ve. Devuelve el largo de la ruta, o None si no hay donde cubrirse."""
        m = self.mapa
        inicio = m.celda(x, y)
        if not m.transitable(*inicio):
            inicio = m.celda_libre_cerca(x, y, 3) or inicio
        dist, prev = self._dijkstra(inicio, limite=4000)
        for c, d in sorted(dist.items(), key=lambda kv: kv[1]):
            if d > maximo:
                return None
            if d < 2:
                continue  # aqui mismo lo estan viendo
            cx, cy = m.centro(*c)
            if not any(m.se_ve(ax, ay, cx, cy) for ax, ay in amenazas):
                camino = self._camino(prev, c)
                self.meta = {"id": "cubierta", "tipo": "cubierta", "celda": c, "datos": None,
                             "camino": camino, "desc": "cubrirse", "dist": round(d * CEL)}
                self.camino = list(camino)
                self.cambio_meta = self.paso
                self.replan = self.paso + CUBIERTA_PASOS
                return len(camino)
        return None

    def _interruptor_elevador(self, aqui, s):
        """La meta de presionar el interruptor mas cercano que mueve el elevador s, con una ruta que
        no necesite ningun elevador (desde abajo no sirve el que esta arriba)."""
        m = self.mapa
        mejor = None
        for idx in m.disparo_elevador.get(s, []):
            t = m.metas_uso[idx]
            if t[4] in (21, 122) and idx in m.presionados:
                continue  # S1: ya no hace nada
            celda = m.celda_libre_cerca(t[0], t[1])
            camino = m.ruta(aqui, [celda]) if celda else None
            # ni este elevador ni otro: llegar al interruptor no puede depender de un elevador
            if not camino or any(m.bloqueo_elevador(a, b) for a, b in zip(camino, camino[1:])):
                continue
            if mejor is None or len(camino) < len(mejor["camino"]):
                mejor = {"id": f"elevador_{idx}", "tipo": "interruptor", "celda": celda, "datos": t,
                         "camino": camino, "desc": f"el interruptor {idx}, que mueve el elevador {s}",
                         "dist": len(camino) * CEL}
        return mejor

    def _dif(self, x, y, angulo, tx, ty):
        deseado = math.degrees(math.atan2(ty - y, tx - x))
        return (deseado - angulo + 180) % 360 - 180

    def _cerca_de_ruta(self, aqui):
        return any(abs(c[0] - aqui[0]) <= 3 and abs(c[1] - aqui[1]) <= 3 for c in self.camino[:8])

    # ---------- texto para Jev y Haiku ----------

    def resumen(self):
        """Linea corta para el estado que leen Jev y Haiku."""
        llaves = ", ".join(sorted(self.mapa.llaves)) or "ninguna"
        meta = self.meta["desc"] if self.meta else "ninguna"
        return (f"Meta actual: {meta}, {len(self.camino)} pasos de ruta. "
                f"Interruptores usados: {len(self.mapa.presionados)}. Llaves: {llaves}.")

    def resumen_mapa(self, x, y):
        """El rompecabezas del nivel en texto, para que Haiku arme el plan."""
        m = self.mapa
        lineas = [f"Mapa {m.nombre}. Jugador en ({round(x)},{round(y)}), salud {int(self.salud)}, "
                  f"municion {int(self.municion)}. Llaves que trae: {', '.join(sorted(m.llaves)) or 'ninguna'}."]
        for color, _n, kx, ky in m.llaves_mapa:
            if color not in m.llaves:
                lineas.append(f"- Llave {color} en ({kx},{ky}).")
        puertas = {}
        for s, color in m.sector_llave.items():
            js, is_ = np.nonzero(m.sector == s)
            if len(is_):
                cx, cy = m.centro(int(is_.mean()), int(js.mean()))
                puertas.setdefault(color, []).append(f"({round(cx)},{round(cy)})")
        for color, pos in puertas.items():
            lineas.append(f"- Puertas que piden llave {color}: {', '.join(pos[:4])}.")
        for i, t in enumerate(m.metas_uso):
            estado = "ya usado" if i in m.presionados else "sin usar"
            if t[5]:
                lineas.append(f"- Salida (interruptor o linea) en ({round(t[2])},{round(t[3])}).")
            else:
                lineas.append(f"- {self._desc_interruptor(i, t)}, {estado}.")
        for k in range(len(m.disparadores)):
            if m.disparadores[k][4] != 3:
                estado = "ya pisada" if k in m.pisados else "sin pisar"
                lineas.append(f"- {self._desc_disparador(k)}, {estado}.")
        if m.sector_elevador:
            pos = []
            for s in sorted(m.sector_elevador):
                js, is_ = np.nonzero(m.sector == s)
                if len(is_):
                    cx, cy = m.centro(int(is_.mean()), int(js.mean()))
                    pos.append(f"({round(cx)},{round(cy)})")
            lineas.append(f"- Elevadores en {', '.join(pos)}.")
        if self.cands:
            lineas.append("Metas con ruta AHORA (id: que es, distancia):")
            for c in self.cands:
                lineas.append(f"  {c['id']}: {c['desc']}, {c['dist']}")
        else:
            lineas.append("Sin metas calculadas todavia.")
        if self.descartados:
            lineas.append(f"Metas que fallaron (atorado): {', '.join(sorted(k for k, v in self.descartados.items() if v > self.paso))}.")
        pct = 100 * self.visitado.sum() / max(1, ((m.sector >= 0) & ~m.pared).sum())
        lineas.append(f"Explorado: {pct:.0f}% del mapa.")
        return "\n".join(lineas)


def cargar(nombre="MAP01"):
    import vizdoom as vzd
    return Mapa(os.path.join(os.path.dirname(vzd.__file__), "freedoom2.wad"), nombre)
