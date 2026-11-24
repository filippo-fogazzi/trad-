"""REGISTRATORE: salva una "foto" di ogni memecoin nuova nel momento in cui la vede.

La foto contiene quello che il passato gratis non conserva: volumi, acquisti/vendite,
holder e controllo anti-truffa IN QUEL MOMENTO. Il Laboratorio meme poi scarica il prezzo
delle ore successive e prova qualsiasi strategia su queste foto, in pochi secondi.

Uso: python -m bot.notte.registro --minuti 340
Scrive: registro/<AAAA-MM-GG>-<etichetta>.jsonl (una riga per foto)
"""
import argparse
import json
import os
import time
import traceback
from datetime import datetime, timezone

from bot.notte.controlli import liquidita, prezzo
from bot.notte.fonti import Fonti
from bot.regole import RADICE

CARTELLA = RADICE / "registro"
LIQUIDITA_MIN = 5_000          # più bassa di ogni strategia, così il Laboratorio può provare filtri larghi
ETA_MAX_ORE = 6
FOTO_PER_TOKEN = 3             # la stessa moneta viene rifotografata fino a 3 volte...
MINUTI_TRA_FOTO = 5            # ...a distanza di almeno 5 minuti (serve per la crescita degli holder)
RUGCHECK_PER_GIRO = 25         # RugCheck è lento: al massimo 25 controlli per giro, prima i più scambiati


def coppia_ridotta(c: dict) -> dict:
    volume, tx, var = c.get("volume") or {}, (c.get("txns") or {}).get("m5") or {}, c.get("priceChange") or {}
    return {
        "dexId": c.get("dexId"), "pairAddress": c.get("pairAddress"), "url": c.get("url"),
        "pairCreatedAt": c.get("pairCreatedAt"), "priceUsd": c.get("priceUsd"),
        "liquidity": {"usd": liquidita(c)},
        "volume": {"m5": volume.get("m5"), "h1": volume.get("h1")},
        "txns": {"m5": {"buys": tx.get("buys"), "sells": tx.get("sells")}},
        "priceChange": {"m5": var.get("m5"), "h1": var.get("h1")},
        "baseToken": {"address": c["baseToken"]["address"], "symbol": c["baseToken"].get("symbol")},
    }


def rapporto_ridotto(r: dict) -> dict:
    """Solo i campi che usa controllo_truffe(), così una foto pesa poco."""
    holder = (r.get("topHolders") or [])[:15]
    noti = r.get("knownAccounts") or {}
    return {
        "mintAuthority": r.get("mintAuthority"), "freezeAuthority": r.get("freezeAuthority"), "rugged": r.get("rugged"),
        "transferFee": {"pct": (r.get("transferFee") or {}).get("pct")},
        "token": {"supply": (r.get("token") or {}).get("supply")}, "creatorBalance": r.get("creatorBalance"),
        "topHolders": [{"owner": h.get("owner"), "address": h.get("address"), "pct": h.get("pct")} for h in holder],
        "knownAccounts": {k: {"type": v.get("type")} for k, v in noti.items()
                          if any(k in (h.get("owner"), h.get("address")) for h in holder)},
        "markets": [{"lp": {"quoteUSD": (m.get("lp") or {}).get("quoteUSD"), "lpLockedPct": (m.get("lp") or {}).get("lpLockedPct")}}
                    for m in r.get("markets") or []],
        "graphInsidersDetected": r.get("graphInsidersDetected"),
        "risks": [{"name": x.get("name"), "level": x.get("level")} for x in r.get("risks") or []],
        "totalHolders": r.get("totalHolders"),
    }


class Registratore:
    def __init__(self, fonti: Fonti, file_uscita):
        self.fonti = fonti
        self.file = file_uscita
        self.foto: dict[str, list[int]] = {}   # token → istanti (ms) delle foto già fatte

    def giro(self, adesso_ms: int) -> int:
        coppie = self.fonti.coppie(self.fonti.token_recenti())
        candidati = []
        for token, c in coppie.items():
            eta_ore = (adesso_ms - (c.get("pairCreatedAt") or 0)) / 3_600_000
            fatte = self.foto.get(token, [])
            if (prezzo(c) is None or liquidita(c) < LIQUIDITA_MIN or eta_ore > ETA_MAX_ORE
                    or len(fatte) >= FOTO_PER_TOKEN or (fatte and adesso_ms - fatte[-1] < MINUTI_TRA_FOTO * 60_000)):
                continue
            candidati.append((float((c.get("volume") or {}).get("m5") or 0), token, c))
        scritte = 0
        for _, token, c in sorted(candidati, key=lambda x: -x[0])[:RUGCHECK_PER_GIRO]:
            try:
                rapporto = rapporto_ridotto(self.fonti.rapporto_rugcheck(token))
            except Exception:
                continue
            foto = {"ms": adesso_ms, "token": token, "n_foto": len(self.foto.get(token, [])) + 1,
                    "coppia": coppia_ridotta(c), "rugcheck": rapporto}
            self.file.write(json.dumps(foto, ensure_ascii=False) + "\n")
            self.file.flush()
            self.foto.setdefault(token, []).append(adesso_ms)
            scritte += 1
        return scritte


def main() -> None:
    argomenti = argparse.ArgumentParser(description="Registra foto delle memecoin nuove")
    argomenti.add_argument("--minuti", type=int, default=340)
    argomenti.add_argument("--etichetta", default=os.environ.get("GITHUB_RUN_ID", "locale"))
    a = argomenti.parse_args()
    CARTELLA.mkdir(exist_ok=True)
    inizio = datetime.now(timezone.utc)
    percorso = CARTELLA / f"{inizio:%Y-%m-%d-%H%M}-{a.etichetta}.jsonl"
    fine = time.time() + a.minuti * 60
    totale = 0
    with percorso.open("a", encoding="utf-8") as f:
        registratore = Registratore(Fonti(), f)
        while time.time() < fine:
            partenza = time.time()
            try:
                totale += registratore.giro(int(partenza * 1000))
            except Exception:
                traceback.print_exc()
            print(f"{datetime.now(timezone.utc):%H:%M:%S} foto salvate: {totale}", flush=True)
            time.sleep(max(5.0, 60 - (time.time() - partenza)))
    print(f"Fine: {totale} foto in {percorso}")


if __name__ == "__main__":
    main()
