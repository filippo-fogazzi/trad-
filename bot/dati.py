"""Candele reali da Binance (dati pubblici, nessuna chiave), salvate con fonte e orario."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from bot.regole import RADICE

FONTE = "https://data-api.binance.vision/api/v3/klines"
CARTELLA = RADICE / "dati"
MS_PER_INTERVALLO = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "1d": 86_400_000}
ORE_VALIDITA_CACHE = 12


def carica_candele(simbolo: str, intervallo: str, giorni: int) -> tuple[pd.DataFrame, dict]:
    """Ritorna (candele, metadati). Usa la copia locale se è recente e copre il periodo."""
    csv, meta_file = _percorsi(simbolo, intervallo)
    if csv.exists() and meta_file.exists():
        meta = json.loads(meta_file.read_text())
        eta_ore = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["scaricato_il"])).total_seconds() / 3600
        if eta_ore < ORE_VALIDITA_CACHE and meta["giorni"] >= giorni:
            candele = pd.read_csv(csv, parse_dates=["apertura"])
            return _ultimi_giorni(candele, giorni), meta
    candele = scarica(simbolo, intervallo, giorni)
    meta = {
        "fonte": FONTE,
        "simbolo": simbolo,
        "intervallo": intervallo,
        "giorni": giorni,
        "scaricato_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prima_candela": str(candele["apertura"].iloc[0]),
        "ultima_candela": str(candele["apertura"].iloc[-1]),
        "numero_candele": len(candele),
    }
    CARTELLA.mkdir(exist_ok=True)
    candele.to_csv(csv, index=False)
    meta_file.write_text(json.dumps(meta, indent=2))
    return candele, meta


def scarica(simbolo: str, intervallo: str, giorni: int) -> pd.DataFrame:
    passo = MS_PER_INTERVALLO[intervallo]
    adesso_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cursore = adesso_ms - giorni * 86_400_000
    righe: list[list] = []
    while cursore < adesso_ms:
        risposta = requests.get(
            FONTE,
            params={"symbol": simbolo, "interval": intervallo, "startTime": cursore, "limit": 1000},
            timeout=30,
        )
        risposta.raise_for_status()
        blocco = risposta.json()
        if not blocco:
            break
        righe.extend(blocco)
        cursore = blocco[-1][0] + passo
    if not righe:
        raise RuntimeError(f"Binance non ha restituito dati per {simbolo} {intervallo}")
    chiuse = [r for r in righe if r[6] < adesso_ms]  # scarta la candela ancora aperta
    candele = pd.DataFrame(
        {
            "apertura": pd.to_datetime([r[0] for r in chiuse], unit="ms", utc=True),
            "open": [float(r[1]) for r in chiuse],
            "high": [float(r[2]) for r in chiuse],
            "low": [float(r[3]) for r in chiuse],
            "close": [float(r[4]) for r in chiuse],
            "volume_euro": [float(r[7]) for r in chiuse],
        }
    )
    return candele.drop_duplicates("apertura").reset_index(drop=True)


def _percorsi(simbolo: str, intervallo: str) -> tuple[Path, Path]:
    base = CARTELLA / f"{simbolo}_{intervallo}"
    return base.with_suffix(".csv"), base.with_suffix(".json")


def _ultimi_giorni(candele: pd.DataFrame, giorni: int) -> pd.DataFrame:
    inizio = candele["apertura"].iloc[-1] - pd.Timedelta(days=giorni)
    return candele[candele["apertura"] > inizio].reset_index(drop=True)
