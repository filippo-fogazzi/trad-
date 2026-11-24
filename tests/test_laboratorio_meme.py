import pytest

from bot.notte.laboratorio import simula, statistiche
from bot.regole import carica_regole

R = carica_regole()["notte_meme"]
T0 = 1_800_000_000  # secondi


def foto(prezzo=1.0, liquidita=100_000):
    return {"ms": T0 * 1000, "coppia": {"priceUsd": str(prezzo), "liquidity": {"usd": liquidita}}}


def candele(*righe):
    """righe = (open, high, low, close), una per minuto dopo l'ingresso"""
    return [[T0 + 60 * i, o, h, l, c, 1000] for i, (o, h, l, c) in enumerate(righe)]


def test_stop_perde_circa_12_percento_piu_costi():
    esito = simula(R, foto(), candele((1, 1.02, 0.8, 0.85)), puntata_usd=18)
    assert "stop" in esito["motivo"]
    assert -18 < esito["ritorno_pct"] < -12


def test_scala_2x_e_trailing_guadagna():
    esito = simula(R, foto(), candele((1, 1.1, 0.99, 1.05), (1.05, 2.2, 1.04, 2.1), (2.1, 3.0, 2.0, 2.9), (2.9, 2.9, 2.0, 2.1)), 18)
    assert "trailing" in esito["motivo"] and esito["ritorno_pct"] > 50


def test_tempo_scaduto():
    righe = [(1, 1.05, 0.97, 1.0)] * 30
    esito = simula(R, foto(), candele(*righe), 18)
    assert "tempo" in esito["motivo"] and esito["minuti"] == 25


def test_rug_perde_90_percento():
    esito = simula(R, foto(), candele((1, 1, 0.01, 0.01)), 18)
    assert "rug" in esito["motivo"] and esito["ritorno_pct"] < -89


def test_nessuno_scambio_conta_come_rug():
    assert simula(R, foto(), [], 18)["ritorno_pct"] < -89


def test_slippage_troppo_alto_non_compra():
    assert simula(R, foto(liquidita=500), candele((1, 1, 1, 1)), 18) is None


def test_statistiche_massimo_due_posizioni():
    ops = [{"ms": T0 * 1000 + i, "minuti": 30, "ritorno_pct": 10} for i in range(3)]
    s = statistiche(ops, R, 55)
    assert s["eseguite"] == 2 and s["n"] == 3
