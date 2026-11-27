"""TENDENZA: seguire la tendenza delle criptovalute grandi su candele giornaliere (SOLDI FINTI, solo test).

Anni di candele giornaliere gratuite da Binance: il verdetto arriva in pochi secondi, senza aspettare giorni.
Ogni strategia decide alla chiusura del giorno ed esegue all'apertura del giorno dopo (niente sbirciate nel futuro).
Costi: commissione 0,1% + 0,05% di slippage a ogni acquisto e a ogni vendita.

Promossa = su quella moneta guadagna e rende meglio di "compra e tieni" rispetto alla perdita massima
(rendimento annuo diviso perdita massima) sia nella prima sia nella seconda metà degli anni.

Uso: python -m bot.tendenza
Scrive: risultati/tendenza.md e risultati/tendenza.json
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from bot.dati import carica_candele
from bot.regole import RADICE

MONETE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
GIORNI = 3000
COSTO = (0.10 + 0.05) / 100   # per ogni acquisto e ogni vendita


# --- le strategie: per ogni giorno True = dentro, False = fuori (in contanti) ------------------------
def strategie(c: pd.DataFrame) -> dict[str, pd.Series]:
    chiusura, massimi, minimi = c["close"], c["high"], c["low"]
    s = {"Compra e tieni": pd.Series(True, index=c.index)}
    for n in (20, 50, 100, 200):
        s[f"Sopra la media di {n} giorni"] = chiusura > chiusura.rolling(n).mean()
    for veloce, lenta in ((10, 50), (20, 100), (50, 200)):
        s[f"Media {veloce} sopra media {lenta}"] = chiusura.rolling(veloce).mean() > chiusura.rolling(lenta).mean()
    for entrata, uscita in ((20, 10), (55, 20)):
        alto = massimi.shift(1).rolling(entrata).max()
        basso = minimi.shift(1).rolling(uscita).min()
        dentro, stato = [], False
        for chiude, a, b in zip(chiusura, alto, basso):
            if not stato and a == a and chiude > a:
                stato = True
            elif stato and b == b and chiude < b:
                stato = False
            dentro.append(stato)
        s[f"Rottura dei massimi di {entrata} giorni (esce sotto i minimi di {uscita})"] = pd.Series(dentro, index=c.index)
    return s


def simula(c: pd.DataFrame, dentro: pd.Series) -> pd.Series:
    """Capitale giorno per giorno partendo da 1. Decisione a fine giornata, esecuzione all'apertura dopo."""
    posizione = dentro.shift(1, fill_value=False).astype(bool)        # quello che si tiene durante il giorno
    rendimento_giorno = c["close"] / c["open"] - 1                      # dall'apertura (esecuzione) alla chiusura
    rendimento_notte = c["open"] / c["close"].shift(1) - 1              # dalla chiusura di ieri all'apertura di oggi
    tenuto_ieri = posizione.shift(1, fill_value=False)
    r = np.where(tenuto_ieri, rendimento_notte.fillna(0), 0.0) + np.where(posizione, rendimento_giorno, 0.0)
    cambi = (posizione != tenuto_ieri).astype(float) * COSTO
    return pd.Series(np.cumprod((1 + r) * (1 - cambi)), index=c.index)


def misura(capitale: pd.Series, date: pd.Series, dentro: pd.Series) -> dict:
    anni = max((date.iloc[-1] - date.iloc[0]).days / 365.25, 1e-9)
    finale = capitale.iloc[-1] / capitale.iloc[0]
    annuo = finale ** (1 / anni) - 1
    perdita_max = float((capitale / capitale.cummax() - 1).min())
    return {"rendimento_pct": round((finale - 1) * 100, 1), "annuo_pct": round(annuo * 100, 1),
            "perdita_max_pct": round(perdita_max * 100, 1),
            "rapporto": round(annuo / abs(perdita_max), 2) if perdita_max < 0 else 0.0,
            "operazioni": int((dentro.astype(int).diff().fillna(0) == 1).sum()),
            "tempo_dentro_pct": round(float(dentro.mean()) * 100)}


def valuta_moneta(simbolo: str) -> list[dict]:
    c, _ = carica_candele(simbolo, "1d", GIORNI)
    c = c.reset_index(drop=True)
    meta = len(c) // 2
    righe = []
    segnali = strategie(c)
    for nome, dentro in segnali.items():
        riga = {"moneta": simbolo.removesuffix("USDT"), "strategia": nome,
                "dal": str(c["apertura"].iloc[0].date()), "giorni": len(c)}
        riga.update(misura(simula(c, dentro), c["apertura"], dentro))
        for parte, (a, b) in {"prima": (0, meta), "seconda": (meta, len(c))}.items():
            pezzo = c.iloc[a:b].reset_index(drop=True)
            d = dentro.iloc[a:b].reset_index(drop=True)
            m = misura(simula(pezzo, d), pezzo["apertura"], d)
            riga[f"{parte}_annuo_pct"], riga[f"{parte}_rapporto"] = m["annuo_pct"], m["rapporto"]
        righe.append(riga)
    tieni = righe[0]
    for r in righe[1:]:
        r["promossa"] = all(r[f"{p}_annuo_pct"] > 0 and r[f"{p}_rapporto"] > tieni[f"{p}_rapporto"] for p in ("prima", "seconda"))
    tieni["promossa"] = False
    return righe


def rapporto(righe: list[dict]) -> str:
    adesso = datetime.now(timezone.utc)
    promosse = [r for r in righe if r["promossa"]]
    conta: dict[str, int] = {}
    for r in promosse:
        conta[r["strategia"]] = conta.get(r["strategia"], 0) + 1
    testa = ["| Moneta | Strategia | Rendimento totale | All'anno | Perdita massima | Annuo / perdita | Operazioni | Tempo dentro |",
             "|---|---|---|---|---|---|---|---|"]
    riga = lambda r: (f"| {r['moneta']} | {r['strategia']} | {r['rendimento_pct']:+,.0f}% | {r['annuo_pct']:+.1f}% | "
                      f"{r['perdita_max_pct']:.0f}% | {r['rapporto']} | {r['operazioni']} | {r['tempo_dentro_pct']}% |")
    out = [f"# Tendenza sulle criptovalute grandi — {adesso:%d/%m/%Y %H:%M} UTC", "",
           "**Soldi finti, solo test.** Candele giornaliere Binance, decisione a fine giornata ed esecuzione all'apertura dopo, "
           "commissione 0,1% + slippage 0,05% a ogni compravendita.", "",
           "Promossa = guadagna e rende meglio di *Compra e tieni* rispetto alla perdita massima, "
           "sia nella prima sia nella seconda metà degli anni.", "",
           f"## Promosse ({len(promosse)})", ""]
    if conta:
        out += [f"- **{s}**: promossa su {n} monete su {len(MONETE)}" for s, n in sorted(conta.items(), key=lambda x: -x[1])] + [""]
        out += testa + [riga(r) for r in promosse] + [""]
    else:
        out += ["Nessuna.", ""]
    out += ["## Tutti i risultati", ""] + testa + [riga(r) for r in righe] + [""]
    return "\n".join(out)


def main() -> None:
    righe = [r for s in MONETE for r in valuta_moneta(s)]
    cartella = RADICE / "risultati"
    (cartella / "tendenza.json").write_text(json.dumps(righe, ensure_ascii=False, indent=1), encoding="utf-8")
    (cartella / "tendenza.md").write_text(rapporto(righe), encoding="utf-8")
    print(f"{sum(r['promossa'] for r in righe)} promosse su {len(righe)} · risultati/tendenza.md")


if __name__ == "__main__":
    main()
