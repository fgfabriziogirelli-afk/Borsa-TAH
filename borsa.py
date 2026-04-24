"""
Scraper TAH - Borsa Italiana → Telegram
Scarica tutti i contratti e filtra quelli delle 18:00 in Python
"""
import os, re, requests, pytz
from bs4 import BeautifulSoup
from datetime import datetime

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TITOLI = [
    {"isin": "IT0005239360", "ticker": "UCG", "nome": "UNICREDIT"},
    # {"isin": "IT0000072618", "ticker": "ISP", "nome": "INTESA SANPAOLO"},
    # {"isin": "IT0003128367", "ticker": "ENI", "nome": "ENI"},
]

ROME_TZ  = pytz.timezone("Europe/Rome")
BASE_URL = "https://www.borsaitaliana.it"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.borsaitaliana.it/",
}

def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=15
    ).raise_for_status()

def main():
    for titolo in TITOLI:
        isin = titolo["isin"]
        # Nessun filtro HH/MM - scarica tutti i contratti del giorno
        url = f"{BASE_URL}/borsa/azioni/mercato-serale/contratti.html?isin={isin}&mic=MTAH&lang=it"
        print(f"Fetching: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Estrai tutti i contratti
            all_contracts = []
            for t in soup.find_all("table"):
                if any(k in t.get_text().lower() for k in ["ora", "prezzo", "volume"]):
                    for row in t.find_all("tr")[1:]:
                        cols = row.find_all("td")
                        if len(cols) >= 4:
                            ora = cols[0].get_text(strip=True)
                            if len(ora) >= 5 and ora[2] in (":", ",", "."):
                                all_contracts.append({
                                    "ora":        ora,
                                    "prezzo":     cols[1].get_text(strip=True),
                                    "variazione": cols[2].get_text(strip=True),
                                    "quantita":   cols[3].get_text(strip=True),
                                })
                    break

            print(f"Contratti totali scaricati: {len(all_contracts)}")
            if all_contracts:
                print(f"Prime 3 ore: {[c['ora'] for c in all_contracts[:3]]}")

            # Filtra solo 18:00:xx (primo minuto TAH)
            contracts = [c for c in all_contracts if c["ora"][:2] == "18" and c["ora"][3:5] == "00"]
            print(f"Contratti 18:00: {len(contracts)}")

            now = datetime.now(ROME_TZ).strftime("%d/%m/%Y %H:%M")

            if not contracts:
                send_telegram(
                    f"⚠️ <b>{titolo['nome']} ({titolo['ticker']})</b>\n"
                    f"📅 {now}\n"
                    f"Nessun contratto nel range 18:00–18:05.\n"
                    f"Borsa chiusa o assenza di scambi TAH."
                )
                continue

            prezzi, qtot = [], 0
            for c in contracts:
                try: prezzi.append(float(c["prezzo"].replace(",", ".")))
                except: pass
                try: qtot += int(c["quantita"].replace(".", "").replace(",", ""))
                except: pass

            v = round(prezzi[-1] - prezzi[0], 4) if len(prezzi) > 1 else 0
            emoji = "🟢" if v >= 0 else "🔴"
            sep = "─" * 30
            msg = (
                f"🔔 <b>{titolo['nome']} ({titolo['ticker']}) — TAH 18:00</b>\n"
                f"📅 {now}\n{sep}\n"
                f"1° prezzo:  <b>{prezzi[0]:.4f}</b>\n"
                f"Ultimo:     {emoji} <b>{prezzi[-1]:.4f}</b> ({v:+.4f})\n"
                f"Min/Max:    {min(prezzi):.4f} / {max(prezzi):.4f}\n"
                f"Qtà totale: <b>{qtot:,}</b>\n"
                f"{sep}\n"
                f"<b>Contratti 18:00 ({len(contracts)})</b>\n"
                f"<code>Ora        Prezzo   Var%     Qtà\n"
            )
            for c in contracts:
                ora  = c["ora"][:8].replace(",", ":").replace(".", ":").ljust(10)
                prez = c["prezzo"][:7].ljust(8)
                var  = c["variazione"][:7].ljust(8)
                qta  = c["quantita"][:6].rjust(5)
                msg += f"{ora} {prez} {var} {qta}\n"
            msg += "</code>"
            send_telegram(msg)
            print(f"OK - {len(contracts)} contratti inviati")

        except Exception as e:
            print(f"ERRORE: {e}")
            send_telegram(f"❌ <b>Errore {titolo['ticker']}</b>\n<code>{e}</code>")

if __name__ == "__main__":
    main()
