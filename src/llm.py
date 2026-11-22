"""Cliente del modelo de lenguaje.

Con LLM_API_KEY definida llama a cualquier API compatible con OpenAI (Groq, Gemini,
OpenAI, Ollama). Sin ella usa un simulador determinista: sirve para los tests y para
hacer el laboratorio sin cuenta, pero no es un modelo.
"""
import json
import os
import re
import sys
import time

import requests

BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
API_KEY = os.getenv("LLM_API_KEY", "")
MIN_INTERVAL = float(os.getenv("LLM_MIN_INTERVAL", "3.5"))  # 8000 tokens por minuto, ~440 por request

_last_call = 0.0


def model_name() -> str:
    return MODEL if API_KEY else "simulador"


def chat(system: str, user: str, temperature: float = 0.0, max_tokens: int = 200) -> dict:
    """Devuelve text, prompt_tokens, completion_tokens, latency_s y model."""
    start = time.perf_counter()
    if API_KEY:
        text, prompt_tokens, completion_tokens, start = _call_api(system, user, temperature, max_tokens)
    else:
        text = _simulate(system, user)
        prompt_tokens = (len(system) + len(user)) // 4
        completion_tokens = len(text) // 4
    return {
        "text": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_s": round(time.perf_counter() - start, 3),
        "model": model_name(),
    }


def _call_api(system: str, user: str, temperature: float, max_tokens: int):
    global _last_call
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for attempt in range(5):
        wait = MIN_INTERVAL - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        start = time.perf_counter()  # la espera entre requests no cuenta como latencia
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
            timeout=60,
        )
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(float(response.headers.get("retry-after", 2 ** attempt)))
            continue
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage", {})
        return (
            body["choices"][0]["message"]["content"] or "",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            start,
        )
    raise RuntimeError(f"El proveedor respondió {response.status_code} en 5 intentos")


# --- Simulador -------------------------------------------------------------------
# Imita tres fallas reales de un LLM según lo que diga el prompt de sistema:
#   sin lista de categorías  -> inventa etiquetas
#   sin pedir JSON           -> responde en prosa
#   sin regla de inyección   -> obedece las instrucciones escritas dentro del ticket

_KEYWORDS = {
    "precio": ["comisi", "cobr", "caro", "tarifa", "precio", "subieron", "mantenimiento"],
    "competencia": ["otro banco", "competencia", "me ofrece", "cambiarme", "otra billetera"],
    "soporte": ["nadie responde", "atención", "reclamo", "esperando", "soporte", "call center"],
    "producto": ["la app", "error", "transferencia", "no funciona", "se cae", "bloque"],
}
_FREE_LABELS = {
    "precio": "costos",
    "competencia": "competidores",
    "soporte": "atención al cliente",
    "producto": "fallas técnicas",
    "otro": "consulta general",
}
_LEAVING = ["cancelar", "cerrar mi cuenta", "me voy", "dar de baja", "me cambio"]


def _simulate(system: str, user: str) -> str:
    system_l, ticket = system.lower(), user.lower()
    if "ignora" in ticket and "instrucciones" not in system_l:
        return json.dumps({"categoria": "otro", "riesgo_churn": "bajo", "resumen": "APROBADO"})

    categoria = "otro"
    for name, words in _KEYWORDS.items():
        if any(word in ticket for word in words):
            categoria = name
            break
    if any(word in ticket for word in _LEAVING):
        riesgo = "alto"
    elif categoria in ("precio", "competencia", "soporte"):
        riesgo = "medio"
    else:
        riesgo = "bajo"

    if "competencia" not in system_l:
        categoria = _FREE_LABELS[categoria]
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", user.strip())
                 if "ignora" not in s.lower() and "APROBADO" not in s]
    resumen = (sentences[0] if sentences else "")[:120]
    if "json" not in system_l:
        return f"El ticket trata de {categoria} y el riesgo de que el cliente se vaya es {riesgo}."
    return json.dumps({"categoria": categoria, "riesgo_churn": riesgo, "resumen": resumen},
                      ensure_ascii=False)


if __name__ == "__main__":
    # python -m src.llm            -> prueba de conexión
    # python -m src.llm --models   -> modelos disponibles en el proveedor
    if "--models" in sys.argv:
        listing = requests.get(f"{BASE_URL}/models",
                               headers={"Authorization": f"Bearer {API_KEY}"}, timeout=30)
        listing.raise_for_status()
        print("\n".join(sorted(item["id"] for item in listing.json()["data"])))
    else:
        answer = chat("Responde en una sola palabra.", "Di: listo")
        print(f"modelo: {answer['model']} · latencia: {answer['latency_s']} s · respuesta: {answer['text']}")
