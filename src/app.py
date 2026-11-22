"""La aplicación: clasifica un ticket de cliente y estima su riesgo de churn."""
import json
import re
import sys
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from src import llm, tracing

ROOT = Path(__file__).resolve().parents[1]


class Clasificacion(BaseModel):
    """Contrato de salida: lo que el resto del sistema puede asumir."""
    categoria: Literal["precio", "competencia", "soporte", "producto", "otro"]
    riesgo_churn: Literal["alto", "medio", "bajo"]
    resumen: str = Field(max_length=200)


FALLBACK = {"categoria": "otro", "riesgo_churn": "medio", "resumen": ""}


def progress(done: int, total: int) -> None:
    """Avance en la terminal: con un LLM real cada request espera varios segundos."""
    if sys.stderr.isatty():
        print(f"\r  request {done}/{total}", end="\n" if done == total else "", file=sys.stderr, flush=True)


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def load_prompt(name: str, version: str) -> str:
    return (ROOT / "prompts" / name / f"{version}.md").read_text(encoding="utf-8")


def parse(text: str) -> Clasificacion:
    """Valida la respuesta del modelo contra el contrato."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("la respuesta no contiene JSON")
    return Clasificacion.model_validate_json(match.group(0))


def classify(ticket: str, prompt_version: str | None = None, trace_file: Path | None = None) -> dict:
    config = load_config()
    version = prompt_version or config["prompt_version"]
    with tracing.request(ticket, f"{config['prompt']}/{version}") as record:
        answer = llm.chat(
            load_prompt(config["prompt"], version),
            ticket,
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
        )
        try:
            result = parse(answer["text"]).model_dump()
            valid, error = True, ""
        except (ValueError, ValidationError) as exc:
            # Una salida fuera de contrato nunca llega al resto del sistema
            result, valid, error = dict(FALLBACK), False, str(exc).splitlines()[0]

        trace = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "prompt": f"{config['prompt']}/{version}",
            "model": answer["model"],
            "ticket": ticket,
            "raw": answer["text"],
            "valid": valid,
            "error": error,
            "latency_s": answer["latency_s"],
            "prompt_tokens": answer["prompt_tokens"],
            "completion_tokens": answer["completion_tokens"],
            **result,
        }
        record(trace)  # la misma traza va a Langfuse si hay credenciales
    if trace_file:
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        with trace_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace, ensure_ascii=False) + "\n")
    return trace


if __name__ == "__main__":
    out = classify(" ".join(sys.argv[1:]) or "Me subieron la comisión, quiero cerrar mi cuenta")
    fields = ["categoria", "riesgo_churn", "resumen", "valid", "model"]
    if not out["valid"]:
        fields += ["error", "raw"]  # por qué se rechazó y qué respondió el modelo
    print(json.dumps({k: out[k] for k in fields}, ensure_ascii=False, indent=2))
