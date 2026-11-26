import pytest

from bot.notte.laboratorio import simula, statistiche
from bot.regole import carica_regole

R = carica_regole()["notte_meme"]
T0 = 1_800_000_000  # secondi


def foto(prezzo=1.0, liquidita=100_000):
    return {"ms": T0 * 1000, "coppia": {"priceUsd": str(prezzo), "liquidity": {"usd": liquidita}}}


def candele(*righe):
    """righe = (open, high, low, close), una per minuto dopo l'ingresso"""
    return [[T0 + 60 * i, o, h, l, c, 1000] for i, (o, h, l, c) in enumerate(righe)]


def test_stop_perde_circa_12_percento_piu_costi():
    esito = simula(R, foto(), candele((1, 1.02, 0.8, 0.85)), puntata_usd=18)
    assert "stop" in esito["motivo"]
    assert -18 < esito["ritorno_pct"] < -12


def test_scala_2x_e_trailing_guadagna():
    esito = simula(R, foto(), candele((1, 1.1, 0.99, 1.05), (1.05, 2.2, 1.04, 2.1), (2.1, 3.0, 2.0, 2.9), (2.9, 2.9, 2.0, 2.1)), 18)
    assert "trailing" in esito["motivo"] and esito["ritorno_pct"] > 50


def test_tempo_scaduto():
    righe = [(1, 1.05, 0.97, 1.0)] * 30
    esito = simula(R, foto(), candele(*righe), 18)
    assert "tempo" in esito["motivo"] and esito["minuti"] == 25


def test_rug_perde_90_percento():
    esito = simula(R, foto(), candele((1, 1, 0.01, 0.01)), 18)
    assert "rug" in esito["motivo"] and esito["ritorno_pct"] < -89


def test_nessuno_scambio_conta_come_rug():
    assert simula(R, foto(), [], 18)["ritorno_pct"] < -89


def test_slippage_troppo_alto_non_compra():
    assert simula(R, foto(liquidita=500), candele((1, 1, 1, 1)), 18) is None


def test_statistiche_massimo_due_posizioni():
    ops = [{"ms": T0 * 1000 + i, "minuti": 30, "ritorno_pct": 10} for i in range(3)]
    s = statistiche(ops, R, 55)
    assert s["eseguite"] == 2 and s["n"] == 3


def test_scarica_riprova_dopo_troppe_richieste(monkeypatch):
    import bot.notte.laboratorio as lab

    class Risposta:
        def __init__(self, codice):
            self.status_code = codice

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"attributes": {"ohlcv_list": [[2, 1, 1, 1, 1, 5], [1, 1, 1, 1, 1, 5]]}}}

    codici = iter([429, 429, 200])
    http = type("Http", (), {"get": lambda self, *a, **k: Risposta(next(codici))})()
    monkeypatch.setattr(lab.time, "sleep", lambda s: None)
    assert lab._scarica(http, "pool", 10, 0, lab.time.time() + 60) == [[1, 1, 1, 1, 1, 5], [2, 1, 1, 1, 1, 5]]


def test_le_fette_coprono_tutti_i_token(monkeypatch, tmp_path):
    import bot.notte.laboratorio as lab
    monkeypatch.setattr(lab, "CARTELLA_CANDELE", tmp_path)
    foto = [{"token": f"T{i}", "ms": 0, "coppia": {"pairAddress": f"P{i}"}} for i in range(40)]
    for i in range(40):
        (tmp_path / f"P{i}_0.json").write_text("[]")
    fette = [set(lab.scarica_candele(foto, 10**12, parte=k, parti=4)) for k in range(4)]
    assert set().union(*fette) == {f"T{i}" for i in range(40)}
    assert sum(len(f) for f in fette) == 40


def test_pulisci_toglie_i_picchi_impossibili_ma_tiene_i_crolli():
    from bot.notte.laboratorio import pulisci
    candele = [[0, 1, 1.1, 0.9, 1.0, 5], [60, 1, 1.2, 1, 1.1, 5], [120, 1.1, 2500, 1.1, 2500, 1],
               [180, 1.1, 30, 0.01, 0.02, 9]]
    assert pulisci(candele) == [[0, 1, 1.1, 0.9, 1.0, 5], [60, 1, 1.2, 1, 1.1, 5], [180, 1.1, 1.1, 0.01, 0.02, 9]]


def test_compra_al_prezzo_del_minuto_dopo_se_la_foto_e_in_ritardo():
    # la foto dice 1.0 ma il minuto dopo si apre a 1.1: il bot vero paga 1.1, quindi a 1.1 non guadagna nulla
    righe = [(1.1, 1.12, 1.09, 1.1)] * 30
    esito = simula(R, foto(prezzo=1.0), candele(*righe), 18)
    assert esito["ritorno_pct"] < -2


def test_liquidita_ritirata_conta_come_rug_anche_se_il_prezzo_resta_fermo():
    # il prezzo non crolla (nessuna compravendita dopo il ritiro), ma la liquidità è sparita al minuto 5
    righe = [(1, 1.03, 0.99, 1.0)] * 5
    esito = simula(R, foto(), candele(*righe), 18, rug_s=T0 + 5 * 60)
    assert "rug" in esito["motivo"] and esito["ritorno_pct"] < -89


def test_se_il_tempo_scade_prima_del_rug_il_bot_e_gia_uscito():
    righe = [(1, 1.03, 0.99, 1.0)] * 30
    esito = simula(R, foto(), candele(*righe), 18, rug_s=T0 + 40 * 60)
    assert "tempo" in esito["motivo"] and esito["ritorno_pct"] > -10


def test_registratore_scrive_il_rug_quando_la_liquidita_sparisce():
    import io, json
    from bot.notte.registro import Registratore

    class Fonti:
        def __init__(self):
            self.liq = 20_000
        def coppie(self, token):
            return {t: {"liquidity": {"usd": self.liq}, "priceUsd": "1"} for t in token}

    fonti, uscita = Fonti(), io.StringIO()
    r = Registratore(fonti, uscita, {"TOK": (0, 20_000.0)})
    assert r.segui(60_000) == 0                     # liquidità ancora lì
    fonti.liq = 500
    assert r.segui(60_000 + 3 * 60_000) == 1        # sparita: rug
    assert r.segui(60_000 + 6 * 60_000) == 0        # scritto una volta sola
    rug = [json.loads(x) for x in uscita.getvalue().splitlines()]
    assert rug[0]["tipo"] == "rug" and rug[0]["token"] == "TOK"


def test_foto_seguita_solo_se_coperta_per_2_ore_e_mezza():
    from bot.notte.laboratorio import seguita
    ora = 3_600_000
    periodi = [(0, 10 * ora)]
    assert seguita(ora, periodi)
    assert not seguita(9 * ora, periodi)


def test_promosse_in_ordine_senza_doppioni(tmp_path):
    import json
    from bot.notte.laboratorio import promosse
    f = tmp_path / "lab.json"
    f.write_text(json.dumps([
        {"nome": "x", "n": 40, "ritorno_medio_pct": 5.0, "promossa": True},
        {"nome": "x-doppione", "n": 40, "ritorno_medio_pct": 5.0, "promossa": True},
        {"nome": "y", "n": 50, "ritorno_medio_pct": 9.0, "promossa": True},
        {"nome": "z", "n": 60, "ritorno_medio_pct": 20.0, "promossa": False},
    ]))
    assert promosse(f) == ["y", "x"]
