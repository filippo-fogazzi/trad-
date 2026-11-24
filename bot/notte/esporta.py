"""Trasforma i risultati di una notte in file JSON per il pannello.

Uso: python -m bot.notte.esporta risultati/notte/<data>
Scrive <cartella>/pannello/{riepilogo,operazioni,diario,filtri}.json
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ITALIA = ZoneInfo("Europe/Rome")
RIGA = re.compile(r"^(\d\d:\d\d:\d\d) (\S+)\s+(.*)$")


def esporta(cartella: Path) -> Path:
    stato = json.loads((cartella / "stato.json").read_text())
    p, cambio = stato["portafoglio"], stato["cambio_eur_usd"]
    uscita = cartella / "pannello"
    uscita.mkdir(exist_ok=True)

    chiusure = sorted(p["chiusure"], key=lambda c: c["chiusa_ms"])
    operazioni, cumulato = [], 0.0
    for numero, c in enumerate(chiusure, 1):
        guadagno = c["incassato_usd"] - c["speso_usd"]
        cumulato += guadagno
        operazioni.append({
            "n": numero, "moneta": "$" + c["simbolo"], "entrata": _ora(c["aperta_ms"]), "uscita": _ora(c["chiusa_ms"]),
            "speso_usd": round(c["speso_usd"], 2), "incassato_usd": round(c["incassato_usd"], 2),
            "risultato_usd": round(guadagno, 2), "capitale_dopo_usd": round(p["capitale_iniziale"] + cumulato, 2),
            "motivo_ingresso": c["motivo_ingresso"], "motivo_uscita": c["motivo_uscita"],
        })
    aperte_valore = sum(x["quantita"] * x["ultimo_prezzo"] for x in p["posizioni"])
    capitale = p["contanti"] + aperte_valore
    vinte = sum(o["risultato_usd"] > 0 for o in operazioni)
    diario_righe = (cartella / "diario.log").read_text(encoding="utf-8").splitlines() if (cartella / "diario.log").exists() else []
    riepilogo = [{
        "notte": cartella.name,
        "capitale_iniziale_usd": round(p["capitale_iniziale"], 2),
        "capitale_usd": round(capitale, 2),
        "capitale_iniziale_eur": round(p["capitale_iniziale"] / cambio, 2),
        "capitale_eur": round(capitale / cambio, 2),
        "variazione_pct": round((capitale / p["capitale_iniziale"] - 1) * 100, 2),
        "operazioni": len(operazioni), "vinte": vinte, "perse": len(operazioni) - vinte,
        "posizioni_aperte": len(p["posizioni"]), "token_guardati": len(stato["visti"]),
        "stato": p["fermo"] or ("finita" if any("RIEPILOGO" in r for r in diario_righe) else "in corso"),
        "cambio_eur_usd": cambio,
        "aggiornato": datetime.fromtimestamp((cartella / "stato.json").stat().st_mtime, ITALIA).strftime("%d/%m/%Y %H:%M"),
    }]
    diario = [{"ora": m[1], "tipo": m[2], "testo": m[3]} for r in diario_righe if (m := RIGA.match(r))]
    nomi = {"liquidità": "liquidità troppo bassa", "volume 5 min": "volume 5 min troppo basso"}
    filtri = [{"motivo": nomi.get(k, k), "token": v} for k, v in sorted(stato["conteggio_filtri"].items(), key=lambda x: -x[1])]

    agenti, imbuto = _agenti(stato, riepilogo[0], diario, cambio)
    attivita = [dict(g, capitale_eur=round(g.get("capitale_usd", 0) / cambio, 2)) for g in stato.get("attivita", [])]
    for nome, righe in (("riepilogo", riepilogo), ("operazioni", operazioni), ("diario", diario), ("filtri", filtri),
                        ("agenti", agenti), ("imbuto", imbuto), ("attivita", attivita)):
        (uscita / f"{nome}.json").write_text(json.dumps(righe, ensure_ascii=False, indent=1), encoding="utf-8")
    return uscita


FILTRI_PERIMETRO = ("coppia troppo vecchia", "liquidità", "volume 5 min", "nessun prezzo disponibile", "DEX non previsto")


def _agenti(stato: dict, r: dict, diario: list[dict], cambio: float) -> tuple[list[dict], list[dict]]:
    p = stato["portafoglio"]
    c = stato.get("contatori")
    if not c:  # notti registrate prima dei contatori: si ricostruisce quello che si può
        fuori = sum(n for k, n in stato["conteggio_filtri"].items() if k.startswith(FILTRI_PERIMETRO))
        c = {"guardati": len(stato["visti"]), "nel_perimetro": len(stato["visti"]) - fuori, "controllati": 0,
             "bocciati": 0, "senza_segnali": 0, "comprati": sum(d["tipo"] == "ENTRA" for d in diario)}
    else:
        c = dict(c, guardati=len(stato["visti"]))
    ultima = lambda *tipi: next((d["ora"][:5] for d in reversed(diario) if d["tipo"] in tipi), "—")
    attivita = stato.get("attivita") or []
    finita, fermo = r["stato"] == "finita", bool(p["fermo"])
    stato_di = lambda attivo, attesa="in attesa": "fermo" if fermo else "finito" if finita else attivo or attesa
    dimezzata = p["perdite_di_fila"] >= 2
    prossima = r["capitale_eur"] * 0.33 * (0.5 if dimezzata else 1)
    ordini = sum(x["tipo"] in ("ENTRA", "PARZIALE", "ESCE") for x in diario)
    agenti = [
        {"id": "scanner", "agente": "Scanner", "ruolo": "Cerca memecoin nuove e i loro segnali",
         "numero": c["guardati"], "unita": "", "etichetta": "token guardati",
         "dettaglio": f"{c['nel_perimetro']} nel perimetro · {c.get('senza_segnali', 0)} senza 2 segnali",
         "ultima": attivita[-1]["ora"][:5] if attivita else "—", "stato": stato_di("attivo")},
        {"id": "controllo", "agente": "Controllo truffe", "ruolo": "Boccia i token sospetti con RugCheck",
         "numero": c["bocciati"], "unita": "", "etichetta": "token bocciati",
         "dettaglio": f"{c['controllati'] - c['bocciati']} superati su {c['controllati']} controllati",
         "ultima": ultima("FILTRATO"), "stato": stato_di("attivo" if c["controllati"] else None)},
        {"id": "dimensione", "agente": "Dimensione", "ruolo": "Decide quanto puntare su ogni operazione",
         "numero": round(prossima, 2), "unita": "€", "etichetta": "prossima puntata",
         "dettaglio": "33% del capitale" + (" · dimezzata dopo 2 perdite" if dimezzata else "") + " · max 2 posizioni",
         "ultima": ultima("ENTRA"), "stato": stato_di("pronto")},
        {"id": "esecutore", "agente": "Esecutore", "ruolo": "Compra e vende su carta, con stop e scala di vendita",
         "numero": ordini, "unita": "", "etichetta": "ordini su carta",
         "dettaglio": f"{len(p['posizioni'])} posizioni aperte",
         "ultima": ultima("ENTRA", "PARZIALE", "ESCE"), "stato": stato_di("in posizione" if p["posizioni"] else None)},
        {"id": "diario", "agente": "Diario", "ruolo": "Scrive ogni decisione con il suo motivo",
         "numero": len(diario), "unita": "", "etichetta": "righe scritte",
         "dettaglio": f"{sum(x['tipo'] == 'FILTRATO' for x in diario)} scarti spiegati",
         "ultima": diario[-1]["ora"][:5] if diario else "—", "stato": stato_di("attivo")},
        {"id": "capitale", "agente": "Capitale", "ruolo": "Tiene il saldo e ferma tutto a −30%",
         "numero": r["capitale_eur"], "unita": "€", "etichetta": "capitale attuale",
         "dettaglio": f"massimo della notte {p['picco'] / cambio:.2f} €".replace(".", ","),
         "ultima": r["aggiornato"][-5:], "stato": stato_di("attivo")},
    ]
    imbuto = [
        {"passo": "Guardati", "token": c["guardati"]},
        {"passo": "Nel perimetro", "token": c["nel_perimetro"]},
        {"passo": "Controllati", "token": c["controllati"]},
        {"passo": "Superano il controllo", "token": c["controllati"] - c["bocciati"]},
        {"passo": "Con 2 segnali", "token": max(c["controllati"] - c["bocciati"] - c.get("senza_segnali", 0), 0)},
        {"passo": "Comprati", "token": c["comprati"]},
    ]
    return agenti, imbuto


def _ora(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, ITALIA).strftime("%H:%M")


if __name__ == "__main__":
    print(esporta(Path(sys.argv[1])))
