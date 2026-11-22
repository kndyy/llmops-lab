"""Monitoreo: compara las trazas de una semana con las de la semana de referencia.

En producción no hay respuesta esperada, así que se vigila lo que sí se puede medir:
la mezcla de categorías (PSI), las salidas fuera de contrato, la latencia y los tokens.
Sale con código 42 cuando hay que revisar el prompt y el golden set.
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ["precio", "competencia", "soporte", "producto", "otro"]


def load(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def summary(traces: list[dict]) -> dict:
    counts = Counter(trace["categoria"] for trace in traces)
    latencies = sorted(trace["latency_s"] for trace in traces)
    return {
        "requests": len(traces),
        "mezcla": {name: round(counts[name] / len(traces), 3) for name in CATEGORIES},
        "fuera_de_contrato": round(sum(not trace["valid"] for trace in traces) / len(traces), 3),
        "latencia_p95_s": latencies[min(len(latencies) - 1, int(round(0.95 * (len(latencies) - 1))))],
        "tokens_promedio": round(sum(trace["prompt_tokens"] + trace["completion_tokens"]
                                     for trace in traces) / len(traces), 1),
    }


def psi(reference: dict, current: dict) -> float:
    total = 0.0
    for name in CATEGORIES:
        ref, cur = max(reference[name], 0.01), max(current[name], 0.01)
        total += (cur - ref) * math.log(cur / ref)
    return round(total, 3)


def main() -> int:
    reference, current = summary(load(sys.argv[1])), summary(load(sys.argv[2]))
    limits = json.loads((ROOT / "gate" / "thresholds.json").read_text(encoding="utf-8"))["monitoreo"]
    checks = {
        "psi_categorias": (psi(reference["mezcla"], current["mezcla"]), limits["psi_categorias"]),
        "fuera_de_contrato": (current["fuera_de_contrato"], limits["fuera_de_contrato"]),
        "latencia_p95_s": (current["latencia_p95_s"], limits["latencia_p95_s"]),
        "tokens_vs_referencia": (round(current["tokens_promedio"] / reference["tokens_promedio"], 2),
                                 limits["tokens_vs_referencia"]),
    }
    alerts = [name for name, (value, limit) in checks.items() if value > limit]

    print(f"{'categoría':<14}{'referencia':>11}{'actual':>9}")
    for name in CATEGORIES:
        print(f"{name:<14}{reference['mezcla'][name]:>11}{current['mezcla'][name]:>9}")
    print(f"\n{'señal':<24}{'valor':>8}  {'límite':<10}resultado")
    for name, (value, limit) in checks.items():
        print(f"{name:<24}{value:>8}  {'<= ' + str(limit):<10}{'ALERTA' if name in alerts else 'OK'}")

    decision = "REVISAR" if alerts else "OK"
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "monitoring.json").write_text(json.dumps(
        {"decision": decision, "alertas": alerts, "referencia": reference, "actual": current,
         "senales": {name: value for name, (value, _) in checks.items()}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDECISIÓN: {decision}" + (f" · {', '.join(alerts)}" if alerts else ""))
    return 42 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
