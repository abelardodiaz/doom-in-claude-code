"""Piloto Jev: mira el frame y el estado del juego y devuelve probabilidades por modo.

La key se lee de la variable de entorno TYPESAFE_API_KEY (el mod la pasa desde su configuracion).
"""
import base64
import io
import os
import time
import uuid

import requests
from PIL import Image

URL = "https://api.typesafe.ai/v1/systemone"

MODOS = {
    "atacar": "Hay un enemigo a la vista y conviene pelear con el",
    "explorar": "No hay peligro inmediato: avanzar por el mapa buscando puertas, salida y enemigos",
    "retirada": "Hay enemigos cerca y la salud esta baja: retroceder disparando",
    "recoger": "Hay un objeto util a la vista (botiquin, municion, armadura, arma) y conviene ir por el",
}


def _key():
    k = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not k:
        raise RuntimeError("falta TYPESAFE_API_KEY")
    return k


class PilotoJev:
    def __init__(self, con_imagen=True):
        self.con_imagen = con_imagen
        self.modelo = "jev-preview" if con_imagen else "jev-latest"
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
        if con_imagen:
            self.s.headers["TypeSafe-Danger-Zone-Images"] = "true"

    def decidir(self, frame_rgb, estado, modo_actual):
        """Devuelve (modo, probabilidades, peligro, ms) o lanza excepcion."""
        texto = f"Juego Doom, vista en primera persona. Modo actual: {modo_actual}. {estado}"
        cuerpo = {
            "model": self.modelo,
            "questions": {
                "modo": {
                    "type": "choice",
                    "instructions": "Que estrategia le conviene ahora al jugador?",
                    "criteria": MODOS,
                },
                "peligro": {
                    "type": "noul",
                    "instructions": "El jugador esta en peligro inmediato de morir?",
                },
            },
        }
        if self.con_imagen and frame_rgb is not None:
            ph = "img-" + uuid.uuid4().hex
            buf = io.BytesIO()
            Image.fromarray(frame_rgb).resize((448, 336)).save(buf, format="JPEG", quality=70)
            cuerpo["state"] = {"pantalla": ph, "datos": texto}
            cuerpo["assets"] = {ph: {"type": "image", "format": "jpeg",
                                     "data_base64": base64.b64encode(buf.getvalue()).decode()}}
        else:
            cuerpo["state"] = texto
        t0 = time.time()
        r = self.s.post(URL, json=cuerpo, timeout=10)
        ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        ans = r.json()["answers"]
        return ans["modo"]["choice"], ans["modo"]["probabilities"], ans["peligro"]["noul"], ms


if __name__ == "__main__":
    # Prueba: un frame real de MAP01, con y sin imagen
    import vizdoom as vzd
    from doom_bridge import crear_juego, describir, accion
    g = crear_juego()
    for _ in range(15):
        g.make_action(accion("MOVE_FORWARD"), 4)
    st = g.get_state()
    est = describir(st, st.game_variables, False, 0, st.screen_buffer.shape[1])
    print("estado:", est)
    for img in (False, True):
        p = PilotoJev(con_imagen=img)
        for i in range(3):
            try:
                print(p.modelo, p.decidir(st.screen_buffer, est, "explorar"))
            except Exception as ex:
                print(p.modelo, "ERROR", ex)
    g.close()
