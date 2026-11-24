"""DIMENSIONE, ESECUTORE e CAPITALE su carta.

Ogni acquisto e vendita paga slippage, commissione del DEX e commissione di rete (stime da
regole.yaml). Le uscite sono quelle del prompt: -12%, vendi 40% a 2x, 30% a 4x, il resto
con trailing del 25%, tempo massimo 25 minuti, uscita se la liquidità sparisce o lo
sviluppatore vende.
"""
from dataclasses import asdict, dataclass, field


@dataclass
class Posizione:
    token: str
    simbolo: str
    aperta_ms: int
    motivo: str
    liquidita_ingresso: float
    saldo_sviluppatore: float
    speso_usd: float = 0.0
    incassato_usd: float = 0.0
    quantita: float = 0.0
    quantita_iniziale: float = 0.0
    prezzo_medio: float = 0.0
    da_comprare_usd: float = 0.0      # seconda metà dell'ingresso, comprata al controllo successivo
    massimo: float = 0.0
    venduto_2x: bool = False
    venduto_4x: bool = False
    ultimo_prezzo: float = 0.0


@dataclass
class Chiusura:
    simbolo: str
    token: str
    aperta_ms: int
    chiusa_ms: int
    speso_usd: float
    incassato_usd: float
    motivo_ingresso: str
    motivo_uscita: str

    @property
    def guadagno(self) -> float:
        return self.incassato_usd - self.speso_usd


@dataclass
class Portafoglio:
    regole: dict
    contanti: float
    capitale_iniziale: float
    posizioni: dict[str, Posizione] = field(default_factory=dict)
    chiusure: list[Chiusura] = field(default_factory=list)
    picco: float = 0.0
    perdite_di_fila: int = 0
    fermo: str | None = None

    # --- capitale ---------------------------------------------------------
    def capitale(self) -> float:
        return self.contanti + sum(p.quantita * p.ultimo_prezzo for p in self.posizioni.values())

    def aggiorna_picco(self) -> str | None:
        """Ritorna un messaggio se scatta lo stop della notte."""
        valore = self.capitale()
        self.picco = max(self.picco, valore)
        limite = self.regole["uscite"]["stop_notte_pct"]
        if not self.fermo and valore <= self.picco * (1 - limite / 100):
            self.fermo = f"capitale sceso del {limite}% dal massimo (${self.picco:.2f} → ${valore:.2f})"
            return self.fermo
        return None

    # --- dimensione -------------------------------------------------------
    def puo_aprire(self) -> tuple[bool, str]:
        if self.fermo:
            return False, f"bot fermo: {self.fermo}"
        if len(self.posizioni) >= self.regole["dimensione"]["max_posizioni"]:
            return False, "già 2 posizioni aperte"
        return True, "ok"

    def dimensione_usd(self) -> float:
        d = self.regole["dimensione"]
        quota = d["pct_capitale"] / 100
        if self.perdite_di_fila >= d["dimezza_dopo_perdite"]:
            quota /= 2
        return min(self.capitale() * quota, self.contanti)

    # --- esecuzione -------------------------------------------------------
    def slippage_pct(self, usd: float, liquidita: float) -> float:
        """Ritardo + impatto sul pool (in un pool x*y=k, comprare usd sposta il prezzo di circa 2*usd/liquidità)."""
        impatto = 2 * usd / liquidita * 100 if liquidita > 0 else 100.0
        return self.regole["costi"]["slippage_ritardo_pct"] + impatto

    def apri(self, coppia: dict, simbolo: str, motivo: str, adesso_ms: int, saldo_sviluppatore: float) -> tuple[bool, str]:
        usd = self.dimensione_usd()
        prezzo = float(coppia["priceUsd"])
        liquidita = float(coppia["liquidity"]["usd"])
        slippage = self.slippage_pct(usd / 2, liquidita)
        if slippage > self.regole["costi"]["slippage_max_pct"]:
            return False, f"slippage stimato {slippage:.1f}% oltre il massimo"
        if usd < 1:
            return False, "capitale esaurito"
        pos = Posizione(coppia["baseToken"]["address"], simbolo, adesso_ms, motivo, liquidita, saldo_sviluppatore)
        pos.massimo = pos.ultimo_prezzo = prezzo
        self.posizioni[pos.token] = pos
        self._compra(pos, usd / 2, prezzo, liquidita)
        pos.da_comprare_usd = usd / 2
        return True, f"${usd:.2f} ({usd / max(self.capitale(), 1e-9) * 100:.0f}% del capitale), 1ª metà a slippage {slippage:.1f}%"

    def aggiorna(self, token: str, coppia: dict | None, adesso_ms: int, saldo_sviluppatore: float | None) -> list[str]:
        """Applica le regole di uscita a una posizione. Ritorna le righe da scrivere nel diario."""
        pos = self.posizioni[token]
        u, c = self.regole["uscite"], self.regole["costi"]
        eventi: list[str] = []
        liquidita = float(((coppia or {}).get("liquidity") or {}).get("usd") or 0)
        prezzo = float(coppia["priceUsd"]) if coppia and coppia.get("priceUsd") else None

        if prezzo is None or liquidita < pos.liquidita_ingresso * 0.2:
            recupero = pos.quantita * pos.prezzo_medio * (1 - c["perdita_se_rug_pct"] / 100)
            return [self._chiudi_tutto(pos, adesso_ms, "liquidità sparita (rug)", valore_fisso=recupero)]
        pos.ultimo_prezzo = prezzo
        pos.massimo = max(pos.massimo, prezzo)

        if saldo_sviluppatore is not None and saldo_sviluppatore < pos.saldo_sviluppatore:
            return [self._chiudi_tutto(pos, adesso_ms, "lo sviluppatore ha venduto", prezzo, liquidita)]
        if not pos.venduto_2x and prezzo <= pos.prezzo_medio * (1 - u["stop_pct"] / 100):
            return [self._chiudi_tutto(pos, adesso_ms, f"stop -{u['stop_pct']}% (prezzo {prezzo / pos.prezzo_medio - 1:+.0%})", prezzo, liquidita)]
        minuti = (adesso_ms - pos.aperta_ms) / 60_000
        if not pos.venduto_2x and minuti >= u["tempo_max_minuti"]:
            return [self._chiudi_tutto(pos, adesso_ms, f"tempo scaduto ({u['tempo_max_minuti']} min)", prezzo, liquidita)]

        if pos.da_comprare_usd > 0:
            self._compra(pos, min(pos.da_comprare_usd, self.contanti), prezzo, liquidita)
            pos.da_comprare_usd = 0.0
            eventi.append(f"seconda metà comprata a ${prezzo:.8g}")
        if not pos.venduto_2x and prezzo >= pos.prezzo_medio * u["vendi_40pct_a"]:
            self._vendi(pos, pos.quantita_iniziale * 0.4, prezzo, liquidita)
            pos.venduto_2x = True
            eventi.append(f"vende 40% a {u['vendi_40pct_a']:g}x")
        if pos.venduto_2x and not pos.venduto_4x and prezzo >= pos.prezzo_medio * u["vendi_30pct_a"]:
            self._vendi(pos, pos.quantita_iniziale * 0.3, prezzo, liquidita)
            pos.venduto_4x = True
            eventi.append(f"vende 30% a {u['vendi_30pct_a']:g}x")
        if pos.venduto_2x and prezzo <= pos.massimo * (1 - u["trailing_resto_pct"] / 100):
            eventi.append(self._chiudi_tutto(pos, adesso_ms, f"trailing -{u['trailing_resto_pct']}% dal massimo", prezzo, liquidita))
        return eventi

    def chiudi_tutto(self, adesso_ms: int, motivo: str) -> list[str]:
        return [self._chiudi_tutto(p, adesso_ms, motivo, p.ultimo_prezzo, p.liquidita_ingresso)
                for p in list(self.posizioni.values())]

    # --- interni ----------------------------------------------------------
    def _commissioni(self, usd: float) -> float:
        c = self.regole["costi"]
        return usd * c["commissione_dex_pct"] / 100 + c["rete_usd_per_ordine"]

    def _compra(self, pos: Posizione, usd: float, prezzo: float, liquidita: float) -> None:
        if usd <= 0:
            return
        prezzo_reale = prezzo * (1 + self.slippage_pct(usd, liquidita) / 100)
        quantita = (usd - self._commissioni(usd)) / prezzo_reale
        pos.prezzo_medio = (pos.prezzo_medio * pos.quantita + prezzo_reale * quantita) / (pos.quantita + quantita)
        pos.quantita += quantita
        pos.quantita_iniziale += quantita
        pos.speso_usd += usd
        self.contanti -= usd

    def _vendi(self, pos: Posizione, quantita: float, prezzo: float, liquidita: float) -> None:
        quantita = min(quantita, pos.quantita)
        lordo = quantita * prezzo
        netto = lordo * (1 - self.slippage_pct(lordo, liquidita) / 100) - self._commissioni(lordo)
        pos.quantita -= quantita
        pos.incassato_usd += max(netto, 0.0)
        self.contanti += max(netto, 0.0)

    def _chiudi_tutto(self, pos: Posizione, adesso_ms: int, motivo: str, prezzo: float = 0.0,
                      liquidita: float = 0.0, valore_fisso: float | None = None) -> str:
        if valore_fisso is not None:
            pos.incassato_usd += valore_fisso
            self.contanti += valore_fisso
            pos.quantita = 0.0
        elif pos.quantita > 0:
            self._vendi(pos, pos.quantita, prezzo, liquidita)
        chiusura = Chiusura(pos.simbolo, pos.token, pos.aperta_ms, adesso_ms, pos.speso_usd, pos.incassato_usd,
                            pos.motivo, motivo)
        self.chiusure.append(chiusura)
        self.perdite_di_fila = self.perdite_di_fila + 1 if chiusura.guadagno < 0 else 0
        del self.posizioni[pos.token]
        return f"ESCE ${pos.simbolo} {chiusura.guadagno:+.2f}$ motivo: {motivo}"

    # --- salvataggio ------------------------------------------------------
    def a_dizionario(self) -> dict:
        return {
            "contanti": self.contanti, "capitale_iniziale": self.capitale_iniziale, "picco": self.picco,
            "perdite_di_fila": self.perdite_di_fila, "fermo": self.fermo,
            "posizioni": [asdict(p) for p in self.posizioni.values()],
            "chiusure": [asdict(c) for c in self.chiusure],
        }

    @classmethod
    def da_dizionario(cls, regole: dict, d: dict) -> "Portafoglio":
        p = cls(regole, d["contanti"], d["capitale_iniziale"], picco=d["picco"],
                perdite_di_fila=d["perdite_di_fila"], fermo=d["fermo"])
        p.posizioni = {x["token"]: Posizione(**x) for x in d["posizioni"]}
        p.chiusure = [Chiusura(**x) for x in d["chiusure"]]
        return p
