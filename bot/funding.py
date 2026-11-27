"""FUNDING: incassare il funding dei contratti perpetui senza scommettere sul prezzo (SOLDI FINTI, solo test).

Come funziona: con metà del capitale si compra la moneta, con l'altra metà (come garanzia) si apre una vendita
allo scoperto della stessa quantità sul contratto perpetuo. Il prezzo si annulla: se sale, si guadagna sulla
moneta e si perde sul contratto, e viceversa. Ogni 8 ore chi è "lungo" sul perpetuo paga a chi è "corto" il
funding (quando è positivo, cioè quasi sempre nei mercati in salita): quello è il guadagno.

Ipotesi semplici e dichiarate: esposizione = metà del capitale; costi di entrata e di uscita 0,15% sulla moneta
e 0,10% sul contratto; nessun rischio di liquidazione (la garanzia viene ribilanciata); differenza di prezzo
tra moneta e contratto ignorata.

Promossa = rende più del 3% l'anno sia nella prima sia nella seconda metà degli anni.

Uso: python -m bot.funding   (serve fapi.binance.com: gira su GitHub)
Scrive: risultati/funding.md e risultati/funding.json
"""
import json
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from bot.regole import RADICE

FONTE = "https://fapi.binance.com/fapi/v1/fundingRate"
MONETE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
ESPOSIZIONE = 0.5                 # quota del capitale coperta (l'altra metà è la garanzia del contratto)
COSTO_GIRO = (0.15 + 0.10) / 100  # entrare (o uscire) costa questo, sulla parte esposta
SOGLIA_ENTRATA = 0.0001           # "solo quando conviene": funding medio degli ultimi 7 giorni sopra 0,01% ogni 8 ore
PERIODI_MEDIA = 21                # 7 giorni di funding (3 al giorno)
ANNUO_MINIMO_PCT = 3.0


def scarica(simbolo: str) -> pd.DataFrame:
    righe, inizio = [], 0
    while True:
        r = requests.get(FONTE, params={"symbol": simbolo, "startTime": inizio, "limit": 1000}, timeout=30)
        r.raise_for_status()
        blocco = r.json()
        if not blocco:
            break
        righe += blocco
        inizio = blocco[-1]["fundingTime"] + 1
        if len(blocco) < 1000:
            break
        time.sleep(0.3)
    d = pd.DataFrame({"quando": pd.to_datetime([x["fundingTime"] for x in righe], unit="ms", utc=True),
                      "tasso": [float(x["fundingRate"]) for x in righe]})
    return d.drop_duplicates("quando").reset_index(drop=True)


def simula(f: pd.DataFrame, sempre: bool) -> pd.Series:
    """Capitale dopo ogni pagamento di funding, partendo da 1."""
    media = f["tasso"].rolling(PERIODI_MEDIA).mean().shift(1)   # solo funding già pagati
    capitale, dentro, valori = 1.0, False, []
    for tasso, m in zip(f["tasso"], media):
        vuole = True if sempre else (m == m and (m > SOGLIA_ENTRATA or (dentro and m > 0)))
        if vuole != dentro:
            capitale *= 1 - COSTO_GIRO * ESPOSIZIONE
            dentro = vuole
        if dentro:
            capitale *= 1 + tasso * ESPOSIZIONE
        valori.append(capitale)
    if dentro:
        valori[-1] *= 1 - COSTO_GIRO * ESPOSIZIONE   # uscita finale
    return pd.Series(valori, index=f.index)


def misura(capitale: pd.Series, quando: pd.Series) -> dict:
    anni = max((quando.iloc[-1] - quando.iloc[0]).days / 365.25, 1e-9)
    finale = capitale.iloc[-1]
    mensile = capitale.groupby(quando.dt.strftime("%Y-%m")).last().pct_change().dropna()
    return {"annuo_pct": round((finale ** (1 / anni) - 1) * 100, 1), "rendimento_pct": round((finale - 1) * 100, 1),
            "mese_peggiore_pct": round(float(mensile.min()) * 100, 2) if len(mensile) else 0.0,
            "mesi_in_perdita_pct": round(float((mensile < 0).mean()) * 100) if len(mensile) else 0}


def valuta(simbolo: str, f: pd.DataFrame) -> list[dict]:
    meta = len(f) // 2
    righe = []
    for nome, sempre in (("Sempre dentro", True), ("Solo quando il funding è alto", False)):
        riga = {"moneta": simbolo.removesuffix("USDT"), "strategia": nome, "dal": str(f["quando"].iloc[0].date()),
                "funding_medio_annuo_pct": round(f["tasso"].mean() * 3 * 365 * 100, 1)}
        riga.update(misura(simula(f, sempre), f["quando"]))
        for parte, pezzo in {"prima": f.iloc[:meta], "seconda": f.iloc[meta:]}.items():
            pezzo = pezzo.reset_index(drop=True)
            riga[f"{parte}_annuo_pct"] = misura(simula(pezzo, sempre), pezzo["quando"])["annuo_pct"]
        riga["promossa"] = riga["prima_annuo_pct"] > ANNUO_MINIMO_PCT and riga["seconda_annuo_pct"] > ANNUO_MINIMO_PCT
        righe.append(riga)
    return righe


def rapporto(righe: list[dict]) -> str:
    adesso = datetime.now(timezone.utc)
    testa = ["| Moneta | Strategia | Dal | All'anno | 1ª metà | 2ª metà | Mese peggiore | Mesi in perdita | Promossa |",
             "|---|---|---|---|---|---|---|---|---|"]
    riga = lambda r: (f"| {r['moneta']} | {r['strategia']} | {r['dal']} | {r['annuo_pct']:+.1f}% | {r['prima_annuo_pct']:+.1f}% | "
                      f"{r['seconda_annuo_pct']:+.1f}% | {r['mese_peggiore_pct']:+.2f}% | {r['mesi_in_perdita_pct']}% | "
                      f"{'sì' if r['promossa'] else 'no'} |")
    return "\n".join([
        f"# Funding dei contratti perpetui — {adesso:%d/%m/%Y %H:%M} UTC", "",
        "**Soldi finti, solo test.** Metà capitale nella moneta, metà come garanzia di una vendita allo scoperto uguale sul "
        "perpetuo Binance: il prezzo si annulla e si incassa il funding. Costi 0,25% a ogni entrata o uscita.", "",
        f"Promossa = più del {ANNUO_MINIMO_PCT:.0f}% l'anno sia nella prima sia nella seconda metà degli anni.", "",
        *testa, *[riga(r) for r in righe], "",
        "Rischi che il test non vede: il cambio (risultati in dollari), il fallimento dell'exchange, "
        "e brevi momenti in cui il prezzo del contratto si stacca da quello della moneta.", ""])


def main() -> None:
    righe = []
    for simbolo in MONETE:
        righe += valuta(simbolo, scarica(simbolo))
    cartella = RADICE / "risultati"
    (cartella / "funding.json").write_text(json.dumps(righe, ensure_ascii=False, indent=1), encoding="utf-8")
    (cartella / "funding.md").write_text(rapporto(righe), encoding="utf-8")
    print(f"{sum(r['promossa'] for r in righe)} promosse su {len(righe)} · risultati/funding.md")


if __name__ == "__main__":
    main()
