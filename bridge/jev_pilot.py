"""Piloto Jev: mira el frame y el estado y elige entre las opciones que arma el codigo.

Dos preguntas por llamada (casi no cuesta mas que una):
- tactica: pelear, esquivar o avanzar hacia la meta;
- meta: cual de las metas con ruta perseguir (salida, llave, interruptor, provision, frontera).

Reglas aprendidas de otros builders (sesion jev-117, 2026-10-21):
- version fija (la calibracion cambio de 1.13 a 1.14);
- decidir por argmax de probabilities, no por el campo choice;
- confianza = brecha entre las dos mas altas; por debajo de 0.2 decide el script;
- choice favorece la primera opcion: el orden se baraja en cada llamada.

La key se lee de la variable de entorno TYPESAFE_API_KEY (el mod la pasa desde su configuracion).
"""
import base64
import io
import os
import random
import time
import uuid

import requests
from PIL import Image

URL = "https://api.typesafe.ai/v1/systemone"
MODELO = "jev-1.14.0"
BRECHA_MIN = 0.2

TACTICAS = {
    "pelear": "Hay un enemigo a la vista y conviene pelear con el",
    "esquivar": "Hay peligro cerca (salud baja o varios enemigos): retroceder disparando",
    "avanzar": "No vale la pena pelear ahora: seguir hacia la meta",
    "curarse": "La salud esta baja y hay un botiquin con ruta: dejar la pelea e ir por el",
}


def _key():
    k = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not k:
        raise RuntimeError("falta TYPESAFE_API_KEY")
    return k


def _barajar(d):
    items = list(d.items())
    random.shuffle(items)
    return dict(items)


def _decision(ans):
    """(opcion, brecha, probabilidades) usando argmax, no el campo choice."""
    probs = ans["probabilities"]
    orden = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    brecha = orden[0][1] - (orden[1][1] if len(orden) > 1 else 0.0)
    return orden[0][0], round(brecha, 2), probs


# v1 empujaba a explorar (MAP01: "frontera" 152 de 223, "salida" 7). v2 dice para que sirve cada meta.
PREGUNTA_META = {
    "v1": "Hacia cual meta conviene ir ahora para avanzar en el nivel sin morir?",
    "v2": ("El objetivo es TERMINAR el nivel llegando a la salida. La salida lo termina; una llave abre "
           "las puertas de su color; un interruptor abre puertas lejanas o baja elevadores; armas, salud "
           "y municion solo si hacen falta; explorar zonas nuevas solo cuando no hay otra forma de avanzar. "
           "Cual de estas metas acerca mas a terminar el nivel?"),
}


class PilotoJev:
    def __init__(self, con_imagen=True, pregunta="v2"):
        self.pregunta = pregunta
        self.con_imagen = con_imagen
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
        if con_imagen:
            self.s.headers["TypeSafe-Danger-Zone-Images"] = "true"

    def decidir(self, frame_rgb, estado, metas, pelea=None):
        """metas: lista de (id, descripcion). pelea: texto con los numeros del codigo (enemigos,
        distancias, arma) para la pregunta si/no de pelear; None = no se pregunta.
        Devuelve un dict con la decision y sus numeros."""
        texto = f"Juego Doom, vista en primera persona. {estado}"
        if pelea:
            texto += f" Situacion de combate: {pelea}"
        preguntas = {
            "tactica": {"type": "choice", "instructions": "Que debe hacer el jugador en este momento?",
                        "criteria": _barajar(TACTICAS)},
            "peligro": {"type": "noul", "instructions": "El jugador esta en peligro inmediato de morir?"},
        }
        if pelea:
            preguntas["pelear"] = {
                "type": "noul",
                "instructions": ("Con esta arma, esta municion y esta salud, conviene pelear ahora con los "
                                 "enemigos a la vista, en vez de ignorarlos y seguir hacia la meta?")}
        if len(metas) >= 2:
            preguntas["meta"] = {
                "type": "choice",
                "instructions": PREGUNTA_META[self.pregunta],
                "criteria": _barajar({i: d for i, d in metas}),
            }
        cuerpo = {"model": MODELO, "questions": preguntas}
        if self.con_imagen and frame_rgb is not None:
            ph = "img-" + uuid.uuid4().hex
            buf = io.BytesIO()
            # lado minimo de 280 px (1.14); 448x336 pasa
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
            # 403/429/499 son fallas, no decisiones: quien llama usa su respaldo
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        ans = r.json()["answers"]
        tactica, brecha_t, probs_t = _decision(ans["tactica"])
        out = {"tactica": tactica if brecha_t >= BRECHA_MIN else None, "tactica_cruda": tactica,
               "brecha_tactica": brecha_t, "probs": probs_t, "peligro": ans["peligro"]["noul"], "ms": ms,
               "meta": None, "brecha_meta": None, "probs_meta": None,
               "pelear": ans["pelear"]["noul"] if "pelear" in ans else None}
        if len(metas) == 1:
            out["meta"] = metas[0][0]
        elif "meta" in ans:
            meta, brecha_m, probs_m = _decision(ans["meta"])
            out.update(meta=meta if brecha_m >= BRECHA_MIN else None, meta_cruda=meta,
                       brecha_meta=brecha_m, probs_meta=probs_m)
        return out
