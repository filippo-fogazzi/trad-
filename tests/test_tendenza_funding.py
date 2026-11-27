import pandas as pd
import pytest

from bot import funding, tendenza


def candele(prezzi):
    n = len(prezzi)
    return pd.DataFrame({"apertura": pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"),
                         "open": prezzi, "high": prezzi, "low": prezzi, "close": prezzi})


def test_tendenza_decide_ieri_ed_esegue_oggi():
    c = candele([100.0, 100.0, 200.0, 200.0])
    dentro = pd.Series([False, True, True, True])   # decide di entrare alla chiusura del giorno 1
    capitale = tendenza.simula(c, dentro)
    # il salto da 100 a 200 avviene tra la chiusura del giorno 1 e l'apertura del giorno 2: si compra al giorno 2 a 200
    assert capitale.iloc[-1] == pytest.approx(1 - tendenza.COSTO)


def test_tendenza_compra_e_tieni_segue_il_prezzo():
    c = candele([100.0, 110.0, 121.0])
    capitale = tendenza.simula(c, pd.Series([True, True, True]))
    # decide alla chiusura del giorno 0, compra all apertura del giorno 1 (110)
    assert capitale.iloc[-1] == pytest.approx(121 / 110 * (1 - tendenza.COSTO), rel=1e-6)


def test_funding_sempre_dentro_incassa_meta_del_tasso():
    f = pd.DataFrame({"quando": pd.date_range("2022-01-01", periods=30, freq="8h", tz="UTC"), "tasso": [0.0001] * 30})
    capitale = funding.simula(f, sempre=True)
    atteso = (1 - funding.COSTO_GIRO * 0.5) ** 2 * (1 + 0.0001 * 0.5) ** 30
    assert capitale.iloc[-1] == pytest.approx(atteso)


def test_funding_solo_quando_alto_resta_fuori_se_negativo():
    f = pd.DataFrame({"quando": pd.date_range("2022-01-01", periods=60, freq="8h", tz="UTC"), "tasso": [-0.0002] * 60})
    assert funding.simula(f, sempre=False).iloc[-1] == pytest.approx(1.0)
