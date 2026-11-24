"""SCANNER e CONTROLLO TRUFFE: funzioni pure, senza rete, facili da testare.

- universo(): il token è anche solo da guardare? (età, DEX, liquidità, volume)
- segnali(): quali segnali di ingresso sono accesi (ne servono almeno 2)
- controllo_truffe(): PASS o lista dei motivi per cui è bocciato
"""


def liquidita(coppia: dict) -> float:
    return float((coppia.get("liquidity") or {}).get("usd") or 0)


def prezzo(coppia: dict) -> float | None:
    valore = coppia.get("priceUsd")
    return float(valore) if valore else None


def universo(coppia: dict, regole: dict, adesso_ms: int) -> tuple[bool, str]:
    u = regole["universo"]
    eta_ore = (adesso_ms - (coppia.get("pairCreatedAt") or 0)) / 3_600_000
    volume_5m = float((coppia.get("volume") or {}).get("m5") or 0)
    if coppia.get("dexId") not in u["dex"]:
        return False, f"DEX non previsto ({coppia.get('dexId')})"
    if eta_ore > u["eta_max_ore"]:
        return False, f"coppia troppo vecchia ({eta_ore:.0f} ore)"
    if prezzo(coppia) is None:
        return False, "nessun prezzo disponibile"
    if liquidita(coppia) < u["liquidita_min_usd"]:
        return False, f"liquidità ${liquidita(coppia):,.0f} sotto ${u['liquidita_min_usd']:,}"
    if volume_5m < u["volume_5min_min_usd"]:
        return False, f"volume 5 min ${volume_5m:,.0f} sotto ${u['volume_5min_min_usd']:,}"
    return True, "ok"


def insegue(coppia: dict, regole: dict) -> bool:
    """Già salito più del 300% nell'ultima ora e ancora in salita negli ultimi 5 minuti."""
    variazioni = coppia.get("priceChange") or {}
    return (variazioni.get("h1") or 0) > regole["uscite"]["no_inseguire_pct_1h"] and (variazioni.get("m5") or 0) >= 0


def segnali(coppia: dict, holder_ora: int | None, holder_prima: int | None, regole: dict) -> list[str]:
    s = regole["segnali"]
    accesi = []
    volume = coppia.get("volume") or {}
    media_5m_ultima_ora = float(volume.get("h1") or 0) / 12
    if media_5m_ultima_ora > 0 and float(volume.get("m5") or 0) > s["picco_volume_x"] * media_5m_ultima_ora:
        accesi.append(f"picco volume {float(volume['m5']) / media_5m_ultima_ora:.1f}x")
    tx = (coppia.get("txns") or {}).get("m5") or {}
    totale = (tx.get("buys") or 0) + (tx.get("sells") or 0)
    if totale >= s["transazioni_min_5min"] and tx["buys"] / totale * 100 >= s["acquisti_min_pct"]:
        accesi.append(f"acquisti {tx['buys'] / totale * 100:.0f}%")
    if holder_ora and holder_prima and (holder_ora / holder_prima - 1) * 100 >= s["crescita_holder_pct"]:
        accesi.append(f"holder +{(holder_ora / holder_prima - 1) * 100:.0f}%")
    return accesi


def quota_sviluppatore_pct(rapporto: dict) -> float:
    fornitura = (rapporto.get("token") or {}).get("supply") or 0
    return (rapporto.get("creatorBalance") or 0) / fornitura * 100 if fornitura else 0.0


def top10_pct(rapporto: dict) -> float:
    """Quota dei 10 maggiori holder, esclusi i conti del pool (AMM) e simili."""
    conti_noti = rapporto.get("knownAccounts") or {}
    holder = [h for h in rapporto.get("topHolders") or []
              if h.get("owner") not in conti_noti and h.get("address") not in conti_noti]
    return sum(h.get("pct") or 0 for h in holder[:10])


def lp_bloccata_pct(rapporto: dict) -> float:
    mercati = rapporto.get("markets") or []
    if not mercati:
        return 0.0
    principale = max(mercati, key=lambda m: (m.get("lp") or {}).get("quoteUSD") or 0)
    return float((principale.get("lp") or {}).get("lpLockedPct") or 0)


def controllo_truffe(rapporto: dict, regole: dict) -> tuple[bool, list[str]]:
    c = regole["controllo_truffe"]
    motivi = []
    if rapporto.get("rugged"):
        motivi.append("già segnalato come truffa")
    if c["no_mint_authority"] and rapporto.get("mintAuthority"):
        motivi.append("mint authority attiva (possono stampare token)")
    if c["no_freeze_authority"] and rapporto.get("freezeAuthority"):
        motivi.append("freeze authority attiva (possono bloccarti i token)")
    if ((rapporto.get("transferFee") or {}).get("pct") or 0) > 0:
        motivi.append("tassa sul trasferimento")
    if quota_sviluppatore_pct(rapporto) > c["sviluppatore_max_pct"]:
        motivi.append(f"sviluppatore ha il {quota_sviluppatore_pct(rapporto):.1f}%")
    if top10_pct(rapporto) > c["top10_max_pct"]:
        motivi.append(f"top 10 holder hanno il {top10_pct(rapporto):.0f}%")
    if lp_bloccata_pct(rapporto) < c["lp_bloccata_min_pct"]:
        motivi.append(f"liquidità bloccata solo al {lp_bloccata_pct(rapporto):.0f}%")
    if c["no_insider_rilevati"] and (rapporto.get("graphInsidersDetected") or 0) > 0:
        motivi.append(f"{rapporto['graphInsidersDetected']} portafogli insider collegati")
    if c["no_rischi_gravi"]:
        motivi += [f"RugCheck: {r['name']}" for r in rapporto.get("risks") or [] if r.get("level") == "danger"]
    if (rapporto.get("totalHolders") or 0) < regole["universo"]["holder_min"]:
        motivi.append(f"solo {rapporto.get('totalHolders') or 0} holder")
    return not motivi, motivi
