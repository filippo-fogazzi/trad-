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


def test_stop_della_notte_al_30_percento():
    p = portafoglio()
    p.picco = 80
    assert p.aggiorna_picco()
    assert not p.puo_aprire()[0]


def test_salva_e_ricarica():
    p = portafoglio()
    apri(p)
    copia = Portafoglio.da_dizionario(R, p.a_dizionario())
    assert copia.capitale() == pytest.approx(p.capitale())
