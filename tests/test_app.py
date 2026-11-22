"""Tests sin red: usan el simulador, así corren en cada push sin gastar tokens."""
import json

import pytest

from src import app, llm, tracing


@pytest.fixture(autouse=True)
def sin_api(monkeypatch):
    monkeypatch.setattr(llm, "API_KEY", "")
    monkeypatch.setattr(tracing, "ENABLED", False)


def test_contrato_acepta_una_salida_valida():
    out = app.parse('{"categoria": "precio", "riesgo_churn": "alto", "resumen": "Cobro indebido"}')
    assert out.categoria == "precio"


@pytest.mark.parametrize("texto", [
    "El ticket trata de precios.",                                             # prosa
    '{"categoria": "costos", "riesgo_churn": "alto", "resumen": "x"}',         # etiqueta inventada
    '{"categoria": "precio", "riesgo_churn": "altísimo", "resumen": "x"}',     # valor fuera del enum
    '{"categoria": "precio"}',                                                 # faltan campos
])
def test_contrato_rechaza_salidas_invalidas(texto):
    with pytest.raises(ValueError):
        app.parse(texto)


def test_salida_invalida_no_rompe_la_app(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: {
        "text": "no sé", "prompt_tokens": 1, "completion_tokens": 1, "latency_s": 0.0, "model": "x"})
    out = app.classify("cualquier cosa")
    assert out["valid"] is False and out["categoria"] == "otro" and out["riesgo_churn"] == "medio"


def test_cada_request_deja_una_traza(tmp_path):
    trazas = tmp_path / "trazas.jsonl"
    app.classify("Me cobraron una comisión", prompt_version="v2", trace_file=trazas)
    traza = json.loads(trazas.read_text(encoding="utf-8"))
    assert {"prompt", "model", "valid", "latency_s", "prompt_tokens", "categoria"} <= traza.keys()
    assert traza["prompt"] == "clasificador/v2"


def test_golden_set_bien_formado():
    lineas = (app.ROOT / "data" / "golden.jsonl").read_text(encoding="utf-8").splitlines()
    casos = [json.loads(linea) for linea in lineas if linea.strip()]
    assert len({caso["id"] for caso in casos}) == len(casos) >= 20
    for caso in casos:
        app.Clasificacion(categoria=caso["categoria"], riesgo_churn=caso["riesgo_churn"], resumen="")
    assert sum(caso["tipo"] == "inyeccion" for caso in casos) >= 4
