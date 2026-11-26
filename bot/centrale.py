"""CENTRALE DI CONTROLLO: raccoglie lo stato di tutto il progetto in file JSON per il pannello.

Uso: python -m bot.centrale
Scrive risultati/centrale/*.json (un file per ogni dataset del pannello) e stampa l'elenco.
"""
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.notte.__main__ import unisci
from bot.notte.esporta import esporta
from bot.regole import RADICE, carica_regole

ITALIA = ZoneInfo("Europe/Rome")
USCITA = RADICE / "risultati" / "centrale"
NOTTI = RADICE / "risultati" / "notte"
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}(-[a-z])?$")


def _ora_it(dt: datetime) -> str:
    return dt.astimezone(ITALIA).strftime("%d/%m %H:%M")


def _ultima_notte(variante: str = "") -> Path | None:
    """variante "" = la A (cartella AAAA-MM-GG), "-b" = la B (AAAA-MM-GG-b), e così via."""
    cartelle = sorted(p for p in NOTTI.glob("*") if p.is_dir() and DATA.match(p.name) and p.name[10:] == variante
                      and (p / "stato.json").exists())
    return cartelle[-1] if cartelle else None


def _foto() -> list[dict]:
    foto = []
    for file in sorted((RADICE / "registro").glob("*.jsonl")):
        for riga in file.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                f = json.loads(riga)
                foto.append({"ms": f["ms"], "token": f["token"]})
    return foto


def _riga_notte(id_: str, nome: str, cartella: Path | None) -> dict:
    if not cartella:
        return {"id": id_, "attivita": nome, "stato": "in attesa", "dettaglio": "Nessuna giornata registrata ancora.",
                "ultimo": "—", "prossimo": "gira 24 ore su 24"}
    stato = json.loads((cartella / "stato.json").read_text())
    p, cambio = stato["portafoglio"], stato["cambio_eur_usd"]
    capitale = (p["contanti"] + sum(x["quantita"] * x["ultimo_prezzo"] for x in p["posizioni"])) / cambio
    finita = (cartella / "riepilogo.md").exists()
    return {"id": id_, "attivita": nome, "stato": "finita" if finita else "in corso",
            "dettaglio": f"Giornata {cartella.name[:10]}: {len(p['chiusure'])} operazioni, capitale {capitale:.2f} €".replace(".", ","),
            "ultimo": _ora_it(datetime.fromtimestamp((cartella / "stato.json").stat().st_mtime, timezone.utc)),
            "prossimo": "gira 24 ore su 24, nuova giornata alle 07:00"}


def sistema(foto: list[dict]) -> list[dict]:
    adesso = datetime.now(timezone.utc)
    righe = [_riga_notte("notte_b", "Bot B · Aggressiva", _ultima_notte("-b")),
             _riga_notte("notte_c", "Bot C · Grandi e protette", _ultima_notte("-c")),
             _riga_notte("notte_d", "Bot D · Piccole e veloci", _ultima_notte("-d"))]
    if foto:
        ultima = datetime.fromtimestamp(foto[-1]["ms"] / 1000, timezone.utc)
        attivo = adesso - ultima < timedelta(hours=7)  # le foto arrivano su GitHub a fine turno (circa ogni 6 ore)
        righe.append({"id": "registratore", "attivita": "Registratore 24/7", "stato": "attivo" if attivo else "in pausa",
                      "dettaglio": f"{len(foto)} foto di {len({f['token'] for f in foto})} memecoin",
                      "ultimo": _ora_it(ultima), "prossimo": "foto caricate a fine turno, ogni 6 ore circa"})
    else:
        righe.append({"id": "registratore", "attivita": "Registratore 24/7", "stato": "in attesa",
                      "dettaglio": "Nessuna foto ancora.", "ultimo": "—", "prossimo": "riparte ogni 6 ore"})
    lab = RADICE / "risultati" / "laboratorio_meme.json"
    if lab.exists():
        risultati = json.loads(lab.read_text())
        a = next((r for r in risultati if r["nome"].startswith("D ")), None)
        griglia = [r for r in risultati if r["nome"].startswith("liq ")]
        positive = sum(1 for r in griglia if r["n"] >= 20 and r["variazione_pct"] > 0)
        dettaglio = (f"D: {a['variazione_pct']:+.1f}% su {a['n']} operazioni · " if a else "") + \
                    f"{positive} varianti su {len(griglia)} in positivo (con almeno 20 operazioni)"
        righe.append({"id": "lab_meme", "attivita": "Laboratorio meme", "stato": "pronto", "dettaglio": dettaglio,
                      "ultimo": _ora_it(datetime.fromtimestamp(lab.stat().st_mtime, timezone.utc)), "prossimo": "dopo ogni turno del registratore"})
    else:
        righe.append({"id": "lab_meme", "attivita": "Laboratorio meme", "stato": "in attesa",
                      "dettaglio": "Servono 2,5 ore di prezzi dopo le prime foto.", "ultimo": "—", "prossimo": "dopo il primo turno del registratore"})
    binance = sorted((RADICE / "risultati").glob("laboratorio_20*.md"))
    if binance:
        testo = binance[-1].read_text(encoding="utf-8")
        trovato = re.search(r"Promosse: (\d+) su (\d+)", testo)
        righe.append({"id": "lab_binance", "attivita": "Laboratorio Binance", "stato": "fatto",
                      "dettaglio": f"{trovato[1]} strategie promosse su {trovato[2]} (BTC, ETH, SOL, DOGE, PEPE)" if trovato else "Rapporto disponibile",
                      "ultimo": binance[-1].stem.removeprefix("laboratorio_"), "prossimo": "su richiesta"})
    domani = (adesso.astimezone(ITALIA) + timedelta(days=1)).strftime("%d/%m")
    oggi_708 = adesso.astimezone(ITALIA).replace(hour=7, minute=8, second=0, microsecond=0)
    prossimo = oggi_708 if adesso.astimezone(ITALIA) < oggi_708 else oggi_708 + timedelta(days=1)
    righe.append({"id": "aggiornamento", "attivita": "Aggiornamento del pannello", "stato": "programmato",
                  "dettaglio": "Claude aggiorna questa centrale e ti manda una notifica.", "ultimo": _ora_it(adesso),
                  "prossimo": f"{prossimo:%d/%m} alle 07:08" if prossimo.strftime('%d/%m') != domani else "domani alle 07:08"})
    return righe


# I primi lavori hanno messaggi in inglese: qui la loro versione italiana. I nuovi sono già in italiano.
TRADUZIONI = {
    "Add Lab and Shield: paper-only backtests on real Binance data": "Laboratorio e Scudo: test su carta con dati reali di Binance",
    "Add overnight memecoin paper bot replicating the Grok Bot rules": "Bot notturno memecoin su carta con le regole del prompt Grok",
    "Track agent activity per scan and export panel data": "Il bot registra cosa fa ogni agente; dati per il pannello",
    "Add GeckoTerminal discovery and a riskier strategy B": "Più token da GeckoTerminal e strategia B più rischiosa",
    "Add a 24/7 snapshot recorder and a memecoin strategy lab": "Registratore 24/7 e laboratorio delle strategie meme",
    "Export strategy B test data for the dashboard": "Dati della prova B caricati nel pannello",
    "Live paper test: partial results (run still in progress)": "Prima prova dal vivo: risultati parziali",
    "Live paper tests A (30 min) and B (15 min): final results": "Prove dal vivo A (30 min) e B (15 min): risultati finali",
    "Live paper tests A and B: update partial results": "Prove dal vivo A e B: risultati parziali",
    "Recorder: local snapshots so far": "Registratore: foto raccolte finora",
    "Second live paper test: partial results (run in progress)": "Seconda prova dal vivo: risultati parziali",
    "Second live paper test: update partial results": "Seconda prova dal vivo: risultati parziali",
}


def lavori(limite: int = 40) -> list[dict]:
    uscita = subprocess.run(["git", "log", f"-{limite}", "--format=%ct%x09%an%x09%s"], cwd=RADICE,
                            capture_output=True, text=True, check=False).stdout
    chi = {"notte-bot": "Bot notturno", "registratore-bot": "Registratore"}
    righe = []
    for riga in uscita.splitlines():
        ts, autore, oggetto = riga.split("\t", 2)
        if oggetto.startswith(("Bot su carta: salvataggio intermedio", "Prezzi per il laboratorio")):
            continue  # salvataggi automatici frequenti: nascondono i lavori veri
        righe.append({"n": len(righe) + 1, "quando": _ora_it(datetime.fromtimestamp(int(ts), timezone.utc)),
                      "chi": chi.get(autore, "Claude"), "cosa": TRADUZIONI.get(oggetto, oggetto)})
    return righe


def registro_ore(foto: list[dict]) -> list[dict]:
    ore = Counter()
    token_ora: dict[str, set] = {}
    for f in foto:
        chiave = datetime.fromtimestamp(f["ms"] / 1000, ITALIA).strftime("%d/%m %H:00")
        ore[chiave] += 1
        token_ora.setdefault(chiave, set()).add(f["token"])
    return [{"ora": k, "foto": ore[k], "token": len(token_ora[k])} for k in sorted(ore, key=lambda k: (k[3:5], k[:2], k[6:]))]


# Le tre strategie in parole semplici. I numeri delle regole vengono da regole.yaml, così restano veri.
STRATEGIE = [
    ("B", "b", "Aggressiva", "Filtri larghi ma controllo anti-truffa severo (liquidità bloccata). L'unica ad aver chiuso una notte in guadagno."),
    ("C", "c", "Lascia correre", "Come la B, ma tiene le monete fino a un'ora con uno stop più largo, per prendere le salite lunghe."),
    ("D", "d", "Puntate piccole", "Come la B, ma punta solo il 20% ed esce presto (−10%): perde meno quando va male."),
]


def _regole_in_parole(r: dict) -> tuple[str, str, str]:
    u, t, x, d = r["universo"], r["controllo_truffe"], r["uscite"], r["dimensione"]
    truffe = ("controllo anti-truffa severo" if t["lp_bloccata_min_pct"] >= 90
              else "controllo anti-truffa senza guardare se la liquidità è bloccata")
    compra = f"Monete con almeno {u['liquidita_min_usd'] // 1000}k $ di liquidità e {u['holder_min']} holder, {truffe}"
    vende = f"A −{x['stop_pct']}%, oppure dopo {x['tempo_max_minuti']} minuti se non è raddoppiata"
    punta = f"{d['pct_capitale']}% del capitale per operazione"
    return compra, vende, punta


def _notti(suffisso: str) -> list[Path]:
    return sorted(p for p in NOTTI.glob("*") if p.is_dir() and DATA.match(p.name) and p.name[10:] == (f"-{suffisso}" if suffisso else "")
                  and (p / "stato.json").exists())


def _capitale_eur(cartella: Path) -> tuple[float, int, int, int]:
    stato = json.loads((cartella / "stato.json").read_text())
    p, cambio = stato["portafoglio"], stato["cambio_eur_usd"]
    capitale = (p["contanti"] + sum(x["quantita"] * x["ultimo_prezzo"] for x in p["posizioni"])) / cambio
    vinte = sum(1 for c in p["chiusure"] if c["incassato_usd"] > c["speso_usd"])
    return capitale, len(p["chiusure"]), vinte, len(p["chiusure"]) - vinte


def strategie() -> list[dict]:
    tutte = carica_regole()
    base = tutte["notte_meme"]
    lab_file = RADICE / "risultati" / "laboratorio_meme.json"
    lab = json.loads(lab_file.read_text()) if lab_file.exists() else []
    righe = []
    for lettera, suffisso, nome, frase in STRATEGIE:
        regole = unisci(base, tutte["notte_meme_varianti"][suffisso]) if suffisso else base
        compra, vende, punta = _regole_in_parole(regole)
        notti = _notti(suffisso)
        riga = {"id": lettera, "nome": nome, "frase": frase, "compra": compra, "vende": vende, "punta": punta,
                "notti": len(notti), "notte": "", "capitale_eur": None, "variazione_pct": None,
                "operazioni": 0, "vinte": 0, "perse": 0, "totale_pct": None, "in_corso": False}
        if notti:
            capitale, n, vinte, perse = _capitale_eur(notti[-1])
            partenza = base["capitale_euro"]
            totale = sum(_capitale_eur(c)[0] - partenza for c in notti)  # ogni notte riparte da 50 €
            riga.update(notte=notti[-1].name[:10], capitale_eur=round(capitale, 2), in_corso=not (notti[-1] / "riepilogo.md").exists(),
                        variazione_pct=round((capitale / partenza - 1) * 100, 1), operazioni=n, vinte=vinte, perse=perse,
                        totale_pct=round(totale / (partenza * len(notti)) * 100, 1))
        test = next((r for r in lab if r["nome"].startswith(lettera + " ")), None)
        riga.update(lab_operazioni=test["n"] if test else 0, lab_variazione_pct=test["variazione_pct"] if test else None,
                    lab_media_pct=test["ritorno_medio_pct"] if test else None)
        righe.append(riga)
    return righe


def operazioni_di_tutti() -> list[dict]:
    """Le operazioni dell'ultima giornata di ogni bot in un'unica tabella, con la colonna del bot."""
    righe = []
    for lettera, suffisso, _, _ in STRATEGIE:
        notti = _notti(suffisso)
        if not notti:
            continue
        for o in json.loads((esporta(notti[-1]) / "operazioni.json").read_text(encoding="utf-8")):
            righe.append(dict(o, bot=lettera, notte=notti[-1].name[:10], n=len(righe) + 1))
    return righe


def lab_meme() -> list[dict]:
    lab = RADICE / "risultati" / "laboratorio_meme.json"
    if not lab.exists():
        return []
    risultati = json.loads(lab.read_text())
    fissi = sum(1 for r in risultati if not r["nome"].startswith("liq "))
    riferimento = [dict(r, gruppo="riferimento") for r in risultati[:fissi]]
    migliori = sorted([r for r in risultati[fissi:] if r["n"] >= 20], key=lambda r: -r["capitale_finale_usd"])[:10]
    return [dict(r, n_riga=i + 1, **({"gruppo": r.get("gruppo", "migliori")})) for i, r in enumerate(riferimento + migliori)]


def main() -> None:
    USCITA.mkdir(parents=True, exist_ok=True)
    foto = _foto()
    # prima l'ultima notte vera; se non c'è ancora, la prova più recente che ha fatto operazioni
    prove = [p for p in NOTTI.glob("prova*") if (p / "stato.json").exists()]
    con_operazioni = lambda p: bool(json.loads((p / "stato.json").read_text())["portafoglio"]["chiusure"])
    notte = _ultima_notte("-b") or max(prove, key=lambda p: (con_operazioni(p), (p / "stato.json").stat().st_mtime), default=None)
    file = {"sistema": sistema(foto), "lavori": lavori(), "registro_ore": registro_ore(foto), "lab_meme": lab_meme(),
            "strategie": strategie()}
    if notte:
        pannello = esporta(notte)
        for json_notte in pannello.glob("*.json"):
            file[json_notte.stem] = json.loads(json_notte.read_text(encoding="utf-8"))
    tutte_le_operazioni = operazioni_di_tutti()
    if tutte_le_operazioni:
        file["operazioni"] = tutte_le_operazioni
    for nome, righe in file.items():
        (USCITA / f"{nome}.json").write_text(json.dumps(righe, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(str(USCITA / f"{n}.json") for n in file))


if __name__ == "__main__":
    main()
