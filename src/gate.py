"""El juez: decide si una versión del prompt puede llegar a producción.

Lee reports/eval.json y lo compara con los umbrales y con el baseline. Quien propone
el cambio (una persona o un agente) no debe poder editar este archivo ni gate/.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    metrics = json.loads((ROOT / "reports" / "eval.json").read_text(encoding="utf-8"))["metrics"]
    rules = json.loads((ROOT / "gate" / "thresholds.json").read_text(encoding="utf-8"))
    baseline = json.loads((ROOT / "gate" / "baseline.json").read_text(encoding="utf-8"))

    if "--write-baseline" in sys.argv:
        (ROOT / "gate" / "baseline.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        print("gate/baseline.json actualizado con las métricas de reports/eval.json")
        return 0

    failures = []
    print(f"{'métrica':<24}{'valor':>8}  {'regla':<22}resultado")
    for name, limit in rules["minimo"].items():
        ok = metrics[name] >= limit
        print(f"{name:<24}{metrics[name]:>8}  {'>= ' + str(limit):<22}{'OK' if ok else 'FALLA'}")
        failures += [] if ok else [name]
    for name, limit in rules["maximo"].items():
        ok = metrics[name] <= limit
        print(f"{name:<24}{metrics[name]:>8}  {'<= ' + str(limit):<22}{'OK' if ok else 'FALLA'}")
        failures += [] if ok else [name]
    for name in rules["no_empeorar"]:
        floor = max(0, round(baseline[name] - rules["tolerancia"], 3))
        ok = metrics[name] >= floor
        print(f"{name:<24}{metrics[name]:>8}  {'>= baseline ' + str(floor):<22}{'OK' if ok else 'FALLA'}")
        failures += [] if ok else [f"{name} vs baseline"]

    if failures:
        print(f"\nGATE: RECHAZADO · {', '.join(failures)}")
        return 1
    print("\nGATE: APROBADO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
