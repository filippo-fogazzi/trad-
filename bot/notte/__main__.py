"""Esperimento notturno memecoin SU CARTA.

Uso:
  python -m bot.notte                 # gira fino all'ora di fine in regole.yaml (07:00)
  python -m bot.notte --minuti 30     # gira 30 minuti (prova)

Scrive in risultati/notte/<data>/:
  diario.log     ogni decisione con il suo motivo (ENTRA / ESCE / FILTRATO)
  cruscotto.md   situazione aggiornata a ogni giro
  riepilogo.md   il resoconto finale
  stato.json     per ripartire da dove era dopo un crash o un riavvio
"""
import argparse
import json
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.notte.controlli import controllo_truffe, insegue, segnali, universo
from bot.notte.fonti import Fonti
from bot.notte.portafoglio import Portafoglio
from bot.regole import RADICE, carica_regole

ITALIA = ZoneInfo("Europe/Rome")


class Notte:
    def __init__(self, regole: dict, fine: datetime, cartella: Path, fonti: Fonti | None = None,
                 pausa: datetime | None = None):
        self.r = regole
        self.fine = fine
        self.pausa = min(pausa or fine, fine)   # prima della fine: salva e riprende in un secondo turno
        self.cartella = cartella
        self.fonti = fonti or Fonti()
        self.cartella.mkdir(parents=True, exist_ok=True)
        self.holder: dict[str, int] = {}            # ultimo numero di holder visto per token
        self.filtrati: dict[str, str] = {}          # ultimo motivo di scarto per token (per non ripeterlo)
        self.conteggio_filtri: dict[str, int] = {}
        self.visti: set[str] = set()
        self.ultima_ricerca = 0.0
        self.ultimo_controllo_svil = 0.0
        self.saldi_svil: dict[str, float] = {}
        self.dati_mancanti: dict[str, int] = {}
        self.attivita: list[dict] = []              # un riga per ogni giro dello scanner
        self.contatori = {"guardati": 0, "nel_perimetro": 0, "controllati": 0, "bocciati": 0,
                          "senza_segnali": 0, "rifiutati_dimensione": 0, "comprati": 0}
        self.portafoglio = self._carica_o_crea()

    # --- ciclo principale ----------------------------------------------------
    def gira(self) -> None:
        self.scrivi("AVVIO", f"capitale ${self.portafoglio.capitale():.2f}, "
                             f"fine alle {self.fine:%H:%M}, questo turno fino alle {self.pausa:%H:%M}")
        while datetime.now(ITALIA) < self.pausa:
            try:
                adesso = time.time()
                if adesso - self.ultima_ricerca >= self.r["ritmo_secondi"]["ricerca"]:
                    self.ultima_ricerca = adesso
                    self.cerca()
                if self.portafoglio.posizioni:
                    self.controlla_posizioni()
                messaggio = self.portafoglio.aggiorna_picco()
                if messaggio:
                    self.scrivi("FERMO", messaggio)
                self.salva()
            except Exception as errore:  # il bot non si ferma per un errore: lo scrive e riprova
                self.scrivi("ERRORE", f"{type(errore).__name__}: {errore}")
                (self.cartella / "errori.txt").open("a").write(traceback.format_exc() + "\n")
                time.sleep(15)
            time.sleep(self.r["ritmo_secondi"]["posizioni"])
        if self.pausa < self.fine:
            self.salva()
            self.scrivi("PAUSA", "fine del turno: stato salvato, le posizioni restano aperte")
            return
        for riga in self.portafoglio.chiudi_tutto(_ms(), "fine della notte"):
            self.scrivi("ESCE", riga.removeprefix("ESCE "))
        self.salva()
        self.scrivi_riepilogo()

    # --- SCANNER + CONTROLLO TRUFFE ------------------------------------------
    def cerca(self) -> None:
        token = self.fonti.token_recenti()
        coppie = self.fonti.coppie(token)
        adesso_ms = _ms()
        giro = {"ora": datetime.now(ITALIA).strftime("%H:%M:%S"), "guardati": len(coppie), "nuovi": 0,
                "nel_perimetro": 0, "controllati": 0, "bocciati": 0, "senza_segnali": 0, "comprati": 0}
        try:
            self._cerca(coppie, adesso_ms, giro)
        finally:
            for chiave in self.contatori:
                self.contatori[chiave] += giro.get(chiave, 0)
            giro["capitale_usd"] = round(self.portafoglio.capitale(), 2)
            self.attivita = (self.attivita + [giro])[-2000:]

    def _cerca(self, coppie: dict, adesso_ms: int, giro: dict) -> None:
        for indirizzo, coppia in coppie.items():
            simbolo = coppia["baseToken"].get("symbol") or indirizzo[:6]
            giro["nuovi"] += indirizzo not in self.visti
            self.visti.add(indirizzo)
            if indirizzo in self.portafoglio.posizioni:
                continue
            ok, motivo = universo(coppia, self.r, adesso_ms)
            if not ok:
                self.filtra(indirizzo, simbolo, motivo, scrivi=False)
                continue
            giro["nel_perimetro"] += 1
            if insegue(coppia, self.r):
                self.filtra(indirizzo, simbolo, "già +300% nell'ultima ora, niente inseguimento")
                continue
            rapporto = self.fonti.rapporto_rugcheck(indirizzo)
            giro["controllati"] += 1
            holder_prima, holder_ora = self.holder.get(indirizzo), rapporto.get("totalHolders")
            if holder_ora:
                self.holder[indirizzo] = holder_ora
            passa, motivi = controllo_truffe(rapporto, self.r)
            if not passa:
                giro["bocciati"] += 1
                self.filtra(indirizzo, simbolo, "; ".join(motivi))
                continue
            accesi = segnali(coppia, holder_ora, holder_prima, self.r)
            if len(accesi) < self.r["segnali"]["minimi_richiesti"]:
                giro["senza_segnali"] += 1
                self.filtra(indirizzo, simbolo, f"segnali {len(accesi)}/2 ({', '.join(accesi) or 'nessuno'})")
                continue
            permesso, perche = self.portafoglio.puo_aprire()
            if not permesso:
                giro["rifiutati_dimensione"] = giro.get("rifiutati_dimensione", 0) + 1
                self.filtra(indirizzo, simbolo, perche)
                continue
            motivo_ingresso = " + ".join(accesi) + " · rug check PASS"
            aperta, dettaglio = self.portafoglio.apri(coppia, simbolo, motivo_ingresso, adesso_ms,
                                                      float(rapporto.get("creatorBalance") or 0))
            if aperta:
                giro["comprati"] += 1
                self.scrivi("ENTRA", f"${simbolo} {dettaglio} · motivo: {motivo_ingresso} · {coppia.get('url', '')}")
            else:
                giro["rifiutati_dimensione"] = giro.get("rifiutati_dimensione", 0) + 1
                self.filtra(indirizzo, simbolo, dettaglio)

    def filtra(self, token: str, simbolo: str, motivo: str, scrivi: bool = True) -> None:
        chiave = motivo.split(" (")[0].split("$")[0].strip()
        if self.filtrati.get(token) != chiave:
            self.conteggio_filtri[chiave] = self.conteggio_filtri.get(chiave, 0) + 1
            if scrivi:
                self.scrivi("FILTRATO", f"${simbolo} non comprato · motivo: {motivo}")
        self.filtrati[token] = chiave

    # --- ESECUTORE -----------------------------------------------------------
    def controlla_posizioni(self) -> None:
        token = list(self.portafoglio.posizioni)
        coppie = self.fonti.coppie(token)
        controlla_svil = time.time() - self.ultimo_controllo_svil >= 60
        if controlla_svil:
            self.ultimo_controllo_svil = time.time()
            for t in token:
                try:
                    self.saldi_svil[t] = float(self.fonti.rapporto_rugcheck(t).get("creatorBalance") or 0)
                except Exception:
                    self.saldi_svil.pop(t, None)
        for t in token:
            simbolo = self.portafoglio.posizioni[t].simbolo
            coppia = coppie.get(t)
            if not coppia or not coppia.get("priceUsd"):
                # un buco nei dati non è un rug: si aspetta fino a 3 controlli di fila
                self.dati_mancanti[t] = self.dati_mancanti.get(t, 0) + 1
                if self.dati_mancanti[t] < 3:
                    self.scrivi("ATTESA", f"${simbolo} dati mancanti ({self.dati_mancanti[t]}/3)")
                    continue
            else:
                self.dati_mancanti.pop(t, None)
            saldo = self.saldi_svil.get(t) if controlla_svil else None
            for riga in self.portafoglio.aggiorna(t, coppia, _ms(), saldo):
                if riga.startswith("ESCE "):
                    self.scrivi("ESCE", riga.removeprefix("ESCE "))
                else:
                    self.scrivi("PARZIALE", f"${simbolo} {riga}")

    # --- DIARIO e CAPITALE ---------------------------------------------------
    def scrivi(self, tipo: str, testo: str) -> None:
        riga = f"{datetime.now(ITALIA):%H:%M:%S} {tipo:<9} {testo}"
        print(riga, flush=True)
        with (self.cartella / "diario.log").open("a", encoding="utf-8") as f:
            f.write(riga + "\n")

    def salva(self) -> None:
        stato = {"portafoglio": self.portafoglio.a_dizionario(), "holder": self.holder,
                 "conteggio_filtri": self.conteggio_filtri, "visti": sorted(self.visti),
                 "cambio_eur_usd": self.cambio,
                 "attivita": self.attivita, "contatori": self.contatori}
        (self.cartella / "stato.json").write_text(json.dumps(stato, indent=1))
        (self.cartella / "cruscotto.md").write_text(self.cruscotto(), encoding="utf-8")

    def _carica_o_crea(self) -> Portafoglio:
        file = self.cartella / "stato.json"
        if file.exists():
            stato = json.loads(file.read_text())
            self.holder = stato["holder"]
            self.conteggio_filtri = stato["conteggio_filtri"]
            self.visti = set(stato["visti"])
            self.cambio = stato["cambio_eur_usd"]
            self.attivita = stato.get("attivita", [])
            self.contatori.update(stato.get("contatori", {}))
            return Portafoglio.da_dizionario(self.r, stato["portafoglio"])
        self.cambio = self.fonti.euro_in_dollari()
        dollari = self.r["capitale_euro"] * self.cambio
        return Portafoglio(self.r, contanti=dollari, capitale_iniziale=dollari, picco=dollari)

    def cruscotto(self) -> str:
        p = self.portafoglio
        vinte = sum(c.guadagno > 0 for c in p.chiusure)
        righe = [
            f"# Cruscotto notte — aggiornato {datetime.now(ITALIA):%d/%m %H:%M:%S}",
            "",
            "**SOLDI FINTI, PREZZI VERI.**",
            "",
            f"| Capitale | Operazioni | Vinte | Perse | Token visti | Stato |",
            "|---|---|---|---|---|---|",
            f"| ${p.capitale():.2f} (≈ {p.capitale() / self.cambio:.2f}€) su ${p.capitale_iniziale:.2f} "
            f"| {len(p.chiusure)} | {vinte} | {len(p.chiusure) - vinte} | {len(self.visti)} | {p.fermo or 'attivo'} |",
            "",
            "## Posizioni aperte",
            "",
        ]
        righe += [f"- ${x.simbolo}: speso ${x.speso_usd:.2f}, valore ${x.quantita * x.ultimo_prezzo:.2f}, "
                  f"massimo {x.massimo / x.prezzo_medio:.2f}x · {x.motivo}" for x in p.posizioni.values()] or ["Nessuna."]
        return "\n".join(righe) + "\n"

    def scrivi_riepilogo(self) -> None:
        p = self.portafoglio
        chiusure = sorted(p.chiusure, key=lambda c: c.guadagno)
        per_moneta: dict[str, float] = {}
        for c in chiusure:
            per_moneta[c.simbolo] = per_moneta.get(c.simbolo, 0) + c.guadagno
        commissioni_stimate = sum(c.speso_usd for c in chiusure) * 2 * (
            self.r["costi"]["commissione_dex_pct"] + self.r["costi"]["slippage_ritardo_pct"]) / 100
        fine = p.capitale()
        righe = [
            f"# Riepilogo notte — {datetime.now(ITALIA):%d/%m/%Y %H:%M}",
            "",
            "**SOLDI FINTI, PREZZI VERI** (DexScreener + RugCheck). Costi e slippage sono stime da `regole.yaml`.",
            "",
            "| | |",
            "|---|---|",
            f"| Inizio | ${p.capitale_iniziale:.2f} (≈ {p.capitale_iniziale / self.cambio:.2f}€) |",
            f"| Fine | ${fine:.2f} (≈ {fine / self.cambio:.2f}€) |",
            f"| Risultato | {fine - p.capitale_iniziale:+.2f}$ ({(fine / p.capitale_iniziale - 1) * 100:+.1f}%) |",
            f"| Operazioni | {len(chiusure)} ({sum(c.guadagno > 0 for c in chiusure)} vinte, {sum(c.guadagno <= 0 for c in chiusure)} perse) |",
            f"| Costi stimati (commissioni + ritardo) | circa ${commissioni_stimate:.2f} |",
            f"| Token guardati | {len(self.visti)} |",
            f"| Stop della notte | {p.fermo or 'mai scattato'} |",
            "",
        ]
        if chiusure:
            migliore, peggiore = chiusure[-1], chiusure[0]
            righe += [
                f"**Migliore:** ${migliore.simbolo} {migliore.guadagno:+.2f}$ ({migliore.motivo_uscita})",
                "",
                f"**Peggiore:** ${peggiore.simbolo} {peggiore.guadagno:+.2f}$ ({peggiore.motivo_uscita})",
                "",
                "**Le 3 monete che hanno reso di più:** " + ", ".join(
                    f"${s} {g:+.2f}$" for s, g in sorted(per_moneta.items(), key=lambda x: -x[1])[:3]),
                "",
                "## Tutte le operazioni",
                "",
                "| Moneta | Entrata | Uscita | Speso | Incassato | Risultato | Perché è entrato | Perché è uscito |",
                "|---|---|---|---|---|---|---|---|",
            ]
            righe += [f"| ${c.simbolo} | {_ora(c.aperta_ms)} | {_ora(c.chiusa_ms)} | ${c.speso_usd:.2f} | ${c.incassato_usd:.2f} "
                      f"| {c.guadagno:+.2f}$ | {c.motivo_ingresso} | {c.motivo_uscita} |" for c in p.chiusure]
            righe.append("")
        righe += ["## Perché i token sono stati scartati", "", "| Motivo | Token |", "|---|---|"]
        righe += [f"| {m} | {n} |" for m, n in sorted(self.conteggio_filtri.items(), key=lambda x: -x[1])]
        righe += ["", f"Cambio usato: 1€ = ${self.cambio:.4f} (Binance EURUSDT all'avvio)."]
        (self.cartella / "riepilogo.md").write_text("\n".join(righe) + "\n", encoding="utf-8")
        self.scrivi("RIEPILOGO", f"scritto in {self.cartella / 'riepilogo.md'}")


def _ms() -> int:
    return int(time.time() * 1000)


def _ora(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, ITALIA).strftime("%H:%M")


def calcola_fine(regole: dict, minuti: int | None) -> datetime:
    adesso = datetime.now(ITALIA)
    if minuti:
        return adesso + timedelta(minutes=minuti)
    ora, minuto = map(int, regole["fine"].split(":"))
    fine = adesso.replace(hour=ora, minute=minuto, second=0, microsecond=0)
    return fine if fine > adesso else fine + timedelta(days=1)


def unisci(base: dict, modifiche: dict) -> dict:
    """Copia di base con le modifiche applicate, anche nei livelli interni."""
    risultato = dict(base)
    for chiave, valore in modifiche.items():
        if isinstance(valore, dict) and isinstance(base.get(chiave), dict):
            risultato[chiave] = unisci(base[chiave], valore)
        elif chiave != "descrizione":
            risultato[chiave] = valore
    return risultato


def data_della_notte() -> str:
    """Le ore dopo mezzanotte appartengono alla notte iniziata il giorno prima."""
    adesso = datetime.now(ITALIA)
    return (adesso - timedelta(days=1) if adesso.hour < 12 else adesso).strftime("%Y-%m-%d")


if __name__ == "__main__":
    argomenti = argparse.ArgumentParser(description="Esperimento notturno memecoin su carta")
    argomenti.add_argument("--minuti", type=int, help="durata in minuti (default: fino all'ora di fine)")
    argomenti.add_argument("--max-minuti", type=int, help="ferma questo turno dopo N minuti senza chiudere le posizioni")
    argomenti.add_argument("--variante", help="strategia alternativa da regole.yaml → notte_meme_varianti (es. b)")
    argomenti.add_argument("--nome", help="nome della cartella dei risultati (default: data della notte)")
    a = argomenti.parse_args()
    tutte = carica_regole()
    regole = tutte["notte_meme"]
    if a.variante:
        regole = unisci(regole, tutte["notte_meme_varianti"][a.variante])
    nome = a.nome or data_della_notte() + (f"-{a.variante}" if a.variante else "")
    cartella = RADICE / "risultati" / "notte" / nome
    pausa = datetime.now(ITALIA) + timedelta(minutes=a.max_minuti) if a.max_minuti else None
    Notte(regole, calcola_fine(regole, a.minuti), cartella, pausa=pausa).gira()
