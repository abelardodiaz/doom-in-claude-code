"""Benchmark del reparto: solo codigo / + Jev / + Jev + Haiku, en los mismos mapas y semillas.

Uso:
  python bench_reparto.py --modo codigo --mapas MAP01,MAP02 --semillas 2
  python bench_reparto.py --modo jev --mapas MAP01,MAP02          (pide TYPESAFE_API_KEY)
  python bench_reparto.py --modo jev_haiku --mapas MAP01,MAP02    (ademas usa `claude -p --model haiku`)

El juego espera a cada llamada (modo sincrono), asi que la latencia no penaliza aqui: se mide
la calidad de las decisiones, no la velocidad. En el juego real Jev corre en su propio hilo.
Jev decide cada 9 frames (~1 por segundo de juego) para no pasar el limite de ~90 llamadas/min.
"""
import argparse
import json
import math
import os
import random
import re
import subprocess
import time

import doom_bridge as db
import navegacion as nv

CELDA = 128
JEV_CADA = 9
HAIKU_CADA = 900
HAIKU_MIN = 150
ESTANCADO = 540  # ~60 s de juego sin llave ni interruptor nuevo: replantear (Sonnet si hay escalamiento)
PREGUNTA = "v2"  # pregunta de meta para Jev; --pregunta v1 para la original
AQUI = os.path.dirname(os.path.abspath(__file__))
PLANNER = os.path.join(AQUI, "..", "prompts", "planner.md")


def pedir_plan(resumen, modelo="haiku"):
    """Planificador por la CLI de Claude Code (usa la sesion del usuario, sin API key aparte)."""
    with open(PLANNER, encoding="utf-8") as f:
        sistema = f.read().replace("{LANGUAGE}", "in Mexican Spanish")
    prompt = f"{sistema}\n\n--- Estado del nivel ---\n{resumen}\n"
    t0 = time.time()
    r = subprocess.run(["claude", "-p", "--model", modelo], input=prompt, capture_output=True,
                       text=True, encoding="utf-8", timeout=120, shell=(os.name == "nt"))
    seg = round(time.time() - t0, 1)
    m = re.search(r"\{.*\}", r.stdout, re.S)
    if not m:
        return None, "", seg, r.stdout[-200:]
    try:
        d = json.loads(m.group(0))
        return [str(x) for x in d.get("plan", [])][:5], d.get("comentario", ""), seg, ""
    except ValueError:
        return None, "", seg, r.stdout[-200:]


def correr(mapa, semilla, modo, frames, log):
    random.seed(semilla)
    g = db.crear_juego(mapa)
    g.set_seed(semilla)
    g.new_episode()
    nav = nv.Navegador(nv.cargar(mapa))
    cerebro = db.Cerebro(nav)
    piloto = None
    if modo in ("jev", "jev_haiku", "jev_haiku_sonnet"):
        from jev_pilot import PilotoJev
        piloto = PilotoJev(con_imagen=True, pregunta=PREGUNTA)
    orden = "explorar"
    celdas, muertes, terminado = set(), 0, None
    ultimo = {}
    st_jev = {"llamadas": 0, "dudas_tactica": 0, "dudas_meta": 0, "errores": 0, "ms": 0}
    planea = modo in ("jev_haiku", "jev_haiku_sonnet")
    st_haiku = {"llamadas": 0, "seg": 0.0, "fallos": 0, "sonnet": 0}
    ult_haiku = -HAIKU_MIN
    # motivo de la proxima consulta al planificador: inicio, evento, muerte o estancado van a
    # Sonnet en el modo con escalamiento; la revision periodica siempre es Haiku
    pendiente_haiku = "inicio" if planea else None
    ult_progreso = 0
    ultima_llamada = 0.0
    for n in range(frames):
        if g.is_episode_finished() and not g.is_player_dead():
            terminado = n
            break
        if g.is_player_dead():
            muertes += 1
            log({"ev": "muerte", "frame": n, **ultimo})
            g.new_episode()
            nav = nv.Navegador(nv.cargar(mapa))
            cerebro = db.Cerebro(nav)
            pendiente_haiku = "muerte" if planea else None
        st = g.get_state()
        if st is None:
            g.advance_action(1)
            continue
        v = st.game_variables
        celdas.add((int(v[4] // CELDA), int(v[5] // CELDA)))
        # lo ultimo que se vio vivo, para saber que lo mato
        cerca = sorted(((round(math.hypot(o.position_x - v[4], o.position_y - v[5])), o.name)
                        for o in st.objects if o.name in db.MONSTRUOS or o.name in db.PROYECTILES))
        ultimo = {"pos": [round(v[4]), round(v[5])], "salud": int(v[0]), "municion": int(v[2]),
                  "arma": int(v[12]), "modo": cerebro.modo, "cerca": cerca[:6]}
        if n % 200 == 0:
            # foto periodica: si se traba sin eventos (peleando con algo inalcanzable), aqui se ve
            log({"ev": "foto", "frame": n, **ultimo, "meta": nav.meta["id"] if nav.meta else None})

        # Haiku: plan al inicio, cada tanto y tras eventos que cambian el rompecabezas
        if planea and not pendiente_haiku and n - ult_progreso >= ESTANCADO:
            pendiente_haiku, ult_progreso = "estancado", n
        if planea and nav.cands and (pendiente_haiku or n - ult_haiku >= HAIKU_CADA) \
                and n - ult_haiku >= HAIKU_MIN:
            modelo = "sonnet" if modo == "jev_haiku_sonnet" and pendiente_haiku else "haiku"
            plan, coment, seg, err = pedir_plan(nav.resumen_mapa(v[4], v[5]), modelo)
            st_haiku["llamadas"] += 1
            st_haiku["sonnet"] += modelo == "sonnet"
            st_haiku["seg"] += seg
            if plan:
                nav.plan = plan
            else:
                st_haiku["fallos"] += 1
            log({"ev": "haiku", "frame": n, "modelo": modelo, "motivo": pendiente_haiku or "periodico",
                 "plan": plan, "comentario": coment, "seg": seg, "error": err})
            ult_haiku, pendiente_haiku = n, None

        # Jev: tactica y meta, cada JEV_CADA frames
        if piloto and n % JEV_CADA == 0:
            espera = 0.7 - (time.time() - ultima_llamada)
            if espera > 0:
                time.sleep(espera)
            ultima_llamada = time.time()
            estado = db.describir(st, v, False, muertes, st.screen_buffer.shape[1], cerebro) + " " + nav.resumen()
            metas = [(c["id"], f"{c['desc']}, a {c['dist']} unidades") for c in nav.cands][:8]
            try:
                d = piloto.decidir(st.screen_buffer, estado, metas)
                st_jev["llamadas"] += 1
                st_jev["ms"] += d["ms"]
                st_jev["dudas_tactica"] += d["tactica"] is None
                st_jev["dudas_meta"] += d["meta"] is None and len(metas) >= 2
                orden = db.TACTICA_A_MODO[d["tactica"]]
                nav.pedido_jev = d["meta"]
                log({"ev": "jev", "frame": n, "tactica": d["tactica"], "cruda": d["tactica_cruda"],
                     "brecha": d["brecha_tactica"], "meta": d["meta"], "brecha_meta": d["brecha_meta"],
                     "ms": d["ms"]})
            except Exception as ex:  # 403/429/499: falla, no decision
                st_jev["errores"] += 1
                orden, nav.pedido_jev = "explorar", None
                log({"ev": "jev_error", "frame": n, "error": str(ex)[:150]})

        act, _ = cerebro.decidir(st, v, orden)
        if nav.evento:
            log({"ev": "nav", "frame": n, "que": [str(x) for x in nav.evento]})
            if nav.evento[0] in ("llave_recogida", "interruptor"):
                ult_progreso = n
                pendiente_haiku = "evento" if planea else None
            elif nav.evento[0] == "atorado" and nav.fallos.get(nav.evento[2], 0) >= 3:
                pendiente_haiku = "estancado" if planea else None
        g.make_action(act, 4)
    kills = int(g.get_game_variable(db.vzd.GameVariable.KILLCOUNT))
    g.close()
    if st_jev["llamadas"]:
        st_jev["ms"] = round(st_jev["ms"] / st_jev["llamadas"])
    return {"mapa": mapa, "semilla": semilla, "modo": modo, "pregunta": PREGUNTA if modo != "codigo" else None, "celdas": len(celdas), "kills": kills,
            "muertes": muertes, "terminado": terminado, "jev": st_jev, "haiku": st_haiku}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["codigo", "jev", "jev_haiku", "jev_haiku_sonnet"], required=True)
    ap.add_argument("--mapas", default="MAP01,MAP02")
    ap.add_argument("--semillas", type=int, default=1)
    ap.add_argument("--frames", default="MAP01:2000,MAP02:6000", help="tope por mapa; default 4000")
    ap.add_argument("--salida", default=os.path.join(AQUI, "..", "bench-resultados"))
    ap.add_argument("--pregunta", choices=["v1", "v2"], default="v2")
    a = ap.parse_args()
    PREGUNTA = a.pregunta
    topes = dict(x.split(":") for x in a.frames.split(","))
    os.makedirs(a.salida, exist_ok=True)
    for mapa in a.mapas.split(","):
        for s in range(1, a.semillas + 1):
            etiqueta = a.modo if a.modo == "codigo" else f"{a.modo}-{a.pregunta}"
            ruta = os.path.join(a.salida, f"{etiqueta}-{mapa}-s{s}.jsonl")
            with open(ruta, "w", encoding="utf-8") as f:
                def log(d, f=f):
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
                    f.flush()
                t0 = time.time()
                r = correr(mapa, s, a.modo, int(topes.get(mapa, 4000)), log)
                r["seg_reales"] = round(time.time() - t0)
                log({"ev": "resultado", **r})
            print(json.dumps(r, ensure_ascii=False), flush=True)
