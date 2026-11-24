from datetime import datetime, timezone

import pandas as pd
import pytest

from bot.laboratorio import simula
from bot.regole import carica_regole
from bot.scudo import Scudo
from bot.strategie import Strategia

REGOLE = carica_regole()


def scudo():
    s = Scudo(REGOLE, controlla_interruttore=False)
    s.aggiorna_momento(datetime(2026, 1, 5, 10, tzinfo=timezone.utc), 500)
    return s


# --- Scudo ---------------------------------------------------------------

def test_rischia_esattamente_1_percento():
    quantita, _ = scudo().dimensiona(500, prezzo_ingresso=100, stop=98)
    assert quantita * (100 - 98) == pytest.approx(5.0)


def test_non_supera_meta_del_capitale():
    quantita, _ = scudo().dimensiona(500, prezzo_ingresso=100, stop=99.9)
    assert quantita * 100 == pytest.approx(250.0)


def test_rifiuta_ordine_sotto_minimo():
    quantita, motivo = scudo().dimensiona(500, prezzo_ingresso=100, stop=-1)
    assert quantita == 0
    quantita, motivo = scudo().dimensiona(3, prezzo_ingresso=100, stop=99)
    assert quantita == 0 and "minimo" in motivo


def test_stop_dopo_3_perdite_e_ripartenza_il_giorno_dopo():
    s = scudo()
    for capitale in (499, 498, 497):
        assert s.puo_aprire()[0]
        s.registra_esito(-1, capitale)
    assert not s.puo_aprire()[0]
    s.aggiorna_momento(datetime(2026, 1, 6, 10, tzinfo=timezone.utc), 497)
    assert s.puo_aprire()[0]


def test_stop_giornaliero_al_3_percento():
    s = scudo()
    s.registra_esito(-15, 485)
    permesso, motivo = s.puo_aprire()
    assert not permesso and "giornaliera" in motivo


def test_il_giorno_cambia_a_mezzanotte_italiana_non_utc():
    s = scudo()
    s.registra_esito(-15, 485)
    s.aggiorna_momento(datetime(2026, 1, 5, 22, 30, tzinfo=timezone.utc), 485)  # 23:30 in Italia
    assert not s.puo_aprire()[0]
    s.aggiorna_momento(datetime(2026, 1, 5, 23, 30, tzinfo=timezone.utc), 485)  # 00:30 in Italia
    assert s.puo_aprire()[0]


def test_interruttore_stop(tmp_path, monkeypatch):
    import bot.scudo as modulo
    file_stop = tmp_path / "STOP"
    file_stop.touch()
    monkeypatch.setattr(modulo, "FILE_INTERRUTTORE", file_stop)
    s = Scudo(REGOLE)
    assert s.puo_aprire() == (False, "interruttore STOP attivo")


# --- Laboratorio ---------------------------------------------------------

def candele(prezzi):
    """Candele finte: ogni tupla è (open, high, low, close)."""
    return pd.DataFrame({
        "apertura": pd.date_range("2026-01-05 08:00", periods=len(prezzi), freq="1h", tz="UTC"),
        "open": [p[0] for p in prezzi], "high": [p[1] for p in prezzi],
        "low": [p[2] for p in prezzi], "close": [p[3] for p in prezzi],
    })


def strategia_fissa(entra_a, atr=1.0, esci_a=None):
    def calcola(c):
        n = len(c)
        return pd.DataFrame({
            "entra": [i == entra_a for i in range(n)],
            "esci": [i == esci_a for i in range(n)],
            "atr": [atr] * n,
        })
    return Strategia("prova", "", calcola)


def test_stop_perde_al_massimo_5_euro_costi_inclusi():
    c = candele([(100, 100, 100, 100)] * 2 + [(100, 100.5, 97, 97)] + [(97, 97, 97, 97)])
    r = simula(c, strategia_fissa(entra_a=1), "BTCEUR", "1h", REGOLE)
    (op,) = r.operazioni
    assert op.motivo_uscita == "stop"
    assert op.guadagno == pytest.approx(-5.0)   # 1% di 500€, commissioni e slippage inclusi
    assert op.commissioni > 0


def test_ingresso_alla_candela_dopo_il_segnale():
    c = candele([(100, 100, 100, 100), (100, 100, 100, 100), (101, 102, 101, 102), (102, 102, 102, 102)])
    r = simula(c, strategia_fissa(entra_a=1, esci_a=2), "BTCEUR", "1h", REGOLE)
    (op,) = r.operazioni
    assert op.prezzo_entrata == pytest.approx(101 * 1.0005)   # apertura candela 2 + slippage
    assert op.uscita == c["apertura"].iat[3]


def test_buco_sotto_lo_stop_esce_al_prezzo_peggiore():
    c = candele([(100, 100, 100, 100)] * 3 + [(90, 91, 89, 90)])
    r = simula(c, strategia_fissa(entra_a=1), "BTCEUR", "1h", REGOLE)
    (op,) = r.operazioni
    assert "apertura" in op.motivo_uscita
    assert op.prezzo_uscita < 90
