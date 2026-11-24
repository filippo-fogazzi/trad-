"""SCUDO: controlla ogni operazione prima che parta. È codice fisso, non intelligenza artificiale:
non si può convincere a fare un'eccezione.

Regole (tutte da regole.yaml):
- dimensione: si rischia al massimo l'1% del capitale tra ingresso e stop
- esposizione: una operazione non usa più del 50% del capitale
- ordine minimo: sotto i 5€ l'ordine non parte
- stop giornaliero: -3% nella giornata, oppure 3 perdite di fila → niente nuove operazioni fino a domani
- interruttore: se esiste il file STOP nella cartella del progetto, si ferma tutto
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from bot.regole import RADICE

FILE_INTERRUTTORE = RADICE / "STOP"


@dataclass
class Scudo:
    regole: dict
    controlla_interruttore: bool = True
    giorno: date | None = None
    capitale_inizio_giorno: float = 0.0
    perdite_di_fila: int = 0
    motivo_blocco: str | None = None
    giorni_bloccati: set = field(default_factory=set)

    def aggiorna_momento(self, quando: datetime, capitale: float) -> None:
        """Da chiamare a ogni candela: al cambio di giorno (ora italiana) i limiti ripartono."""
        oggi = quando.astimezone(ZoneInfo(self.regole["rischio"]["fuso_orario"])).date()
        if oggi != self.giorno:
            self.giorno = oggi
            self.capitale_inizio_giorno = capitale
            self.perdite_di_fila = 0
            self.motivo_blocco = None

    def registra_esito(self, guadagno: float, capitale: float) -> None:
        r = self.regole["rischio"]
        self.perdite_di_fila = self.perdite_di_fila + 1 if guadagno < 0 else 0
        perdita_oggi_pct = (self.capitale_inizio_giorno - capitale) / self.capitale_inizio_giorno * 100
        if perdita_oggi_pct >= r["stop_giornaliero_pct"]:
            self._blocca(f"perdita giornaliera {perdita_oggi_pct:.1f}% ≥ {r['stop_giornaliero_pct']}%")
        elif self.perdite_di_fila >= r["max_perdite_di_fila"]:
            self._blocca(f"{self.perdite_di_fila} perdite di fila")

    def puo_aprire(self) -> tuple[bool, str]:
        if self.controlla_interruttore and FILE_INTERRUTTORE.exists():
            return False, "interruttore STOP attivo"
        if self.motivo_blocco:
            return False, f"bloccato per oggi: {self.motivo_blocco}"
        return True, "ok"

    def dimensiona(
        self, capitale: float, prezzo_ingresso: float, stop: float, commissione: float = 0.0, slippage: float = 0.0
    ) -> tuple[float, str]:
        """Ritorna (quantità da comprare, motivo). Quantità 0 = operazione rifiutata.
        La perdita allo stop include commissioni e slippage, così non supera mai l'1%
        (salvo un buco di prezzo che salta lo stop)."""
        r = self.regole["rischio"]
        if stop >= prezzo_ingresso or stop <= 0:
            return 0.0, "stop non valido"
        rischio_euro = capitale * r["per_operazione_pct"] / 100
        uscita_allo_stop = stop * (1 - slippage)
        perdita_per_unita = prezzo_ingresso - uscita_allo_stop + (prezzo_ingresso + uscita_allo_stop) * commissione
        quantita = rischio_euro / perdita_per_unita
        massimo_euro = capitale * r["max_esposizione_pct"] / 100
        if quantita * prezzo_ingresso > massimo_euro:
            quantita = massimo_euro / prezzo_ingresso
        if quantita * prezzo_ingresso < r["ordine_minimo_euro"]:
            return 0.0, f"ordine sotto il minimo di {r['ordine_minimo_euro']}€"
        return quantita, "ok"

    def _blocca(self, motivo: str) -> None:
        self.motivo_blocco = motivo
        self.giorni_bloccati.add(self.giorno)
