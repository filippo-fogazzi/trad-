# trad- — bot di trading su carta

**Soldi finti, prezzi veri.** Il bot non può usare soldi veri: quella parte non esiste nel codice.
Verrà aggiunta solo quando scriverai "go live", e solo dopo almeno 2 settimane di prove su carta superate.

Non serve saper programmare. L'unico file da leggere è [`regole.yaml`](regole.yaml):
ogni numero ha accanto la sua spiegazione in italiano.

## La squadra

| Agente | Il suo unico lavoro | Stato |
|---|---|---|
| **Laboratorio** | Prova ogni strategia su dati reali di Binance, con commissioni e slippage, e boccia quelle che perdono | ✅ funziona |
| **Scudo** | Controlla ogni operazione: massimo 5€ di rischio, stop a −15€ al giorno o dopo 3 perdite di fila, interruttore di emergenza | ✅ funziona (codice fisso, non AI) |
| **Esploratore** | Guarda i prezzi 24/7 e trova i segnali delle strategie promosse | da fare |
| **Pilota** | Esegue le operazioni su carta, solo dopo il sì dello Scudo | da fare |
| **Diario** | Registra ogni operazione con il suo motivo e scrive il riepilogo settimanale | da fare |
| **Coordinatore** | L'unico che ti scrive: un messaggio al giorno su Telegram | da fare |

## Interruttore di emergenza

Se esiste un file chiamato `STOP` nella cartella del progetto, lo Scudo blocca ogni nuova operazione.

## Ultimi risultati

Vedi la cartella [`risultati/`](risultati/).

## Per chi programma

```
python -m bot.laboratorio   # scarica i dati e scrive il rapporto
python -m pytest -q         # test dello Scudo e del Laboratorio
```
