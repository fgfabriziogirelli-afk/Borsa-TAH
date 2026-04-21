"""
Scraper TAH (Trading After Hour) - Borsa Italiana → Telegram
Usa il filtro "Cerca intraday per range temporale" (HH=18, MM=00)
per ottenere SOLO i contratti del primo slot da 5 minuti del TAH.
Supporta più titoli contemporaneamente.
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

# ── Configurazione ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ── Titoli da monitorare ──────────────────────────────────────────────────────
TITOLI = [
    {"isin": "IT0005239360", "ticker": "UCG",  "nome": "UNICREDIT"},
    # {"isin": "IT0000072618", "ticker": "ISP",  "nome": "INTESA SANPAOLO"},
    # {"isin": "IT0003128367", "ticker": "ENI",  "nome": "ENI"},
    # {"isin": "IT0003242622", "ticker": "ENEL", "nome": "ENEL"},
]

TROVA_HH = "18"
TROVA_MM = "00"
PAUSA_TRA_TITOLI = 3

ROME_TZ  = pytz.timezone("Europe/Rome")
BASE_URL = "https://www.borsaitaliana.it"
HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": BASE_URL + "/",
}


def build_url(isin: str) -> str:
    return (
        f"{BASE_URL}/borsa/azioni/mercato-serale/contratti.html"
        f"?isin={isin}&mic=MTAH&lang=it"
    )


def fetch_contracts_tah(isin: str) -> tuple[list[dict], dict]:
    url = (
        f"{BASE_URL}/borsa/azioni/mercato-serale/contratti.html"
        f"?isin={isin}&mic=MTAH&HH={TROVA_HH}&MM={TROVA_MM}&lang=it"
    )
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return _parse_page(resp.text)


def _parse_page(html: str) -> tuple[list[dict], dict]:
    soup      = BeautifulSoup(html, "html.parser")
    contracts = []
    summary   = {"num_contratti": 0, "quantita_totale": 0}

    for tag in soup.find_all(string=re.compile(r"numero contratti", re.I)):
        text = tag.strip()
        nc = re.search(r"numero contratti[:\s]+([0-9.,]+)", text, re.I)
        qt = re.search(r"quantit[àa][^:]*[:\s]+([0-9.,]+)", text, re.I)
        if nc:
            summary["num_contratti"] = int(nc.group(1).replace(".", "").replace(",", ""))
        if qt:
            summary["quantita_totale"] = int(qt.group(1).replace(".", "").replace(",", ""))

    target = None
    for t in soup.find_all("table"):
        h = (t.find("tr") or t).get_text().lower()
        if any(k in h for k in ["ora", "prezzo", "volume", "tipo"]):
            target = t
            break
    if not target:
        return contracts, summary

    for row in target.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue
        ora = cols[0].get_text(strip=True)
        if not (len(ora) >= 5 and ora[2] in (":", ",", ".")):
            continue
        contracts.append({
            "ora":        ora,
            "prezzo":     cols[1].get_text(strip=True),
            "variazione": cols[2].get_text(strip=True),
            "quantita":   cols[3].get_text(strip=True),
            "tipo":       cols[4].get_text(strip=True) if len(cols) > 4 else "CT",
        })

    def to_time(c):
        try:
            return datetime.strptime(
                c["ora"][:8].replace(",", ":").replace(".", ":"), "%H:%M:%S"
            )
        except ValueError:
            return datetime.min

    contracts.sort(key=to_time)
    return contracts, summary


def calcola_statistiche(contracts: list[dict]) -> dict:
    if not contracts:
        return {}
    prezzi, qtot = [], 0
    for c in contracts:
        try:
            prezzi.append(float(c["prezzo"].replace(",", ".").replace("\xa0", "")))
        except ValueError:
            pass
        try:
            qtot += int(c["quantita"].replace(".", "").replace(",", "").replace("\xa0", ""))
        except ValueError:
            pass
    if not prezzi:
        return {}
    return {
        "n":          len(contracts),
        "apertura":   prezzi[0],
        "chiusura":   prezzi[-1],
        "minimo":     min(prezzi),
        "massimo":    max(prezzi),
        "qtot":       qtot,
        "variazione": round(prezzi[-1] - prezzi[0], 4),
    }


def send_telegram(text: str) -> None:
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id":                  TELEGRAM_CHAT_ID,
            "text":                     text,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    r.raise_for_status()


def formatta_messaggio(titolo: dict, contracts: list[dict],
                       stats: dict, summary: dict) -> str:
    now  = datetime.now(ROME_TZ).strftime("%d/%m/%Y %H:%M")
    sep  = "─" * 30
    link = build_url(titolo["isin"])

    msg = (
        f"🔔 <b>{titolo['nome']} ({titolo['ticker']}) — TAH 18:00</b>\n"
        f"📅 {now}\n{sep}\n"
    )

    if stats:
        v = stats["variazione"]
        emoji = "🟢" if v >= 0 else "🔴"
        msg += (
            f"1° contratto:  <b>{stats['apertura']:.4f}</b>\n"
            f"Ultimo slot:   {emoji} <b>{stats['chiusura']:.4f}</b> ({v:+.4f})\n"
            f"Min / Max:     {stats['minimo']:.4f} / {stats['massimo']:.4f}\n"
            f"Qtà 18:00–05:  <b>{stats['qtot']:,}</b>\n"
        )
    if summary["num_contratti"]:
        msg += (
            f"Contratti TAH: {summary['num_contratti']:,}  "
            f"| Qtà TAH: {summary['quantita_totale']:,}\n"
        )

    msg += f"{sep}\n<b>Contratti 18:00–18:05 ({len(contracts)} righe)</b>\n"
    msg += "<code>Ora        Prezzo    Var%      Qtà\n"
    for c in contracts:
        ora  = c["ora"][:8].replace(",", ":").replace(".", ":").ljust(10)
        prez = c["prezzo"][:7].ljust(9)
        varp = c["variazione"][:7].ljust(9)
        qta  = c["quantita"][:6].rjust(5)
        msg += f"{ora} {prez} {varp} {qta}\n"
    msg += "</code>"
    msg += f"\n🔗 <a href='{link}'>Apri su Borsa Italiana</a>"
    return msg


def main():
    print(f"[{datetime.now(ROME_TZ).strftime('%H:%M:%S')}] "
          f"Scraping TAH — {len(TITOLI)} titolo/i")

    for i, titolo in enumerate(TITOLI):
        print(f"  → {titolo['ticker']} ({titolo['isin']})")
        try:
            contracts, summary = fetch_contracts_tah(titolo["isin"])
            print(f"     {len(contracts)} contratti nel range 18:00–18:05")

            if not contracts:
                send_telegram(
                    f"⚠️ <b>{titolo['nome']} ({titolo['ticker']})</b>\n"
                    f"Nessun contratto nel range 18:00–18:05.\n"
                    f"Borsa chiusa o assenza di scambi TAH."
                )
            else:
                stats = calcola_statistiche(contracts)
                send_telegram(formatta_messaggio(titolo, contracts, stats, summary))
                print("     ✓ Messaggio inviato")

        except Exception as e:
            print(f"     ✗ Errore: {e}")
            try:
                send_telegram(
                    f"❌ <b>Errore {titolo['ticker']}</b>\n"
                    f"<code>{type(e).__name__}: {e}</code>"
                )
            except Exception:
                pass

        if i < len(TITOLI) - 1:
            time.sleep(PAUSA_TRA_TITOLI)

    print("Fine.")


if __name__ == "__main__":
    main()
