"""LABORATORIO MEME: prova molte strategie sulle foto salvate dal Registratore.

Per ogni foto scarica le candele al minuto delle 2,5 ore successive (GeckoTerminal, gratis)
e simula: filtri, controllo anti-truffa, segnali, poi uscite (-stop, 2x/4x, trailing,
tempo massimo) con commissioni e slippage stimati.

Uso: python -m bot.notte.laboratorio
     python -m bot.notte.laboratorio --solo-candele --parte 0 --parti 4   (solo prezzi, una fetta)
Scrive: risultati/laboratorio_meme.md e risultati/laboratorio_meme.json
"""
import argparse
import itertools
import json
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import requests

from bot.notte.__main__ import unisci
from bot.notte.controlli import controllo_truffe, insegue, segnali, universo
from bot.notte.fonti import GECKOTERMINAL
from bot.notte.registro import CARTELLA as CARTELLA_REGISTRO
from bot.regole import RADICE, carica_regole

CARTELLA_CANDELE = RADICE / "registro" / "candele"  # salvate nel repository: ogni token si scarica una volta sola
FINESTRA_MINUTI = 150
PAUSA_GECKO = 2.2  # circa 27 richieste al minuto, sotto il limite gratuito di 30


# --- dati -------------------------------------------------------------------

def carica_foto() -> list[dict]:
    foto = []
    for file in sorted(CARTELLA_REGISTRO.glob("*.jsonl")):
        for riga in file.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                foto.append(json.loads(riga))
    return sorted(foto, key=lambda f: f["ms"])


def scarica_candele(foto: list[dict], adesso_ms: int, max_minuti: float = 55,
                    parte: int = 0, parti: int = 1) -> dict[str, list]:
    """Una richiesta per token, che copre tutte le sue foto più 150 minuti. Usa una copia locale se c'è.
    Dopo max_minuti smette di scaricare: i token mancanti verranno presi al giro successivo.
    Con parti > 1 scarica solo la sua fetta di token, così più macchine (con indirizzi diversi,
    quindi limiti di GeckoTerminal separati) lavorano in parallelo."""
    scadenza = time.time() + max_minuti * 60
    CARTELLA_CANDELE.mkdir(parents=True, exist_ok=True)
    per_token: dict[str, list[dict]] = {}
    for f in foto:
        per_token.setdefault(f["token"], []).append(f)
    http = requests.Session()
    http.headers.update({"Accept": "application/json", "User-Agent": "trad-paper-bot"})
    candele: dict[str, list] = {}
    for token, sue in per_token.items():
        if zlib.crc32(token.encode()) % parti != parte:
            continue
        ultima = max(f["ms"] for f in sue)
        if adesso_ms < ultima + FINESTRA_MINUTI * 60_000:
            continue  # il futuro di questa foto non è ancora successo
        pool = sue[0]["coppia"].get("pairAddress")
        if not pool:
            continue
        cache = CARTELLA_CANDELE / f"{pool}_{ultima}.json"
        if cache.exists():
            candele[token] = json.loads(cache.read_text())
            continue
        if time.time() > scadenza:
            continue
        prima = min(f["ms"] for f in sue)
        limite = min(1000, int((ultima - prima) / 60_000) + FINESTRA_MINUTI + 5)
        lista = _scarica(http, pool, limite, int(ultima / 1000) + FINESTRA_MINUTI * 60, scadenza)
        if lista is not None:
            cache.write_text(json.dumps(lista, separators=(",", ":")))
            candele[token] = lista
    return candele


def _scarica(http: requests.Session, pool: str, limite: int, prima_di: int, scadenza: float) -> list | None:
    """Candele al minuto di un pool. Se GeckoTerminal dice "troppe richieste" (429) aspetta e riprova
    lo stesso token, invece di saltarlo. None = non disponibile adesso (si riprova la volta dopo)."""
    attesa = 15
    while time.time() < scadenza:
        try:
            r = http.get(f"{GECKOTERMINAL}/pools/{pool}/ohlcv/minute",
                         params={"aggregate": 1, "limit": limite, "currency": "usd", "before_timestamp": prima_di},
                         timeout=20)
            if r.status_code == 429:
                time.sleep(attesa)
                attesa = min(attesa * 2, 60)
                continue
            r.raise_for_status()
            return sorted(r.json()["data"]["attributes"]["ohlcv_list"])
        except (requests.RequestException, KeyError, ValueError):
            return None
        finally:
            time.sleep(PAUSA_GECKO)
    return None


SALTO_MAX = 10  # oltre 10 volte il prezzo del minuto prima: dato sbagliato o prezzo irraggiungibile


def pulisci(candele: list) -> list:
    """Toglie i picchi impossibili (es. x2500 in un minuto quando la liquidità sparisce):
    a quel prezzo non si vende davvero, e da soli falsavano i risultati di migliaia di %.
    Candela: [ts, apertura, massimo, minimo, chiusura, volume]. I crolli restano: sono rug veri."""
    pulite, prima = [], None
    for c in candele:
        if prima is not None and c[4] > SALTO_MAX * prima:
            continue
        if prima is not None and c[2] > SALTO_MAX * prima:
            c = [c[0], c[1], max(c[1], c[4]), c[3], c[4], c[5]]
        pulite.append(c)
        prima = c[4]
    return pulite


# --- simulazione di una operazione ------------------------------------------

def simula(regole: dict, foto: dict, candele: list, puntata_usd: float) -> dict | None:
    """Ritorna {ritorno_pct, motivo, minuti} o None se l'ordine non sarebbe partito (slippage troppo alto)."""
    u, c = regole["uscite"], regole["costi"]
    liq = float(foto["coppia"]["liquidity"]["usd"] or 0)
    impatto = lambda usd: 2 * usd / liq * 100 if liq > 0 else 100.0
    slip_in = c["slippage_ritardo_pct"] + impatto(puntata_usd)
    if slip_in > c["slippage_max_pct"]:
        return None
    comm, rete = c["commissione_dex_pct"] / 100, c["rete_usd_per_ordine"]
    entrata_s = foto["ms"] / 1000
    dopo = [k for k in candele if k[0] >= entrata_s]  # candele che iniziano dopo la foto
    # Il prezzo della foto (DexScreener) arriva in ritardo: in media è ~3% sotto il prezzo vero di quel minuto.
    # Un bot vero compra al prezzo del minuto dopo, quindi si usa il più alto tra foto e apertura della candela successiva.
    p_base = max(float(foto["coppia"]["priceUsd"]), dopo[0][1] if dopo else 0.0)
    p_in = p_base * (1 + slip_in / 100)
    quantita = (puntata_usd * (1 - comm) - rete) / p_in
    stato = {"rimasto": 1.0, "incassato": 0.0}

    def vendi(frazione: float, prezzo: float) -> None:
        frazione = min(frazione, stato["rimasto"])
        lordo = quantita * frazione * prezzo
        netto = lordo * (1 - (c["slippage_ritardo_pct"] + impatto(lordo)) / 100) - lordo * comm - rete
        stato["incassato"] += max(netto, 0.0)
        stato["rimasto"] -= frazione

    def fine(motivo: str, minuti: float) -> dict:
        return {"ritorno_pct": (stato["incassato"] - puntata_usd) / puntata_usd * 100, "motivo": motivo, "minuti": round(minuti)}

    if not dopo:
        stato["incassato"] += quantita * p_in * (1 - c["perdita_se_rug_pct"] / 100)
        return fine("nessuno scambio dopo l'ingresso", 0)
    stop = p_in * (1 - u["stop_pct"] / 100)
    massimo, venduto2 = p_in, False
    for ts, o, h, l, chiusura, _ in dopo:
        minuti = (ts - entrata_s) / 60 + 1
        if minuti > FINESTRA_MINUTI:
            break
        if l <= p_in * (1 - c["perdita_se_rug_pct"] / 100):  # crollo di oltre il 90%: si assume il rug
            stato["incassato"] += quantita * stato["rimasto"] * p_in * (1 - c["perdita_se_rug_pct"] / 100)
            stato["rimasto"] = 0
            return fine("crollo oltre il 90% (rug)", minuti)
        if not venduto2:
            if o <= stop:
                vendi(1, o)
                return fine(f"stop -{u['stop_pct']}% (apertura sotto)", minuti)
            if l <= stop:  # se nella stessa candela toccava sia lo stop che il 2x, si assume prima lo stop
                vendi(1, stop)
                return fine(f"stop -{u['stop_pct']}%", minuti)
            if h >= p_in * u["vendi_40pct_a"]:
                # nella candela del 2x non si sa se il minimo è venuto prima o dopo: il trailing parte dalla successiva
                vendi(0.4, p_in * u["vendi_40pct_a"])
                venduto2, massimo = True, h
                continue
            if minuti >= u["tempo_max_minuti"]:
                vendi(1, chiusura)
                return fine(f"tempo scaduto ({u['tempo_max_minuti']} min)", minuti)
        if venduto2:
            soglia = massimo * (1 - u["trailing_resto_pct"] / 100)
            if l <= soglia:
                vendi(1, min(o, soglia))
                return fine(f"trailing -{u['trailing_resto_pct']}%", minuti)
            if stato["rimasto"] > 0.31 and h >= p_in * u["vendi_30pct_a"]:
                vendi(0.3, p_in * u["vendi_30pct_a"])
            massimo = max(massimo, h)
    vendi(1, dopo[-1][4] if dopo else p_in)
    return fine("fine della finestra di 2,5 ore", FINESTRA_MINUTI)


# --- una strategia su tutte le foto ------------------------------------------

def valuta(regole: dict, foto: list[dict], candele: dict[str, list], capitale_usd: float) -> dict:
    holder_prec: dict[str, int] = {}
    entrati: set[str] = set()
    operazioni = []
    for f in foto:
        token, coppia, rapporto = f["token"], f["coppia"], f["rugcheck"]
        prima, ora = holder_prec.get(token), rapporto.get("totalHolders")
        if ora:
            holder_prec[token] = ora
        if token in entrati or token not in candele:
            continue
        if not universo(coppia, regole, f["ms"])[0] or insegue(coppia, regole):
            continue
        if not controllo_truffe(rapporto, regole)[0]:
            continue
        if len(segnali(coppia, ora, prima, regole)) < regole["segnali"]["minimi_richiesti"]:
            continue
        puntata = capitale_usd * regole["dimensione"]["pct_capitale"] / 100
        esito = simula(regole, f, candele[token], puntata)
        if esito is None:
            continue
        entrati.add(token)
        operazioni.append({"ms": f["ms"], "simbolo": coppia["baseToken"].get("symbol"), **esito})
    return {"operazioni": operazioni, **statistiche(operazioni, regole, capitale_usd)}


def statistiche(operazioni: list[dict], regole: dict, capitale_usd: float) -> dict:
    """Capitale finale con puntata in % del capitale, massimo 2 posizioni insieme."""
    pct, massimo_aperte = regole["dimensione"]["pct_capitale"] / 100, regole["dimensione"]["max_posizioni"]
    contanti, aperte, eseguite = capitale_usd, [], 0
    for op in operazioni:
        for chiusa in [a for a in aperte if a[0] <= op["ms"]]:
            contanti += chiusa[1]
            aperte.remove(chiusa)
        if len(aperte) >= massimo_aperte:
            continue
        capitale = contanti + sum(a[2] for a in aperte)
        puntata = min(capitale * pct, contanti)
        contanti -= puntata
        aperte.append((op["ms"] + op["minuti"] * 60_000, puntata * (1 + op["ritorno_pct"] / 100), puntata))
        eseguite += 1
    contanti += sum(a[1] for a in aperte)
    ritorni = [o["ritorno_pct"] for o in operazioni]
    vinti = sum(r for r in ritorni if r > 0)
    persi = -sum(r for r in ritorni if r < 0)
    return {
        "n": len(ritorni), "eseguite": eseguite,
        "vincenti_pct": round(sum(r > 0 for r in ritorni) / len(ritorni) * 100, 1) if ritorni else 0.0,
        "ritorno_medio_pct": round(sum(ritorni) / len(ritorni), 2) if ritorni else 0.0,
        "profit_factor": round(vinti / persi, 2) if persi else (99.0 if vinti else 0.0),
        "capitale_finale_usd": round(contanti, 2), "variazione_pct": round((contanti / capitale_usd - 1) * 100, 1),
    }


# --- tante strategie -----------------------------------------------------------

def varianti(tutte: dict) -> list[tuple[str, dict]]:
    base = tutte["notte_meme"]
    elenco = [("B · Pazienti", unisci(base, tutte["notte_meme_varianti"]["b"])),
              ("C · Stop stretto", unisci(base, tutte["notte_meme_varianti"]["c"])),
              ("D · Piccole e veloci", unisci(base, tutte["notte_meme_varianti"]["d"]))]
    elenco.append(("Compra tutto (senza filtri né controlli)", unisci(base, {
        "universo": {"liquidita_min_usd": 0, "volume_5min_min_usd": 0, "holder_min": 0},
        "controllo_truffe": {"sviluppatore_max_pct": 100, "top10_max_pct": 100, "lp_bloccata_min_pct": 0,
                             "no_mint_authority": False, "no_freeze_authority": False, "no_rischi_gravi": False,
                             "no_insider_rilevati": False},
        "segnali": {"minimi_richiesti": 0}, "uscite": {"no_inseguire_pct_1h": 10**9}})))
    griglia = itertools.product([5000, 15000, 40000], [1000, 5000, 25000], ["severo", "senza LP"], [8, 12, 20], [10, 25, 60])
    for liq, vol, truffe, stop, minuti in griglia:
        modifiche = {"universo": {"liquidita_min_usd": liq, "volume_5min_min_usd": vol, "holder_min": 150},
                     "uscite": {"stop_pct": stop, "tempo_max_minuti": minuti}}
        if truffe == "senza LP":
            modifiche["controllo_truffe"] = {"lp_bloccata_min_pct": 0, "no_rischi_gravi": False}
        nome = f"liq ≥{liq // 1000}k · vol5m ≥{vol // 1000}k · truffe {truffe} · stop -{stop}% · max {minuti} min"
        elenco.append((nome, unisci(base, modifiche)))
    return elenco


def rapporto(risultati: list[dict], n_foto: int, n_token: int, n_candele: int) -> str:
    adesso = datetime.now(timezone.utc)
    n_fissi = sum(1 for r in risultati if not r["nome"].startswith("liq "))
    fissi = risultati[:n_fissi]
    affidabili = sorted([r for r in risultati[n_fissi:] if r["n"] >= 20], key=lambda r: -r["capitale_finale_usd"])
    riga = lambda r: (f"| {r['nome']} | {r['n']} | {r['vincenti_pct']}% | {r['ritorno_medio_pct']:+.1f}% | "
                      f"{r['profit_factor']} | {r['variazione_pct']:+.1f}% |")
    testa = ["| Strategia | Operazioni | Vincenti | Media per operazione | Profit factor | Capitale (50€) |", "|---|---|---|---|---|---|"]
    righe = [
        f"# Laboratorio meme — {adesso:%d/%m/%Y %H:%M} UTC", "",
        "**Soldi finti.** Foto salvate dal Registratore + prezzi al minuto da GeckoTerminal nelle 2,5 ore dopo ogni foto. "
        "Commissioni, slippage e perdita in caso di rug sono stime da `regole.yaml`.", "",
        f"Foto: **{n_foto}** di **{n_token}** token · token con prezzi successivi disponibili: **{n_candele}**.", "",
        "## Le strategie di riferimento", "", *testa, *[riga(r) for r in fissi], "",
        "## Le 10 varianti migliori (almeno 20 operazioni)", "", *testa, *[riga(r) for r in affidabili[:10]], "",
        "## Le 5 peggiori", "", *testa, *[riga(r) for r in affidabili[-5:]], "",
        "## Come leggerlo", "",
        "- Con poche operazioni un buon risultato può essere fortuna: aspetta più notti di registrazione.",
        "- Provare tante varianti e scegliere la migliore esagera i risultati: la vincitrice va riprovata su notti nuove.",
        "- Lo stop è simulato al prezzo peggiore della candela; un crollo di oltre il 90% conta come rug (recuperi il 10%).",
        "",
    ]
    return "\n".join(righe)


def main() -> None:
    argomenti = argparse.ArgumentParser(description="Laboratorio meme: riprova le strategie sulle foto")
    argomenti.add_argument("--solo-candele", action="store_true", help="scarica i prezzi e basta")
    argomenti.add_argument("--parte", type=int, default=0)
    argomenti.add_argument("--parti", type=int, default=1)
    argomenti.add_argument("--max-minuti", type=float, default=55)
    a = argomenti.parse_args()
    tutte = carica_regole()
    foto = carica_foto()
    print(f"{len(foto)} foto di {len({f['token'] for f in foto})} token")
    candele = scarica_candele(foto, int(time.time() * 1000), a.max_minuti, a.parte, a.parti)
    print(f"prezzi successivi disponibili per {len(candele)} token")
    if a.solo_candele:
        return
    candele = {token: pulisci(lista) for token, lista in candele.items()}
    capitale = 50 * 1.1  # circa 50€ in dollari
    risultati = []
    for nome, regole in varianti(tutte):
        esito = valuta(regole, foto, candele, capitale)
        risultati.append({"nome": nome, **{k: v for k, v in esito.items() if k != "operazioni"}})
    cartella = RADICE / "risultati"
    cartella.mkdir(exist_ok=True)
    (cartella / "laboratorio_meme.md").write_text(
        rapporto(risultati, len(foto), len({f["token"] for f in foto}), len(candele)), encoding="utf-8")
    (cartella / "laboratorio_meme.json").write_text(json.dumps(risultati, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Rapporto in {cartella / 'laboratorio_meme.md'}")


if __name__ == "__main__":
    main()
