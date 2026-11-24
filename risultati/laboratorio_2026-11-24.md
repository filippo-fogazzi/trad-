# Rapporto del Laboratorio — 24/11/2026 03:11 UTC

Soldi finti, prezzi veri. Ogni operazione paga commissioni e slippage (stime da `regole.yaml`) e rispetta lo Scudo (1% di rischio, stop giornaliero −3%, stop dopo 3 perdite di fila).

**Promosse: 0 su 45 combinazioni.**

## Le strategie testate

- **trend**: Segue la tendenza: compra quando la media veloce (20) supera la lenta (50), vende quando torna sotto.
- **breakout**: Rottura: compra quando il prezzo chiude sopra il massimo delle ultime 20 candele, vende sotto il minimo delle ultime 10.
- **rimbalzo**: Ritorno alla media: compra quando l'RSI scende sotto 30 in un mercato che sale (sopra la media 200), vende quando l'RSI risale sopra 55.

## Come leggere le tabelle

- **Rendimento**: quanto è cambiato il capitale di 500€, dopo tutti i costi.
- **Compra e tieni**: quanto avresti fatto comprando all'inizio e non toccando nulla. Se la strategia fa peggio, non serve.
- **Profit factor**: euro guadagnati per ogni euro perso. Sotto 1 = perde soldi.
- **Drawdown**: la discesa peggiore dal punto più alto del capitale.
- **Commissioni**: quanto è andato a Binance.

## Grafico 1h (ultimi 365 giorni)

| Moneta | Strategia | Operazioni | Vincenti | Profit factor | Rendimento | Compra e tieni | Drawdown | Commissioni | Esito |
|---|---|---|---|---|---|---|---|---|---|
| BTCEUR | trend | 82 | 17% | 0.53 | -17.5% | -27.6% | 17.4% | 35.73€ | ❌ profit factor 0.53, drawdown 17.4%, non positiva in entrambe le metà |
| BTCEUR | breakout | 136 | 27% | 0.59 | -19.8% | -27.6% | 22.2% | 58.78€ | ❌ profit factor 0.59, drawdown 22.2%, non positiva in entrambe le metà |
| BTCEUR | rimbalzo | 8 | 75% | 2.71 | +3.1% | -27.6% | 1.9% | 4.01€ | ❌ solo 8 operazioni, non positiva in entrambe le metà |
| ETHEUR | trend | 89 | 13% | 0.52 | -21.1% | -37.7% | 22.8% | 37.42€ | ❌ profit factor 0.52, drawdown 22.8%, non positiva in entrambe le metà |
| ETHEUR | breakout | 132 | 24% | 0.69 | -18.9% | -37.7% | 21.5% | 55.31€ | ❌ profit factor 0.69, drawdown 21.5%, non positiva in entrambe le metà |
| ETHEUR | rimbalzo | 13 | 38% | 0.43 | -4.1% | -37.7% | 6.4% | 5.58€ | ❌ solo 13 operazioni, profit factor 0.43, non positiva in entrambe le metà |
| SOLEUR | trend | 82 | 18% | 0.53 | -20.1% | -43.9% | 21.4% | 32.03€ | ❌ profit factor 0.53, drawdown 21.4%, non positiva in entrambe le metà |
| SOLEUR | breakout | 126 | 25% | 0.83 | -10.3% | -43.9% | 18.0% | 53.00€ | ❌ profit factor 0.83, drawdown 18.0%, non positiva in entrambe le metà |
| SOLEUR | rimbalzo | 7 | 57% | 1.21 | +0.6% | -43.9% | 3.0% | 3.11€ | ❌ solo 7 operazioni, non positiva in entrambe le metà |
| DOGEEUR | trend | 86 | 20% | 0.71 | -15.4% | -59.9% | 23.6% | 34.86€ | ❌ profit factor 0.71, drawdown 23.6%, non positiva in entrambe le metà |
| DOGEEUR | breakout | 139 | 20% | 0.57 | -31.3% | -59.9% | 32.9% | 51.13€ | ❌ profit factor 0.57, drawdown 32.9%, non positiva in entrambe le metà |
| DOGEEUR | rimbalzo | 5 | 60% | 1.34 | +0.7% | -59.9% | 2.6% | 1.67€ | ❌ solo 5 operazioni, non positiva in entrambe le metà |
| PEPEEUR | trend | 82 | 15% | 0.58 | -22.3% | -16.0% | 43.7% | 27.85€ | ❌ profit factor 0.58, drawdown 43.7%, non positiva in entrambe le metà |
| PEPEEUR | breakout | 137 | 23% | 0.93 | -6.4% | -16.0% | 29.2% | 53.62€ | ❌ profit factor 0.93, drawdown 29.2%, non positiva in entrambe le metà |
| PEPEEUR | rimbalzo | 4 | 75% | 2.53 | +1.5% | -16.0% | 1.4% | 1.13€ | ❌ solo 4 operazioni, non positiva in entrambe le metà |

## Grafico 15m (ultimi 90 giorni)

| Moneta | Strategia | Operazioni | Vincenti | Profit factor | Rendimento | Compra e tieni | Drawdown | Commissioni | Esito |
|---|---|---|---|---|---|---|---|---|---|
| BTCEUR | trend | 87 | 9% | 0.20 | -18.4% | -18.8% | 19.2% | 39.80€ | ❌ profit factor 0.20, drawdown 19.2%, non positiva in entrambe le metà |
| BTCEUR | breakout | 150 | 15% | 0.34 | -23.5% | -18.8% | 24.3% | 66.31€ | ❌ profit factor 0.34, drawdown 24.3%, non positiva in entrambe le metà |
| BTCEUR | rimbalzo | 11 | 18% | 0.15 | -3.0% | -18.8% | 3.0% | 5.42€ | ❌ solo 11 operazioni, profit factor 0.15, non positiva in entrambe le metà |
| ETHEUR | trend | 81 | 12% | 0.25 | -20.3% | -26.8% | 21.3% | 36.22€ | ❌ profit factor 0.25, drawdown 21.3%, non positiva in entrambe le metà |
| ETHEUR | breakout | 150 | 21% | 0.35 | -25.7% | -26.8% | 26.4% | 65.77€ | ❌ profit factor 0.35, drawdown 26.4%, non positiva in entrambe le metà |
| ETHEUR | rimbalzo | 7 | 14% | 0.17 | -2.0% | -26.8% | 2.4% | 3.45€ | ❌ solo 7 operazioni, profit factor 0.17, non positiva in entrambe le metà |
| SOLEUR | trend | 87 | 13% | 0.19 | -25.2% | -21.8% | 26.1% | 38.06€ | ❌ profit factor 0.19, drawdown 26.1%, non positiva in entrambe le metà |
| SOLEUR | breakout | 140 | 20% | 0.52 | -21.6% | -21.8% | 25.7% | 64.92€ | ❌ profit factor 0.52, drawdown 25.7%, non positiva in entrambe le metà |
| SOLEUR | rimbalzo | 3 | 0% | 0.00 | -1.4% | -21.8% | 1.4% | 1.49€ | ❌ solo 3 operazioni, profit factor 0.00, non positiva in entrambe le metà |
| DOGEEUR | trend | 93 | 8% | 0.18 | -32.1% | -30.9% | 32.8% | 38.75€ | ❌ profit factor 0.18, drawdown 32.8%, non positiva in entrambe le metà |
| DOGEEUR | breakout | 154 | 15% | 0.30 | -35.8% | -30.9% | 36.4% | 63.02€ | ❌ profit factor 0.30, drawdown 36.4%, non positiva in entrambe le metà |
| DOGEEUR | rimbalzo | 6 | 17% | 0.03 | -3.0% | -30.9% | 3.5% | 2.94€ | ❌ solo 6 operazioni, profit factor 0.03, non positiva in entrambe le metà |
| PEPEEUR | trend | 84 | 8% | 0.36 | -29.1% | -4.8% | 29.1% | 35.28€ | ❌ profit factor 0.36, drawdown 29.1%, non positiva in entrambe le metà |
| PEPEEUR | breakout | 152 | 17% | 0.51 | -30.0% | -4.8% | 32.1% | 63.07€ | ❌ profit factor 0.51, drawdown 32.1%, non positiva in entrambe le metà |
| PEPEEUR | rimbalzo | 7 | 29% | 0.33 | -2.1% | -4.8% | 4.0% | 3.48€ | ❌ solo 7 operazioni, profit factor 0.33, non positiva in entrambe le metà |

## Grafico 1m (ultimi 14 giorni)

| Moneta | Strategia | Operazioni | Vincenti | Profit factor | Rendimento | Compra e tieni | Drawdown | Commissioni | Esito |
|---|---|---|---|---|---|---|---|---|---|
| BTCEUR | trend | 53 | 6% | 0.09 | -8.6% | -17.8% | 8.6% | 25.38€ | ❌ profit factor 0.09, non positiva in entrambe le metà |
| BTCEUR | breakout | 53 | 8% | 0.08 | -7.5% | -17.8% | 7.5% | 25.48€ | ❌ profit factor 0.08, non positiva in entrambe le metà |
| BTCEUR | rimbalzo | 10 | 20% | 0.06 | -1.3% | -17.8% | 1.3% | 4.96€ | ❌ solo 10 operazioni, profit factor 0.06, non positiva in entrambe le metà |
| ETHEUR | trend | 51 | 6% | 0.28 | -6.7% | -18.7% | 6.7% | 24.75€ | ❌ profit factor 0.28, non positiva in entrambe le metà |
| ETHEUR | breakout | 55 | 9% | 0.08 | -8.2% | -18.7% | 8.2% | 26.34€ | ❌ profit factor 0.08, non positiva in entrambe le metà |
| ETHEUR | rimbalzo | 15 | 7% | 0.04 | -2.4% | -18.7% | 2.6% | 7.41€ | ❌ solo 15 operazioni, profit factor 0.04, non positiva in entrambe le metà |
| SOLEUR | trend | 46 | 2% | 0.02 | -9.3% | -15.9% | 9.3% | 21.91€ | ❌ profit factor 0.02, non positiva in entrambe le metà |
| SOLEUR | breakout | 54 | 11% | 0.10 | -8.4% | -15.9% | 8.4% | 25.96€ | ❌ profit factor 0.10, non positiva in entrambe le metà |
| SOLEUR | rimbalzo | 16 | 12% | 0.07 | -2.3% | -15.9% | 2.3% | 7.92€ | ❌ solo 16 operazioni, profit factor 0.07, non positiva in entrambe le metà |
| DOGEEUR | trend | 47 | 2% | 0.09 | -9.7% | -18.2% | 9.7% | 22.37€ | ❌ profit factor 0.09, non positiva in entrambe le metà |
| DOGEEUR | breakout | 45 | 0% | 0.00 | -10.9% | -18.2% | 10.9% | 21.22€ | ❌ profit factor 0.00, non positiva in entrambe le metà |
| DOGEEUR | rimbalzo | 45 | 0% | 0.00 | -9.9% | -18.2% | 9.9% | 21.35€ | ❌ profit factor 0.00, non positiva in entrambe le metà |
| PEPEEUR | trend | 48 | 2% | 0.04 | -12.0% | -31.6% | 12.0% | 22.48€ | ❌ profit factor 0.04, non positiva in entrambe le metà |
| PEPEEUR | breakout | 47 | 2% | 0.00 | -11.2% | -31.6% | 11.5% | 22.18€ | ❌ profit factor 0.00, non positiva in entrambe le metà |
| PEPEEUR | rimbalzo | 45 | 2% | 0.00 | -10.1% | -31.6% | 10.1% | 21.31€ | ❌ profit factor 0.00, non positiva in entrambe le metà |

## Fonti dei dati

| Moneta | Grafico | Da | A | Candele | Scaricato il (UTC) |
|---|---|---|---|---|---|
| BTCEUR | 1h | 2025-11-24 04:00 | 2026-11-24 02:00 | 8759 | 2026-11-24T03:07 |
| ETHEUR | 1h | 2025-11-24 04:00 | 2026-11-24 02:00 | 8759 | 2026-11-24T03:07 |
| SOLEUR | 1h | 2025-11-24 04:00 | 2026-11-24 02:00 | 8759 | 2026-11-24T03:07 |
| DOGEEUR | 1h | 2025-11-24 04:00 | 2026-11-24 02:00 | 8759 | 2026-11-24T03:07 |
| PEPEEUR | 1h | 2025-11-24 04:00 | 2026-11-24 02:00 | 8759 | 2026-11-24T03:08 |
| BTCEUR | 15m | 2026-08-26 03:15 | 2026-11-24 02:45 | 8639 | 2026-11-24T03:08 |
| ETHEUR | 15m | 2026-08-26 03:15 | 2026-11-24 02:45 | 8639 | 2026-11-24T03:08 |
| SOLEUR | 15m | 2026-08-26 03:15 | 2026-11-24 02:45 | 8639 | 2026-11-24T03:08 |
| DOGEEUR | 15m | 2026-08-26 03:15 | 2026-11-24 02:45 | 8639 | 2026-11-24T03:08 |
| PEPEEUR | 15m | 2026-08-26 03:15 | 2026-11-24 02:45 | 8639 | 2026-11-24T03:08 |
| BTCEUR | 1m | 2026-11-10 03:10 | 2026-11-24 03:08 | 20159 | 2026-11-24T03:09 |
| ETHEUR | 1m | 2026-11-10 03:10 | 2026-11-24 03:08 | 20159 | 2026-11-24T03:09 |
| SOLEUR | 1m | 2026-11-10 03:10 | 2026-11-24 03:08 | 20159 | 2026-11-24T03:10 |
| DOGEEUR | 1m | 2026-11-10 03:11 | 2026-11-24 03:09 | 20159 | 2026-11-24T03:10 |
| PEPEEUR | 1m | 2026-11-10 03:11 | 2026-11-24 03:09 | 20159 | 2026-11-24T03:10 |

Fonte: `https://data-api.binance.vision/api/v3/klines` (dati pubblici di Binance).