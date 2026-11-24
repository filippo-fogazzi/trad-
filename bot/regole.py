"""Legge regole.yaml: l'unico posto dove vivono i numeri del bot."""
from pathlib import Path

import yaml

RADICE = Path(__file__).resolve().parent.parent


def carica_regole(percorso: Path = RADICE / "regole.yaml") -> dict:
    regole = yaml.safe_load(percorso.read_text(encoding="utf-8"))
    if regole.get("modalita") != "carta":
        raise ValueError("Solo la modalità 'carta' esiste. I soldi veri non sono implementati.")
    return regole


def categoria(simbolo: str, regole: dict) -> str:
    for nome, simboli in regole["mercati"].items():
        if simbolo in simboli:
            return nome
    raise KeyError(f"{simbolo} non è in regole.yaml → mercati")
