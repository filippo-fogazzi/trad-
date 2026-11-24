"""Tre strategie classiche, con parametri fissi da manuale.

I parametri NON sono ottimizzati sui dati: cercare i numeri "migliori" sul passato
produce strategie che sembrano ottime e poi falliscono. Qui si testa la versione standard.

Ogni strategia guarda solo candele GIÀ CHIUSE e dice: entra / esci. Il Laboratorio
esegue l'ordine all'apertura della candela successiva, come succederebbe davvero.
Solo acquisti (niente vendite allo scoperto): su Binance spot si guadagna solo se il prezzo sale.
"""
from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class Strategia:
    nome: str
    spiegazione: str
    calcola: Callable[[pd.DataFrame], pd.DataFrame]
    stop_atr: float = 2.0          # lo stop sta 2 "movimenti medi" sotto il prezzo di ingresso
    max_candele: int | None = None  # uscita forzata dopo N candele (None = nessun limite)


def ema(serie: pd.Series, periodi: int) -> pd.Series:
    return serie.ewm(span=periodi, adjust=False).mean()


def atr(c: pd.DataFrame, periodi: int = 14) -> pd.Series:
    """Average True Range: quanto si muove il prezzo in media in una candela."""
    chiusura_prec = c["close"].shift()
    escursione = pd.concat(
        [c["high"] - c["low"], (c["high"] - chiusura_prec).abs(), (c["low"] - chiusura_prec).abs()], axis=1
    ).max(axis=1)
    return escursione.ewm(alpha=1 / periodi, adjust=False).mean()


def rsi(serie: pd.Series, periodi: int = 14) -> pd.Series:
    delta = serie.diff()
    guadagni = delta.clip(lower=0).ewm(alpha=1 / periodi, adjust=False).mean()
    perdite = (-delta.clip(upper=0)).ewm(alpha=1 / periodi, adjust=False).mean()
    return 100 - 100 / (1 + guadagni / perdite)


def _trend(c: pd.DataFrame) -> pd.DataFrame:
    veloce, lenta = ema(c["close"], 20), ema(c["close"], 50)
    sopra = veloce > lenta
    return pd.DataFrame({"entra": sopra & ~sopra.shift(fill_value=True), "esci": ~sopra, "atr": atr(c)})


def _breakout(c: pd.DataFrame) -> pd.DataFrame:
    massimo_20 = c["high"].rolling(20).max().shift()
    minimo_10 = c["low"].rolling(10).min().shift()
    return pd.DataFrame({"entra": c["close"] > massimo_20, "esci": c["close"] < minimo_10, "atr": atr(c)})


def _rimbalzo(c: pd.DataFrame) -> pd.DataFrame:
    forza = rsi(c["close"])
    in_salita = c["close"] > ema(c["close"], 200)
    return pd.DataFrame({"entra": (forza < 30) & in_salita, "esci": forza > 55, "atr": atr(c)})


STRATEGIE = [
    Strategia(
        "trend",
        "Segue la tendenza: compra quando la media veloce (20) supera la lenta (50), vende quando torna sotto.",
        _trend,
    ),
    Strategia(
        "breakout",
        "Rottura: compra quando il prezzo chiude sopra il massimo delle ultime 20 candele, vende sotto il minimo delle ultime 10.",
        _breakout,
    ),
    Strategia(
        "rimbalzo",
        "Ritorno alla media: compra quando l'RSI scende sotto 30 in un mercato che sale (sopra la media 200), vende quando l'RSI risale sopra 55.",
        _rimbalzo,
        max_candele=48,
    ),
]
