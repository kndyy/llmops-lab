"""Trazas en Langfuse, además del JSONL local.

Sin LANGFUSE_PUBLIC_KEY y LANGFUSE_SECRET_KEY no hace nada: los tests y el pipeline
siguen corriendo sin red.
"""
import os
from contextlib import contextmanager

ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
ESCENARIO = os.getenv("ESCENARIO", "dev")  # replay.py lo cambia por el nombre de la semana


@contextmanager
def request(ticket: str, prompt: str):
    """Abre una traza por request. Entrega record(trace) para completarla."""
    if not ENABLED:
        yield lambda trace: None
        return

    from langfuse import get_client, propagate_attributes

    client = get_client()
    with propagate_attributes(trace_name="clasificar-ticket",
                              tags=[f"prompt:{prompt}", f"escenario:{ESCENARIO}"]):
        with client.start_as_current_observation(as_type="generation", name="llm",
                                                 input=ticket) as generation:
            def record(trace: dict) -> None:
                generation.update(
                    model=trace["model"],
                    output=trace["raw"],
                    usage_details={"input": trace["prompt_tokens"],
                                   "output": trace["completion_tokens"]},
                    metadata={"latency_s": trace["latency_s"], "error": trace["error"]},
                )
                # Los scores son lo que el dashboard puede agregar
                client.score_current_trace(name="contrato_valido", value=int(trace["valid"]),
                                           data_type="BOOLEAN")
                client.score_current_trace(name="categoria", value=trace["categoria"],
                                           data_type="CATEGORICAL")

            yield record


def flush() -> None:
    """Envía lo pendiente antes de que termine un script corto."""
    if ENABLED:
        from langfuse import get_client

        get_client().flush()


if __name__ == "__main__":
    # python -m src.tracing -> prueba de conexión
    if not ENABLED:
        print("Langfuse desactivado: faltan LANGFUSE_PUBLIC_KEY y LANGFUSE_SECRET_KEY")
    else:
        from langfuse import get_client

        print("Langfuse: conectado" if get_client().auth_check()
              else "Langfuse: credenciales o LANGFUSE_BASE_URL incorrectas")
