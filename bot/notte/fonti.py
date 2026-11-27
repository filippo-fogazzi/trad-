"""Dati in diretta, tutti pubblici e senza chiavi:
- DexScreener: token nuovi, prezzi, volumi, liquidità
- RugCheck: controlli anti-truffa e numero di holder
- Binance: cambio euro/dollaro
"""
import time

import requests

DEXSCREENER = "https://api.dexscreener.com"
RUGCHECK = "https://api.rugcheck.xyz/v1"
BINANCE = "https://data-api.binance.vision/api/v3"
GECKOTERMINAL = "https://api.geckoterminal.com/api/v2/networks/solana"
# GeckoTerminal: pool appena creati e pool di tendenza (gratis, circa 30 richieste al minuto).
ELENCHI_POOL = ("/new_pools?page=1", "/new_pools?page=2", "/trending_pools?duration=5m", "/trending_pools?duration=1h",
                "/trending_pools?duration=6h", "/trending_pools?duration=24h")  # le ultime due: monete già sopravvissute

# DexScreener non ha un elenco ufficiale di "tutte le coppie nuove": usiamo i token che
# hanno appena creato un profilo, comprato visibilità o avuto un cambio di comunità.
# È un campione parziale (e spesso sono token che pagano per farsi notare).
ELENCHI_TOKEN = (
    "/token-profiles/latest/v1",
    "/token-boosts/latest/v1",
    "/token-boosts/top/v1",
    "/community-takeovers/latest/v1",
)


class Fonti:
    def __init__(self, pausa_rugcheck: float = 1.5):
        self.http = requests.Session()
        self.http.headers["User-Agent"] = "trad-paper-bot"
        self.http.headers["Accept"] = "application/json"
        self.pausa_rugcheck = pausa_rugcheck
        self._ultima_rugcheck = 0.0

    def token_recenti(self) -> list[str]:
        indirizzi: list[str] = []
        for percorso in ELENCHI_TOKEN:
            try:
                elenco = self._leggi(DEXSCREENER + percorso)
            except requests.RequestException:
                continue
            indirizzi += [t["tokenAddress"] for t in elenco if isinstance(t, dict) and t.get("chainId") == "solana"]
        for percorso in ELENCHI_POOL:
            try:
                pool = self._leggi(GECKOTERMINAL + percorso).get("data") or []
            except requests.RequestException:
                continue
            for p in pool:
                token = ((p.get("relationships") or {}).get("base_token") or {}).get("data", {}).get("id", "")
                if token.startswith("solana_"):
                    indirizzi.append(token.removeprefix("solana_"))
        return list(dict.fromkeys(indirizzi))

    def coppie(self, indirizzi: list[str]) -> dict[str, dict]:
        """Per ogni token, la sua coppia con più liquidità."""
        migliori: dict[str, dict] = {}
        for i in range(0, len(indirizzi), 30):
            gruppo = ",".join(indirizzi[i:i + 30])
            for coppia in self._leggi(f"{DEXSCREENER}/tokens/v1/solana/{gruppo}") or []:
                token = coppia["baseToken"]["address"]
                if token not in indirizzi:
                    continue
                if _liquidita(coppia) >= _liquidita(migliori.get(token, {})):
                    migliori[token] = coppia
        return migliori

    def rapporto_rugcheck(self, token: str) -> dict:
        attesa = self.pausa_rugcheck - (time.monotonic() - self._ultima_rugcheck)
        if attesa > 0:
            time.sleep(attesa)
        self._ultima_rugcheck = time.monotonic()
        return self._leggi(f"{RUGCHECK}/tokens/{token}/report")

    def euro_in_dollari(self) -> float:
        return float(self._leggi(f"{BINANCE}/ticker/price", params={"symbol": "EURUSDT"})["price"])

    def _leggi(self, url: str, params: dict | None = None):
        for tentativo in range(3):
            try:
                risposta = self.http.get(url, params=params, timeout=20)
                if risposta.status_code == 429:
                    time.sleep(10 * (tentativo + 1))
                    continue
                risposta.raise_for_status()
                return risposta.json()
            except requests.RequestException:
                if tentativo == 2:
                    raise
                time.sleep(3 * (tentativo + 1))
        raise requests.RequestException(f"troppe richieste a {url}")


def _liquidita(coppia: dict) -> float:
    return float((coppia.get("liquidity") or {}).get("usd") or 0)
