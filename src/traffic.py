"""Genera los tickets de dos semanas de producción (sin respuesta esperada).

  base        semana normal: la mezcla de temas con la que se diseñó el prompt
  price_hike  la fintech sube sus comisiones: casi todos escriben por el precio
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHRASES = {
    "precio": ["Me cobraron una comisión que no reconozco.", "Subieron la tarifa de mi tarjeta sin avisar.",
               "El mantenimiento de la cuenta está muy caro.", "¿Por qué me cobran por retirar efectivo?"],
    "competencia": ["Otro banco me ofrece una tasa mejor.", "En la competencia no cobran por esto.",
                    "Mis amigos usan otra billetera y les va mejor."],
    "soporte": ["Nadie responde mi reclamo.", "Llevo días esperando que me devuelvan la llamada.",
                "El call center me dejó en espera una hora."],
    "producto": ["La app se cae al iniciar sesión.", "Me sale error al pagar con QR.",
                 "La transferencia quedó pendiente desde ayer."],
    "otro": ["¿Cómo cambio mi número de celular?", "Necesito mi estado de cuenta de marzo.",
             "¿Tienen agencia en Arequipa?"],
}
ENDINGS = ["", "", " Espero una solución.", " Si no lo arreglan voy a cerrar mi cuenta.", " Gracias."]
MIX = {
    "base": {"precio": 6, "competencia": 5, "soporte": 7, "producto": 8, "otro": 4},
    "price_hike": {"precio": 20, "competencia": 5, "soporte": 2, "producto": 2, "otro": 1},
}


def main() -> None:
    out = ROOT / "data" / "prod"
    out.mkdir(parents=True, exist_ok=True)
    for scenario, mix in MIX.items():
        rng = random.Random(14)
        tickets = [rng.choice(PHRASES[name]) + rng.choice(ENDINGS) for name, n in mix.items() for _ in range(n)]
        if scenario == "price_hike":
            tickets = [t + " Con el aumento de comisiones de este mes ya no me conviene seguir aquí."
                       if i % 2 == 0 else t for i, t in enumerate(tickets)]
        rng.shuffle(tickets)
        path = out / f"tickets_{scenario}.jsonl"
        path.write_text("".join(json.dumps({"ticket": t}, ensure_ascii=False) + "\n" for t in tickets),
                        encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {len(tickets)} tickets")


if __name__ == "__main__":
    sys.exit(main())
