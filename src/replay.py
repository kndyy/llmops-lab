"""Simula tráfico de producción: pasa un archivo de tickets por la aplicación y
deja una traza por request. Uso: python -m src.replay <tickets.jsonl> <trazas.jsonl>
"""
import json
import sys
from pathlib import Path

from src import app, tracing


def main() -> None:
    tickets, traces = Path(sys.argv[1]), Path(sys.argv[2])
    tracing.ESCENARIO = tickets.stem.removeprefix("tickets_")  # tag de la semana en Langfuse
    traces.unlink(missing_ok=True)
    lines = [line for line in tickets.read_text(encoding="utf-8").splitlines() if line.strip()]
    for done, line in enumerate(lines, start=1):
        app.classify(json.loads(line)["ticket"], trace_file=traces)
        app.progress(done, len(lines))
    tracing.flush()
    print(f"{len(lines)} requests · trazas en {traces}")


if __name__ == "__main__":
    main()
