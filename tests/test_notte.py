import pytest

from bot.notte.controlli import controllo_truffe, insegue, segnali, top10_pct, universo
from bot.notte.portafoglio import Portafoglio
from bot.regole import carica_regole

R = carica_regole()["notte_meme"]
ORA = 1_800_000_000_000
MINUTO = 60_000


def coppia(prezzo=1.0, liquidita=100_000, **altro):
    base = {
        "dexId": "pumpswap", "pairCreatedAt": ORA - 3_600_000, "priceUsd": str(prezzo),
        "liquidity": {"usd": liquidita}, "volume": {"m5": 30_000, "h1": 60_000},
        "txns": {"m5": {"buys": 80, "sells": 20}}, "priceChange": {"h1": 50, "m5": 2},
        "baseToken": {"address": "TOKEN", "symbol": "PROVA"},
    }
    base.update(altro)
    return base


def rapporto_pulito(**altro):
    base = {
        "mintAuthority": None, "freezeAuthority": None, "rugged": False, "totalHolders": 1000,
        "token": {"supply": 1_000_000}, "creatorBalance": 0, "transferFee": {"pct": 0},
        "topHolders": [{"owner": "POOL", "address": "P", "pct": 40}] + [{"owner": f"h{i}", "address": f"a{i}", "pct": 2} for i in range(12)],
        "knownAccounts": {"POOL": {"type": "AMM"}},
        "markets": [{"lp": {"quoteUSD": 50_000, "lpLockedPct": 100}}],
        "graphInsidersDetected": 0, "risks": [],
    }
    base.update(altro)
    return base


def portafoglio():
    return Portafoglio(R, contanti=55.0, capitale_iniziale=55.0, picco=55.0)


# --- scanner ------------------------------------------------------------

def test_universo_scarta_liquidita_bassa_e_coppie_vecchie():
    assert universo(coppia(), R, ORA)[0]
    assert not universo(coppia(liquidity={"usd": 10_000}), R, ORA)[0]
    assert not universo(coppia(pairCreatedAt=ORA - 7 * 3_600_000), R, ORA)[0]
    assert not universo(coppia(priceUsd=None), R, ORA)[0]


def test_segnali_volume_e_acquisti():
    accesi = segnali(coppia(), holder_ora=1100, holder_prima=1000, regole=R)
    assert len(accesi) == 3   # volume 6x, acquisti 80%, holder +10%


def test_niente_inseguimento():
    assert insegue(coppia(priceChange={"h1": 400, "m5": 5}), R)
    assert not insegue(coppia(priceChange={"h1": 400, "m5": -10}), R)


# --- controllo truffe ---------------------------------------------------

def test_token_pulito_passa_e_il_pool_non_conta_nei_top10():
    assert top10_pct(rapporto_pulito()) == pytest.approx(20)
    assert controllo_truffe(rapporto_pulito(), R) == (True, [])


@pytest.mark.parametrize("modifica", [
    {"mintAuthority": "X"},
    {"freezeAuthority": "X"},
    {"creatorBalance": 60_000},                                   # sviluppatore al 6%
    {"markets": [{"lp": {"quoteUSD": 50_000, "lpLockedPct": 10}}]},
    {"risks": [{"name": "Creator history of rugged tokens", "level": "danger"}]},
    {"graphInsidersDetected": 3},
    {"totalHolders": 120},
])
def test_token_sospetti_bocciati(modifica):
    passa, motivi = controllo_truffe(rapporto_pulito(**modifica), R)
    assert not passa and motivi


# --- esecutore ----------------------------------------------------------

def apri(p, prezzo=1.0):
    ok, _ = p.apri(coppia(prezzo), "PROVA", "test", ORA, saldo_sviluppatore=0)
    assert ok
    return p.posizioni["TOKEN"]


def test_usa_33_percento_e_paga_i_costi():
    p = portafoglio()
    pos = apri(p)
    p.aggiorna("TOKEN", coppia(1.0), ORA + MINUTO, None)  # compra la seconda metà
    assert pos.speso_usd == pytest.approx(55 * 0.33)
    assert pos.prezzo_medio > 1.0                         # slippage
    assert p.capitale() < 55                              # i costi si pagano subito


def test_stop_meno_12():
    p = portafoglio()
    apri(p)
    p.aggiorna("TOKEN", coppia(1.0), ORA + MINUTO, None)
    righe = p.aggiorna("TOKEN", coppia(0.85), ORA + 2 * MINUTO, None)
    assert "stop" in righe[0] and not p.posizioni
    assert p.chiusure[0].guadagno < -0.12 * p.chiusure[0].speso_usd


def test_scala_di_vendita_2x_4x_e_trailing():
    p = portafoglio()
    apri(p)
    p.aggiorna("TOKEN", coppia(1.0), ORA + MINUTO, None)
    assert "40%" in p.aggiorna("TOKEN", coppia(2.2), ORA + 2 * MINUTO, None)[0]
    assert "30%" in p.aggiorna("TOKEN", coppia(4.5), ORA + 3 * MINUTO, None)[0]
    assert p.aggiorna("TOKEN", coppia(5.0), ORA + 40 * MINUTO, None) == []   # nessun tempo massimo dopo il 2x
    assert "trailing" in p.aggiorna("TOKEN", coppia(3.7), ORA + 41 * MINUTO, None)[0]
    assert p.chiusure[0].guadagno > 0


def test_tempo_scaduto_dopo_25_minuti():
    p = portafoglio()
    apri(p)
    righe = p.aggiorna("TOKEN", coppia(1.1), ORA + 26 * MINUTO, None)
    assert "tempo" in righe[0]


def test_rug_recupera_solo_10_percento():
    p = portafoglio()
    apri(p)
    p.aggiorna("TOKEN", coppia(1.0, liquidita=5_000), ORA + MINUTO, None)
    assert p.chiusure[0].incassato_usd < p.chiusure[0].speso_usd * 0.15


def test_sviluppatore_vende():
    p = portafoglio()
    p.apri(coppia(), "PROVA", "test", ORA, saldo_sviluppatore=1000)
    righe = p.aggiorna("TOKEN", coppia(1.0), ORA + MINUTO, saldo_sviluppatore=10)
    assert "sviluppatore" in righe[0]


def test_dimezza_dopo_2_perdite_e_max_2_posizioni():
    p = portafoglio()
    p.perdite_di_fila = 2
    assert p.dimensione_usd() == pytest.approx(55 * 0.165)
    apri(p)
    p.posizioni["ALTRO"] = p.posizioni["TOKEN"]
    assert not p.puo_aprire()[0]


def test_stop_della_giornata_si_misura_dalla_partenza():
    p = portafoglio()
    p.picco = 80                       # un massimo alto non basta più a fermare il bot
    assert p.aggiorna_picco() is None and p.puo_aprire()[0]
    p.contanti = 55.0 * 0.49           # sotto il 50% della partenza: fermo
    assert p.aggiorna_picco()
    assert not p.puo_aprire()[0]


def test_salva_e_ricarica():
    p = portafoglio()
    apri(p)
    copia = Portafoglio.da_dizionario(R, p.a_dizionario())
    assert copia.capitale() == pytest.approx(p.capitale())


# --- giro completo con dati finti -----------------------------------------

class FontiFinte:
    def __init__(self, coppie, rapporto):
        self._coppie, self._rapporto = coppie, rapporto

    def token_recenti(self):
        return list(self._coppie)

    def coppie(self, indirizzi):
        return {t: c for t, c in self._coppie.items() if t in indirizzi}

    def rapporto_rugcheck(self, token):
        return self._rapporto

    def euro_in_dollari(self):
        return 1.1


def test_un_giro_dello_scanner_compra_e_conta(tmp_path):
    import time
    from datetime import datetime, timedelta
    from bot.notte.__main__ import ITALIA, Notte

    adesso = int(time.time() * 1000)
    buona = coppia(pairCreatedAt=adesso - 3_600_000)
    vecchia = dict(coppia(pairCreatedAt=adesso - 30 * 3_600_000), baseToken={"address": "VECCHIA", "symbol": "OLD"})
    notte = Notte(R, datetime.now(ITALIA) + timedelta(minutes=1), tmp_path,
                  fonti=FontiFinte({"TOKEN": buona, "VECCHIA": vecchia}, rapporto_pulito()))
    notte.cerca()
    notte.salva()
    assert "TOKEN" in notte.portafoglio.posizioni
    assert notte.contatori == {"guardati": 2, "nel_perimetro": 1, "controllati": 1, "bocciati": 0,
                               "senza_segnali": 0, "rifiutati_dimensione": 0, "comprati": 1}
    assert notte.attivita[-1]["comprati"] == 1
    assert "ENTRA" in (tmp_path / "diario.log").read_text()


def test_varianti_b_c_d_coincidono_con_la_griglia_del_laboratorio():
    from bot.notte.__main__ import unisci
    from bot.notte.laboratorio import varianti
    tutte = carica_regole()
    b = unisci(tutte["notte_meme"], tutte["notte_meme_varianti"]["b"])
    assert b["controllo_truffe"]["no_mint_authority"] and b["dimensione"]["max_posizioni"] == 2
    assert "descrizione" not in b
    griglia = dict(varianti(tutte))
    assert griglia["B · Pazienti"] == griglia["liq ≥5k · vol5m ≥5k · truffe senza LP · stop -20% · max 60 min"]
    assert griglia["C · Stop stretto"] == griglia["liq ≥5k · vol5m ≥1k · truffe senza LP · stop -12% · max 25 min"]
    assert griglia["D · Piccole e veloci"] == griglia["liq ≥5k · vol5m ≥1k · truffe senza LP · stop -20% · max 25 min"]
