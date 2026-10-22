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
# elevadores (bajan, esperan y suben): por interruptor/USE o al pisar una linea
ELEVADORES_USE = {21, 62, 122, 123}
ELEVADORES_PISAR = {10, 88, 120, 121}

# abastecimiento: nombres de objetos de ViZDoom por necesidad
ARMAS = {"Shotgun", "SuperShotgun", "Chaingun", "RocketLauncher", "PlasmaRifle", "BFG9000"}
SALUD = {"Stimpack", "Medikit", "Soulsphere", "Megasphere"}
MUNICION = {"Clip", "ClipBox", "Shell", "ShellBox", "RocketAmmo", "RocketBox", "Cell", "CellPack", "Backpack"}
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
        self.pared = np.zeros((self.H, self.W), dtype=bool)
        r = int(math.ceil(RADIO / CEL))
        disco = [(dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                 if (dx * CEL) ** 2 + (dy * CEL) ** 2 <= (RADIO + CEL / 2) ** 2]
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if bk >= 0 and not (flags & 1):
                continue
            largo = math.hypot(x2 - x1, y2 - y1)
            for k in range(int(largo // 6) + 1):
                t = k * 6 / largo if largo else 0
                i, j = self.celda(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
                for dx, dy in disco:
                    if 0 <= j + dy < self.H and 0 <= i + dx < self.W:
                        self.pared[j + dy, i + dx] = True

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
                if tag:
                    for s, sec in enumerate(m.sectors):
                        if sec.tag == tag:
                            self.sector_llave[s] = color
                elif bk >= 0:
                    self.sector_llave[bk] = color
        # elevadores: sectores con el tag de una linea de elevador. Las lineas de USE sin tag
        # (estilo "presiona el costado del elevador") apuntan a su propio sector de atras.
        self.sector_elevador = set()
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if act in ELEVADORES_USE or act in ELEVADORES_PISAR:
                if tag:
                    self.sector_elevador |= {s for s, sec in enumerate(m.sectors) if sec.tag == tag}
                elif bk >= 0:
                    self.sector_elevador.add(bk)
        # llaves tiradas en el mapa (se omiten las que solo salen en multijugador)
        self.llaves_mapa = [(LLAVES[t.type][0], LLAVES[t.type][1], t.x, t.y)
                            for t in m.things if t.type in LLAVES and not (t.flags & 16)]
        self.llaves = set()  # colores que ya trae el jugador

        # interruptores y salidas: punto de llegada del lado de enfrente, a 32 unidades de la linea
        self.metas_uso = []   # (x, y, mira_x, mira_y, accion, es_salida)
        for (x1, y1, x2, y2, fr, bk, act, tag, flags) in lineas:
            if act in INTERRUPTORES or act in SALIDAS:
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                # normal hacia el lado de enfrente (derecha de a->b en Doom)
                nx, ny = (y2 - y1), -(x2 - x1)
                n = math.hypot(nx, ny) or 1
                px, py = mx + nx / n * 32, my + ny / n * 32
                self.metas_uso.append((px, py, mx, my, act, act in SALIDAS))
        self.presionados = set()

    def celda(self, x, y):
        return int((x - self.x0) // CEL), int((y - self.y0) // CEL)

    def centro(self, i, j):
        return self.x0 + (i + 0.5) * CEL, self.y0 + (j + 0.5) * CEL

    def actualizar_alturas(self, sectores):
        for s in sectores:
            if 0 <= s.id < len(self.piso):
                self.piso[s.id] = s.floor_height
                self.techo[s.id] = s.ceiling_height

    def puerta_cerrada(self, s):
        return (s in self.sector_puerta or s in self.sector_llave) and self.techo[s] - self.piso[s] < ALTO_MIN

    def transitable(self, i, j):
        if not (0 <= i < self.W and 0 <= j < self.H) or self.pared[j, i]:
            return False
        s = self.sector[j, i]
        if s < 0:
            return False
        if self.techo[s] - self.piso[s] >= ALTO_MIN:
            return True
        # cerrada: se puede pasar si se abre con USE y, si pide llave, ya se trae
        if s in self.sector_llave and self.sector_llave[s] not in self.llaves:
            return False
        return s in self.sector_puerta or s in self.sector_llave

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
        if self.piso[sb] - self.piso[sa] <= PASO_MAX:
            return True
        # un elevador baja hasta el piso de al lado: se puede subir a el, y desde el (arriba) salir
        return sb in self.sector_elevador or sa in self.sector_elevador

    def bloqueo_elevador(self, a, b):
        """Si el paso a->b necesita un elevador que ahora no esta a la altura, devuelve su sector."""
        sa, sb = self.sector[a[1], a[0]], self.sector[b[1], b[0]]
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
                yield n, costo

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
    """Decide hacia donde caminar y cuando presionar USE. Devuelve botones."""

    def __init__(self, mapa):
        self.mapa = mapa
        self.visitado = np.zeros((mapa.H, mapa.W), dtype=bool)
        self.camino = []
        self.meta = None          # (tipo, datos)
        self.replan = 0
        self.castigo = {}
        self.ultimo_avance = (0, None)
        self.uso = 0
        self.mirar = None
        self.paso = 0
        self.evento = None        # ultimo evento para la bitacora
        self.salud, self.municion, self.objetos = 100, 50, []
        self.descartados = set()  # provisiones a las que no se pudo llegar
        self.objetivo_provision = None

    def marcar_visto(self, x, y):
        i, j = self.mapa.celda(x, y)
        r = 6  # ~96 unidades
        self.visitado[max(0, j - r):j + r + 1, max(0, i - r):i + r + 1] = True

    def provision(self, inicio):
        """Arma nueva cercana siempre; salud o municion solo si hacen falta."""
        quiero = set(ARMAS)
        if self.salud < 50:
            quiero |= SALUD
        if self.municion < 20:
            quiero |= MUNICION
        cand = []
        for o in self.objetos:
            if o.name in quiero and (round(o.position_x), round(o.position_y)) not in self.descartados:
                c = self.mapa.celda_libre_cerca(o.position_x, o.position_y, 2)
                if c and abs(c[0] - inicio[0]) + abs(c[1] - inicio[1]) < DESVIO_MAX:
                    cand.append((o, c))
        if not cand:
            return None, []
        camino = self.mapa.ruta(inicio, [c for _, c in cand], self.castigo, limite=20000)
        if camino and len(camino) <= DESVIO_MAX:
            o = next(o for o, c in cand if c == camino[-1])
            self.objetivo_provision = (round(o.position_x), round(o.position_y))
            return ("provision", o.name), camino
        return None, []

    def elegir_meta(self, inicio):
        m = self.mapa
        meta, camino = self.provision(inicio)
        if camino:
            return meta, camino
        salidas =[(t, m.celda_libre_cerca(t[0], t[1])) for t in m.metas_uso if t[5]]
        for t, c in salidas:
            if c:
                camino = m.ruta(inicio, [c], self.castigo)
                if camino:
                    return ("salida", t), camino
        # sin ruta a la salida: ir por una llave que falte (abren las puertas de color)
        faltan = [(k, m.celda_libre_cerca(k[2], k[3])) for k in m.llaves_mapa if k[0] not in m.llaves]
        faltan = [(k, c) for k, c in faltan if c]
        if faltan:
            camino = m.ruta(inicio, [c for _, c in faltan], self.castigo, limite=60000)
            if camino:
                k = next(k for k, c in faltan if c == camino[-1])
                return ("llave", k), camino
        pend =[(t, m.celda_libre_cerca(t[0], t[1])) for i, t in enumerate(m.metas_uso)
                if not t[5] and i not in m.presionados]
        pend = [(t, c) for t, c in pend if c]
        if pend:
            camino = m.ruta(inicio, [c for _, c in pend], self.castigo, limite=40000)
            if camino:
                fin = camino[-1]
                t = next(t for t, c in pend if c == fin)
                return ("interruptor", t), camino
        # frontera: celdas transitables no visitadas
        js, is_ = np.nonzero(~self.visitado & (self.mapa.sector >= 0) & ~self.mapa.pared)
        front = [(int(i), int(j)) for i, j in zip(is_, js) if m.transitable(int(i), int(j))]
        if front:
            # las mas cercanas primero, para no pagar un Dijkstra sobre todo el mapa
            front.sort(key=lambda c: (c[0] - inicio[0]) ** 2 + (c[1] - inicio[1]) ** 2)
            camino = m.ruta(inicio, front[:400], self.castigo, limite=40000)
            if camino:
                return ("frontera", camino[-1]), camino
        return None, []

    def decidir(self, x, y, angulo, sectores, accion, objetos=None, salud=100, municion=50):
        """accion(*botones) arma el vector de botones del juego."""
        m = self.mapa
        self.paso += 1
        self.evento = None
        self.salud, self.municion = salud, municion
        self.objetos = objetos or []
        if sectores is not None:
            m.actualizar_alturas(sectores)
        if objetos is not None:
            nuevas = m.actualizar_llaves(objetos)
            if nuevas:
                # con llave nueva cambian las rutas posibles: replanear ya
                self.evento = ("llave_recogida", sorted(nuevas))
                self.camino = []
                self.castigo = {}
        self.marcar_visto(x, y)
        aqui = m.celda(x, y)

        # pulsos de USE en curso (abrir puerta o presionar interruptor)
        if self.uso > 0:
            self.uso -= 1
            if self.mirar:
                dif = self._dif(x, y, angulo, *self.mirar)
                if abs(dif) > 6:
                    return accion(giro=max(-45, min(45, dif)))
            return accion("USE") if self.uso % 2 else accion()

        # atoron: sin avance en ~2 s
        if self.ultimo_avance[1] is None or math.hypot(x - self.ultimo_avance[1][0], y - self.ultimo_avance[1][1]) > 24:
            self.ultimo_avance = (self.paso, (x, y))
        elif self.paso - self.ultimo_avance[0] > 18:
            self.evento = ("atorado", aqui)
            if self.meta and self.meta[0] == "provision" and self.objetivo_provision:
                self.descartados.add(self.objetivo_provision)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if self.camino:
                        k = min(3, len(self.camino) - 1)
                        c = (self.camino[k][0] + dx, self.camino[k][1] + dy)
                        self.castigo[c] = self.castigo.get(c, 0) + 30
            self.camino = []
            self.ultimo_avance = (self.paso, (x, y))
            self.uso = 4
            self.mirar = None
            return accion("MOVE_BACKWARD", "USE")

        # replanear cada ~3 s, al perder la ruta o al alejarse de ella
        if not self.camino or self.paso >= self.replan or not self._cerca_de_ruta(aqui):
            inicio = aqui if m.transitable(*aqui) else (m.celda_libre_cerca(x, y, 3) or aqui)
            self.meta, self.camino = self.elegir_meta(inicio)
            self.replan = self.paso + 27
            self.evento = self.evento or ("meta", self.meta[0] if self.meta else None, len(self.camino))
            if not self.camino:
                return accion("USE", giro=30) if self.paso % 2 else accion(giro=30)

        # avanzar el indice de la ruta
        while len(self.camino) > 1 and math.hypot(*(np.subtract(m.centro(*self.camino[0]), (x, y)))) < 24:
            self.camino.pop(0)

        # puerta cerrada en los proximos pasos: mirarla y presionar USE
        for c in self.camino[:6]:
            s = m.sector[c[1], c[0]]
            if m.puerta_cerrada(s):
                cx, cy = m.centro(*c)
                if math.hypot(cx - x, cy - y) < 72:
                    self.mirar = (cx, cy)
                    self.uso = 6
                    self.evento = ("puerta", int(s))
                    return accion("USE")
                break

        # al final de la ruta: presionar el interruptor o la salida
        if len(self.camino) <= 2 and self.meta and self.meta[0] in ("salida", "interruptor"):
            t = self.meta[1]
            if math.hypot(t[0] - x, t[1] - y) < 40:
                self.mirar = (t[2], t[3])
                self.uso = 8
                idx = m.metas_uso.index(t)
                m.presionados.add(idx)
                self.evento = (self.meta[0], idx)
                self.camino = []
                return accion("USE")

        # seguir la ruta: apuntar a un punto ~3 celdas adelante
        k = min(3, len(self.camino) - 1)
        tx, ty = m.centro(*self.camino[k])
        dif = self._dif(x, y, angulo, tx, ty)
        if abs(dif) > 45:
            return accion(giro=max(-45, min(45, dif)))
        return accion("MOVE_FORWARD", giro=dif)

    def _dif(self, x, y, angulo, tx, ty):
        deseado = math.degrees(math.atan2(ty - y, tx - x))
        return (deseado - angulo + 180) % 360 - 180

    def _cerca_de_ruta(self, aqui):
        return any(abs(c[0] - aqui[0]) <= 3 and abs(c[1] - aqui[1]) <= 3 for c in self.camino[:8])

    def resumen(self):
        """Texto corto para Jev y Haiku."""
        if not self.meta:
            return "Sin meta de navegacion."
        tipo = self.meta[0]
        if tipo == "llave":
            tipo = f"llave {self.meta[1][0]}"
        llaves = ", ".join(sorted(self.mapa.llaves)) or "ninguna"
        return (f"Navegacion: meta {tipo}, {len(self.camino)} pasos de ruta, "
                f"{len(self.mapa.presionados)} interruptores usados, llaves: {llaves}.")


def cargar(nombre="MAP01"):
    import vizdoom as vzd
    return Mapa(os.path.join(os.path.dirname(vzd.__file__), "freedoom2.wad"), nombre)
