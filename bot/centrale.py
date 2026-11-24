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

from bot.notte.esporta import esporta
from bot.regole import RADICE

ITALIA = ZoneInfo("Europe/Rome")
USCITA = RADICE / "risultati" / "centrale"
NOTTI = RADICE / "risultati" / "notte"
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}(-b)?$")


def _ora_it(dt: datetime) -> str:
    return dt.astimezone(ITALIA).strftime("%d/%m %H:%M")


def _ultima_notte(variante: str = "") -> Path | None:
    cartelle = sorted(p for p in NOTTI.glob("*") if p.is_dir() and DATA.match(p.name) and p.name.endswith(variante or "")
                      and (variante or not p.name.endswith("-b")) and (p / "stato.json").exists())
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
        return {"id": id_, "attivita": nome, "stato": "in attesa", "dettaglio": "Nessuna notte registrata ancora.",
                "ultimo": "—", "prossimo": "stanotte alle 23:00"}
    stato = json.loads((cartella / "stato.json").read_text())
    p, cambio = stato["portafoglio"], stato["cambio_eur_usd"]
    capitale = (p["contanti"] + sum(x["quantita"] * x["ultimo_prezzo"] for x in p["posizioni"])) / cambio
    finita = (cartella / "riepilogo.md").exists()
    return {"id": id_, "attivita": nome, "stato": "finita" if finita else "in corso",
            "dettaglio": f"Notte {cartella.name[:10]}: {len(p['chiusure'])} operazioni, capitale {capitale:.2f} €".replace(".", ","),
            "ultimo": _ora_it(datetime.fromtimestamp((cartella / "stato.json").stat().st_mtime, timezone.utc)),
            "prossimo": "stanotte alle 23:00"}


def sistema(foto: list[dict]) -> list[dict]:
    adesso = datetime.now(timezone.utc)
    righe = [_riga_notte("notte_a", "Bot notturno A · regole Grok", _ultima_notte()),
             _riga_notte("notte_b", "Bot notturno B · più largo e rischioso", _ultima_notte("-b"))]
    if foto:
        ultima = datetime.fromtimestamp(foto[-1]["ms"] / 1000, timezone.utc)
        attivo = adesso - ultima < timedelta(minutes=30)
        righe.append({"id": "registratore", "attivita": "Registratore 24/7", "stato": "attivo" if attivo else "in pausa",
                      "dettaglio": f"{len(foto)} foto di {len({f['token'] for f in foto})} memecoin",
                      "ultimo": _ora_it(ultima), "prossimo": "riparte ogni 6 ore"})
    else:
        righe.append({"id": "registratore", "attivita": "Registratore 24/7", "stato": "in attesa",
                      "dettaglio": "Nessuna foto ancora.", "ultimo": "—", "prossimo": "riparte ogni 6 ore"})
    lab = RADICE / "risultati" / "laboratorio_meme.json"
    if lab.exists():
        risultati = json.loads(lab.read_text())
        a = next((r for r in risultati if r["nome"].startswith("A ")), None)
        positive = sum(1 for r in risultati[3:] if r["n"] >= 20 and r["variazione_pct"] > 0)
        dettaglio = (f"A: {a['variazione_pct']:+.1f}% su {a['n']} operazioni · " if a else "") + \
                    f"{positive} varianti su {len(risultati) - 3} in positivo (con almeno 20 operazioni)"
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


def lab_meme() -> list[dict]:
    lab = RADICE / "risultati" / "laboratorio_meme.json"
    if not lab.exists():
        return []
    risultati = json.loads(lab.read_text())
    riferimento = [dict(r, gruppo="riferimento") for r in risultati[:3]]
    migliori = sorted([r for r in risultati[3:] if r["n"] >= 20], key=lambda r: -r["capitale_finale_usd"])[:10]
    return [dict(r, n_riga=i + 1, **({"gruppo": r.get("gruppo", "migliori")})) for i, r in enumerate(riferimento + migliori)]


def main() -> None:
    USCITA.mkdir(parents=True, exist_ok=True)
    foto = _foto()
    # prima l'ultima notte vera; se non c'è ancora, la prova più recente che ha fatto operazioni
    prove = [p for p in NOTTI.glob("prova*") if (p / "stato.json").exists()]
    con_operazioni = lambda p: bool(json.loads((p / "stato.json").read_text())["portafoglio"]["chiusure"])
    notte = _ultima_notte() or max(prove, key=lambda p: (con_operazioni(p), (p / "stato.json").stat().st_mtime), default=None)
    file = {"sistema": sistema(foto), "lavori": lavori(), "registro_ore": registro_ore(foto), "lab_meme": lab_meme()}
    if notte:
        pannello = esporta(notte)
        for json_notte in pannello.glob("*.json"):
            file[json_notte.stem] = json.loads(json_notte.read_text(encoding="utf-8"))
    for nome, righe in file.items():
        (USCITA / f"{nome}.json").write_text(json.dumps(righe, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(str(USCITA / f"{n}.json") for n in file))


if __name__ == "__main__":
    main()
