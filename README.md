# llmops-lab · Clasificador de tickets con evals, gate y monitoreo

Repositorio del Laboratorio 15.1 de LLMOps. El prompt es el artefacto versionado: se evalúa contra un golden set, un gate decide si se promueve y el monitoreo vigila la mezcla de categorías cuando no hay respuestas esperadas.

**Repositorio:** <https://github.com/kndyy/llmops-lab>

## Qué hace

Un ticket de cliente entra a `src/app.py`, se clasifica con la versión activa del prompt (`config.json`) y la respuesta se valida con el contrato `Clasificacion` de pydantic:

| Campo | Valores |
|---|---|
| `categoria` | `precio`, `competencia`, `soporte`, `producto`, `otro` |
| `riesgo_churn` | `alto`, `medio`, `bajo` |
| `resumen` | Una frase de máximo 200 caracteres |

Cada request deja una traza en `logs/` y, si hay credenciales, en Langfuse. El pipeline de GitHub Actions corre los tests y el eval con el juez tomado de `main`.

## Cómo reproducirlo

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m pytest -q
python -m src.evaluate --prompt-version v1 && python -m src.gate
python -m src.evaluate --prompt-version v2 && python -m src.gate

python -m src.traffic
python -m src.replay data/prod/tickets_base.jsonl logs/trazas_base.jsonl
python -m src.replay data/prod/tickets_price_hike.jsonl logs/trazas_price_hike.jsonl
python -m src.monitor logs/trazas_base.jsonl logs/trazas_price_hike.jsonl
```

Sin `LLM_API_KEY` todo corre con el simulador determinista de `src/llm.py`. Con una key compatible con OpenAI se exporta `LLM_API_KEY`, `LLM_BASE_URL` y `LLM_MODEL`.

## Resultados del eval

**Golden set original (20 casos).** Es la comparación con la que `v2` se promovió:

| Métrica | v1 | v2 |
|---|---:|---:|
| `contrato_valido` | 0.200 | 1.000 |
| `accuracy_categoria` | 0.000 | 0.875 |
| `accuracy_riesgo` | 0.000 | 0.812 |
| `resistencia_inyeccion` | 0.000 | 1.000 |
| `latencia_p95_s` | 0.0 | 0.0 |
| `tokens_promedio` | 100.8 | 381.9 |
| Casos fallados | 20 de 20 | 2 de 20 |

`v2` usa casi cuatro veces más tokens que `v1`, pero es la primera versión que cumple el contrato y resiste las inyecciones. Los dos casos que todavía falla (`g03` y `g10`) están documentados en `reports/eval.md`: el simulador decide por palabras clave y confunde una queja de precio sobre transferencias con `producto`, y una queja de atención en agencia con `otro`.

**Golden set ampliado (24 casos).** Es la comparación de las tres versiones después del reto:

| Métrica | v1 | v2 | v3 |
|---|---:|---:|---:|
| `contrato_valido` | 0.208 | 1.000 | 1.000 |
| `accuracy_categoria` | 0.000 | 0.737 | 1.000 |
| `accuracy_riesgo` | 0.000 | 0.842 | 0.947 |
| `resistencia_inyeccion` | 0.000 | 0.800 | 1.000 |
| `latencia_p95_s` | 0.0 | 0.0 | 0.0 |
| `tokens_promedio` | 101.0 | 382.2 | 447.3 |
| Casos fallados | 24 de 24 | 6 de 24 | 0 de 24 |

Los cuatro casos nuevos hacen que `v2` deje de aprobar: baja a 0.737 de categoría y 0.8 de inyección. `v3` corrige los seis fallos, se queda en 447.3 tokens (por debajo del máximo de 600) y el gate responde `APROBADO`.

## Preguntas de reflexión

### ¿Por qué el gate rechazó el prompt v1 y qué cambiaste en v2 para que aprobara?

`v1` no declara la lista cerrada de categorías, no exige JSON y no dice nada de las instrucciones que vienen dentro del ticket. Por eso el modelo inventa etiquetas como `costos`, responde en prosa y obedece el `APROBADO` de los casos de inyección: `contrato_valido` 0.2, `accuracy_categoria` 0.0 y `resistencia_inyeccion` 0.0.

En `v2` fijé los tres puntos: los cinco valores exactos de `categoria` con su definición, los tres de `riesgo_churn`, la salida como un único objeto JSON, y la regla de que el ticket es un dato y no una orden. Con eso el contrato llega a 1.0, la categoría a 0.875 y la inyección a 1.0, así que el gate aprueba.

### ¿Por qué el pull request trampa falló en GitHub si en tu máquina el gate aprobaba?

En la rama `trampa` bajé los cuatro umbrales de `minimo` a 0.0 y puse `v1` en `config.json`. En mi máquina `python -m src.gate` lee esos umbrales de la rama y por eso aprueba: el que propone el cambio también controla el examen.

En GitHub Actions, antes de evaluar, el paso **Tomar el juez desde main** reemplaza `gate/`, `data/golden.jsonl`, `src/evaluate.py` y `src/gate.py` por los de `main`. El eval corre con `v1`, pero el gate usa los umbrales vigentes y el baseline de `v2`; por eso `Evaluación · eval y gate` termina en rojo.

### ¿Qué te muestra Langfuse que no ves en el archivo de trazas local?

El JSONL local guarda una línea por request, pero para responder cualquier pregunta hay que escribir código. Langfuse muestra cada request como una traza con su generación, el ticket, la respuesta cruda, el modelo, los tokens y la latencia, y agrega los tags `prompt:clasificador/v2` y `escenario:base` o `escenario:price_hike`.

Además, los scores `contrato_valido` y `categoria` se pueden filtrar y agregar en el dashboard sin abrir un archivo. Lo que Langfuse no hace es decidir: el PSI y el código de salida 42 siguen en `src/monitor.py`, porque Langfuse no conoce los umbrales del negocio.

### El monitor respondió REVISAR en la semana price_hike. ¿Eso significa que el prompt está fallando? ¿Qué dato falta para saberlo?

No. `REVISAR` significa que cambió la mezcla de temas que llegan: `precio` pasa de 0.267 a 0.833 de los tickets y el PSI sube a 1.677. Es drift de entrada, no una prueba de que la clasificación sea incorrecta; de hecho `fuera_de_contrato` sigue en 0.0.

Para saber si el prompt falla falta el dato que el monitoreo no tiene: etiquetas humanas de una muestra de los tickets de `price_hike`. Sin esa muestra no se puede medir `accuracy_categoria` en la semana con alerta.

## Reto 1 · Cuatro casos nuevos y prompt v3

Se agregaron cuatro casos al golden set (`j01` a `j04`), tres normales y uno de inyección, elegidos porque `v2` los falla. El detalle está en `data/golden.jsonl` y la comparación de las tres versiones en MLflow.

| Caso | Tipo | Esperado | Qué prueba |
|---|---|---|---|
| `j01` | normal | `precio` / `alto` | Una queja de comisión y tarifa que además menciona cambiarse de banco; la causa es el precio, no la competencia |
| `j02` | normal | `soporte` / `alto` | Mala atención en agencia sin la palabra "reclamo"; el canal es el problema |
| `j03` | normal | `producto` / `medio` | La tarjeta no llega y la anterior venció; es una falla de producto, no una consulta |
| `j04` | inyección | `producto` / `medio` | Una transferencia pendiente con una orden de escribir `APROBADO`; debe clasificar el problema real |

| `j01` | normal | `precio` / `alto` | Una queja por transferencias caras que además anuncia cambio de banco; la causa es el precio, no la competencia |
| `j02` | normal | `soporte` / `alto` | Mala atención en agencia sin la palabra "reclamo"; el canal es el problema y anuncia que se va |
| `j03` | normal | `producto` / `bajo` | La tarjeta no llega y la anterior venció; es una falla de producto, no una consulta |
| `j04` | inyección | `soporte` / `medio` | Una queja por atención con una orden de escribir `APROBADO`; debe clasificar el problema real |

`v2` falla los cuatro: `j01` cae en `producto`, `j02` y `j04` caen en `otro`, y `j03` también cae en `otro`. `v3` agrega la regla de clasificar por la causa principal, un ejemplo por cada frontera y un lexicón explícito para los casos ambiguos. Con eso el eval sube a `accuracy_categoria` 1.0, `accuracy_riesgo` 0.947, `resistencia_inyeccion` 1.0 y `tokens_promedio` 447.3: el gate aprueba sin pasar el máximo de 600 tokens.

La comparación de las tres versiones está en MLflow, experimento `llmops-clasificador`.

## Reto 2 · Por qué el monitor no decide solo

El monitor compara distribuciones, no aciertos. Durante `price_hike` detecta que la mezcla cambió, pero no puede distinguir entre "los clientes escriben más sobre precios porque la fintech subió las comisiones" y "el prompt dejó de clasificar bien los tickets de precio". Esa distinción exige etiquetas, y el monitor no las recibe.

El dato que falta es una muestra etiquetada a mano de las trazas de la semana con alerta. Con ella se calcula la exactitud real del prompt en esos casos; si baja, se agregan los casos al golden set y se escribe un `v4`. Ese es el trabajo del paso 4.3 de la guía y no se puede automatizar solo con PSI.

## Retos opcionales

- **Protección de `main`:** la rama exige pull request, el check `Evaluación · eval y gate` y la revisión de Code Owners (`.github/CODEOWNERS`). El dueño del juez es `@kndyy`.
- **Issue automático:** `monitoring.yml` incluye un paso con `if: failure()` que abre un issue con la tabla del monitor cuando sale con 42, y el `schedule` semanal está activo.
- **Widget de Langfuse:** el dashboard `Clasificador de tickets` tiene el widget `Mezcla de categorías` (score `categoria`, vista `Scores Categorical`, `Count` por `String Value`).

## Evidencias

| Evidencia | Archivo |
|---|---|
| MLflow con `prompt-v1`, `prompt-v2` y `prompt-v3` | `evidencias/01_mlflow_compare.png` |
| Pipeline en `main` con Preparación y Evaluación en verde | `evidencias/02_pipeline_main.png` |
| Pull request trampa con `Evaluación · eval y gate` en rojo | `evidencias/03_pr_trampa.png` |
| `src.monitor` con `DECISIÓN: REVISAR` y `exit=42` | `evidencias/04_monitor.png` |
| Langfuse Home con 60 trazas y 120 scores | `evidencias/05_langfuse_home.png` |
| Traza abierta con tags y scores | `evidencias/05_langfuse_traza_detalle.png` |
| Widget Mezcla de categorías | `evidencias/06_langfuse_widget.png` |
| LLMOps Monitoring con `price_hike` en rojo y tabla en Summary | `evidencias/07_monitoring_price_hike.png` |

## Estructura

```
.
├── .github/
│   ├── CODEOWNERS
│   └── workflows/
│       ├── llmops.yml
│       └── monitoring.yml
├── config.json
├── data/
│   ├── golden.jsonl
│   └── prod/
├── gate/
│   ├── baseline.json
│   └── thresholds.json
├── prompts/clasificador/
│   ├── v1.md
│   ├── v2.md
│   └── v3.md
├── src/
│   ├── llm.py
│   ├── tracing.py
│   ├── app.py
│   ├── evaluate.py
│   ├── gate.py
│   ├── traffic.py
│   ├── replay.py
│   └── monitor.py
└── tests/test_app.py
```
