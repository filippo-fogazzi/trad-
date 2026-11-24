"""LABORATORIO: prova ogni strategia su dati reali di Binance, con commissioni, slippage e
le regole dello Scudo, e dice quali passano l'esame e quali no.

Uso:  python -m bot.laboratorio
Risultato: risultati/laboratorio_AAAA-MM-GG.md
"""
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from bot.dati import carica_candele
from bot.regole import RADICE, carica_regole, categoria
from bot.scudo import Scudo
from bot.strategie import STRATEGIE, Strategia


@dataclass
class Operazione:
    entrata: pd.Timestamp
    uscita: pd.Timestamp
    prezzo_entrata: float
    prezzo_uscita: float
    quantita: float
    commissioni: float
    guadagno: float
    motivo_uscita: str


@dataclass
class Risultato:
    simbolo: str
    intervallo: str
    strategia: str
    operazioni: list[Operazione]
    capitale_iniziale: float
    capitale_finale: float
    max_drawdown_pct: float
    compra_e_tieni_pct: float
    guadagno_prima_meta: float
    guadagno_seconda_meta: float
    giorni_bloccati_scudo: int
    rifiutate_scudo: int

    @property
    def rendimento_pct(self) -> float:
        return (self.capitale_finale / self.capitale_iniziale - 1) * 100

    @property
    def vincenti_pct(self) -> float:
        if not self.operazioni:
            return 0.0
        return sum(o.guadagno > 0 for o in self.operazioni) / len(self.operazioni) * 100

    @property
    def profit_factor(self) -> float:
        vinto = sum(o.guadagno for o in self.operazioni if o.guadagno > 0)
        perso = -sum(o.guadagno for o in self.operazioni if o.guadagno < 0)
        if perso == 0:
            return float("inf") if vinto > 0 else 0.0
        return vinto / perso

    @property
    def commissioni(self) -> float:
        return sum(o.commissioni for o in self.operazioni)


def simula(candele: pd.DataFrame, strategia: Strategia, simbolo: str, intervallo: str, regole: dict) -> Risultato:
    segnali = strategia.calcola(candele)
    commissione = regole["costi"]["commissione_pct"] / 100
    slippage = regole["costi"]["slippage_pct"][categoria(simbolo, regole)] / 100
    scudo = Scudo(regole, controlla_interruttore=False)

    capitale = float(regole["capitale_euro"])
    picco, max_dd = capitale, 0.0
    operazioni: list[Operazione] = []
    rifiutate = 0
    posizione: dict | None = None

    def chiudi(i: int, prezzo: float, motivo: str) -> None:
        nonlocal capitale, posizione
        uscita = prezzo * (1 - slippage)
        comm_uscita = posizione["quantita"] * uscita * commissione
        guadagno = posizione["quantita"] * (uscita - posizione["prezzo"]) - posizione["comm"] - comm_uscita
        capitale += guadagno
        operazioni.append(
            Operazione(
                posizione["quando"], candele["apertura"].iat[i], posizione["prezzo"], uscita,
                posizione["quantita"], posizione["comm"] + comm_uscita, guadagno, motivo,
            )
        )
        scudo.registra_esito(guadagno, capitale)
        posizione = None

    for i in range(1, len(candele)):
        quando = candele["apertura"].iat[i]
        apertura, minimo, chiusura = (candele[k].iat[i] for k in ("open", "low", "close"))
        scudo.aggiorna_momento(quando.to_pydatetime(), capitale)

        # 1) uscite all'apertura (segnale della candela precedente, o prezzo già sotto lo stop)
        if posizione:
            if segnali["esci"].iat[i - 1]:
                chiudi(i, apertura, "segnale")
            elif strategia.max_candele and i - posizione["indice"] >= strategia.max_candele:
                chiudi(i, apertura, "tempo scaduto")
            elif apertura <= posizione["stop"]:
                chiudi(i, apertura, "stop (apertura sotto lo stop)")

        # 2) ingresso all'apertura, se lo Scudo lo permette
        if not posizione and segnali["entra"].iat[i - 1] and pd.notna(segnali["atr"].iat[i - 1]):
            permesso, _ = scudo.puo_aprire()
            prezzo = apertura * (1 + slippage)
            stop = prezzo - strategia.stop_atr * segnali["atr"].iat[i - 1]
            quantita, _ = scudo.dimensiona(capitale, prezzo, stop, commissione, slippage) if permesso else (0.0, "")
            if quantita > 0:
                posizione = {"quando": quando, "indice": i, "prezzo": prezzo, "stop": stop,
                             "quantita": quantita, "comm": quantita * prezzo * commissione}
            else:
                rifiutate += 1

        # 3) stop toccato durante la candela (si assume sempre il caso peggiore)
        if posizione and minimo <= posizione["stop"]:
            chiudi(i, posizione["stop"], "stop")

        valore = capitale + (posizione["quantita"] * (chiusura - posizione["prezzo"]) - posizione["comm"] if posizione else 0)
        picco = max(picco, valore)
        max_dd = max(max_dd, (picco - valore) / picco * 100)

    if posizione:
        chiudi(len(candele) - 1, candele["close"].iat[-1], "fine del test")

    meta_tempo = candele["apertura"].iat[0] + (candele["apertura"].iat[-1] - candele["apertura"].iat[0]) / 2
    return Risultato(
        simbolo, intervallo, strategia.nome, operazioni, float(regole["capitale_euro"]), capitale, max_dd,
        (candele["close"].iat[-1] / candele["open"].iat[0] - 1) * 100,
        sum(o.guadagno for o in operazioni if o.uscita <= meta_tempo),
        sum(o.guadagno for o in operazioni if o.uscita > meta_tempo),
        len(scudo.giorni_bloccati), rifiutate,
    )


def verdetto(r: Risultato, regole: dict) -> tuple[bool, list[str]]:
    p = regole["promozione"]
    motivi = []
    if len(r.operazioni) < p["min_operazioni"]:
        motivi.append(f"solo {len(r.operazioni)} operazioni")
    if r.profit_factor < p["min_profit_factor"]:
        motivi.append(f"profit factor {r.profit_factor:.2f}")
    if r.max_drawdown_pct > p["max_drawdown_pct"]:
        motivi.append(f"drawdown {r.max_drawdown_pct:.1f}%")
    if p["positiva_in_entrambe_le_meta"] and (r.guadagno_prima_meta <= 0 or r.guadagno_seconda_meta <= 0):
        motivi.append("non positiva in entrambe le metà")
    return not motivi, motivi


def esegui(regole: dict) -> tuple[list[Risultato], list[dict]]:
    risultati, fonti = [], []
    simboli = [s for gruppo in regole["mercati"].values() for s in gruppo]
    for intervallo, giorni in regole["timeframe"].items():
        for simbolo in simboli:
            candele, meta = carica_candele(simbolo, intervallo, giorni)
            fonti.append(meta)
            for strategia in STRATEGIE:
                risultati.append(simula(candele, strategia, simbolo, intervallo, regole))
            print(f"  ✓ {simbolo} {intervallo}: {len(candele)} candele")
    return risultati, fonti


def scrivi_rapporto(risultati: list[Risultato], fonti: list[dict], regole: dict) -> str:
    adesso = datetime.now(timezone.utc)
    promosse = [r for r in risultati if verdetto(r, regole)[0]]
    righe = [
        f"# Rapporto del Laboratorio — {adesso:%d/%m/%Y %H:%M} UTC",
        "",
        "Soldi finti, prezzi veri. Ogni operazione paga commissioni e slippage (stime da `regole.yaml`) "
        "e rispetta lo Scudo (1% di rischio, stop giornaliero −3%, stop dopo 3 perdite di fila).",
        "",
        f"**Promosse: {len(promosse)} su {len(risultati)} combinazioni.**",
        "",
    ]
    if promosse:
        righe += ["Promosse (vanno ancora provate 2 settimane su carta, dal vivo):", ""]
        righe += [f"- {r.strategia} su {r.simbolo} {r.intervallo}: {r.rendimento_pct:+.1f}%, "
                  f"profit factor {r.profit_factor:.2f}, {len(r.operazioni)} operazioni" for r in promosse]
        righe.append("")
    righe += ["## Le strategie testate", ""]
    righe += [f"- **{s.nome}**: {s.spiegazione}" for s in STRATEGIE]
    righe += [
        "",
        "## Come leggere le tabelle",
        "",
        "- **Rendimento**: quanto è cambiato il capitale di 500€, dopo tutti i costi.",
        "- **Compra e tieni**: quanto avresti fatto comprando all'inizio e non toccando nulla. Se la strategia fa peggio, non serve.",
        "- **Profit factor**: euro guadagnati per ogni euro perso. Sotto 1 = perde soldi.",
        "- **Drawdown**: la discesa peggiore dal punto più alto del capitale.",
        "- **Commissioni**: quanto è andato a Binance.",
        "",
    ]
    for intervallo in regole["timeframe"]:
        righe += [
            f"## Grafico {intervallo} (ultimi {regole['timeframe'][intervallo]} giorni)",
            "",
            "| Moneta | Strategia | Operazioni | Vincenti | Profit factor | Rendimento | Compra e tieni | Drawdown | Commissioni | Esito |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in (x for x in risultati if x.intervallo == intervallo):
            ok, motivi = verdetto(r, regole)
            esito = "✅ promossa" if ok else "❌ " + ", ".join(motivi)
            righe.append(
                f"| {r.simbolo} | {r.strategia} | {len(r.operazioni)} | {r.vincenti_pct:.0f}% | {r.profit_factor:.2f} "
                f"| {r.rendimento_pct:+.1f}% | {r.compra_e_tieni_pct:+.1f}% | {r.max_drawdown_pct:.1f}% "
                f"| {r.commissioni:.2f}€ | {esito} |"
            )
        righe.append("")
    righe += [
        "## Fonti dei dati",
        "",
        "| Moneta | Grafico | Da | A | Candele | Scaricato il (UTC) |",
        "|---|---|---|---|---|---|",
    ]
    righe += [f"| {m['simbolo']} | {m['intervallo']} | {m['prima_candela'][:16]} | {m['ultima_candela'][:16]} "
              f"| {m['numero_candele']} | {m['scaricato_il'][:16]} |" for m in fonti]
    righe += ["", f"Fonte: `{fonti[0]['fonte']}` (dati pubblici di Binance)." if fonti else ""]

    cartella = RADICE / "risultati"
    cartella.mkdir(exist_ok=True)
    percorso = cartella / f"laboratorio_{adesso:%Y-%m-%d}.md"
    percorso.write_text("\n".join(righe), encoding="utf-8")
    return str(percorso)


if __name__ == "__main__":
    regole = carica_regole()
    print("Laboratorio: scarico i dati reali da Binance e provo le strategie...")
    risultati, fonti = esegui(regole)
    print(f"Rapporto scritto in {scrivi_rapporto(risultati, fonti, regole)}")
