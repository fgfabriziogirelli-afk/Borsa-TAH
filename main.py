"""
Scraper TAH (Trading After Hours) - Borsa Italiana -> Telegram
Usa il filtro "Cerca intraday per range temporale" (HH, MM) per ottenere
i contratti del primo slot da 5 minuti del TAH.

Novita' rispetto alla versione precedente:
- legge TUTTE le pagine dei risultati (la pagina 1 mostra solo ~20 righe,
  le piu' recenti, e si perdevano i primi contratti)
- ordina i contratti in modo cronologico dopo aver unito le pagine
- invia i contratti in piu' messaggi se superano il limite di Telegram
"""

import os
import re
import time
import html
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

# -- Configurazione -----------------------------------------------------------
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# -- Titoli da monitorare -----------------------------------------------------
TITOLI = [
    {"isin": "IT0005239360", "ticker": "UCG",  "nome": "UNICREDIT"},
    # {"isin": "IT0000072618", "ticker": "ISP",  "nome": "INTESA SANPAOLO"},
    # {"isin": "IT0003128367", "ticker": "ENI",  "nome": "ENI"},
    # {"isin": "IT0003242622", "ticker": "ENEL", "nome": "ENEL"},
]

# Slot temporale: mostra i 5 minuti SUCCESSIVI a HH:MM
TROVA_HH = "18"
TROVA_MM = "00"

# Paginazione
PAGE_PARAM    = "page"   # nome del parametro di pagina nell'URL (da verificare)
MAX_PAGINE    = 30       # limite di sicurezza
PAGINA_PIENA  = 20       # righe per pagina osservate: se ne arrivano >= 20 e
                         # c'e' una sola pagina, c'e' il sospetto di troncamento

# Telegram
LIMITE_BLOCCO = 3500     # caratteri per messaggio (il massimo Telegram e' 4096)

# Pause (buona educazione verso il server)
PAUSA_TRA_TITOLI = 3
PAUSA_TRA_PAGINE = 1

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


# -- Utilita' -----------------------------------------------------------------
def slot_label() -> tuple[str, str]:
    """Restituisce (inizio, fine) dello slot, es. ('18:00', '18:05')."""
    inizio = int(TROVA_HH) * 60 + int(TROVA_MM)
    fine = inizio + 5
    return (f"{int(TROVA_HH):02d}:{int(TROVA_MM):02d}",
            f"{fine // 60:02d}:{fine % 60:02d}")


def norm_ora(ora: str) -> str:
    """Normalizza l'ora in HH:MM:SS per poterla confrontare come stringa."""
    return ora[:8].replace(",", ":").replace(".", ":")


def fmt_int(n: int) -> str:
    """Formato italiano con il punto come separatore delle migliaia."""
    return f"{n:,}".replace(",", ".")


def build_url(isin: str, pagina: int | None = None, con_slot: bool = True) -> str:
    url = (
        f"{BASE_URL}/borsa/azioni/mercato-serale/contratti.html"
        f"?isin={isin}&mic=MTAH&lang=it"
    )
    if con_slot:
        url += f"&HH={TROVA_HH}&MM={TROVA_MM}"
    if pagina is not None:
        url += f"&{PAGE_PARAM}={pagina}"
    return url


# -- Fetch e parsing ----------------------------------------------------------
def _parse_page(html_text: str) -> tuple[list[dict], dict]:
    """Estrae i contratti (nell'ordine della pagina) e il sommario."""
    soup      = BeautifulSoup(html_text, "html.parser")
    contracts = []
    summary   = {"num_contratti": 0, "quantita_totale": 0}

    # Sommario "NUMERO CONTRATTI: 138  QUANTITA' TOTALE: 34.102"
    # Cerco nel testo dell'intera pagina, cosi' funziona anche se etichetta e
    # numero stanno in tag diversi.
    testo = soup.get_text(" ", strip=True)
    nc = re.search(r"numero contratti[:\s]+([0-9.,]+)", testo, re.I)
    qt = re.search(r"quantit[àa][^:]*[:\s]+([0-9.,]+)", testo, re.I)
    if nc:
        try:
            summary["num_contratti"] = int(nc.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            pass
    if qt:
        try:
            summary["quantita_totale"] = int(qt.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            pass

    # Tabella contratti: prendo la prima tabella che contiene righe valide
    # (riga valida = prima colonna con un'ora tipo 18:03:38)
    for t in soup.find_all("table"):
        righe = []
        for row in t.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            ora = cols[0].get_text(strip=True)
            if not re.match(r"^\d{2}[:.,]\d{2}([:.,]\d{2})?", ora):
                continue
            righe.append({
                "ora":        ora,
                "prezzo":     cols[1].get_text(strip=True),
                "variazione": cols[2].get_text(strip=True),
                "quantita":   cols[3].get_text(strip=True),
                "tipo":       cols[4].get_text(strip=True) if len(cols) > 4 else "CT",
            })
        if righe:
            contracts = righe
            break

    return contracts, summary


def fetch_contracts_tah(isin: str) -> tuple[list[dict], dict, int]:
    """
    Scarica tutte le pagine dello slot e restituisce
    (contratti in ordine cronologico, sommario, numero di pagine lette).
    """
    tutti: list[dict] = []
    summary = {"num_contratti": 0, "quantita_totale": 0}
    firma_prec = None
    pagine_lette = 0

    for pagina in range(1, MAX_PAGINE + 1):
        resp = requests.get(build_url(isin, pagina), headers=HEADERS, timeout=20)
        resp.raise_for_status()
        righe, summ = _parse_page(resp.text)

        if pagina == 1:
            summary = summ
        if not righe:
            break

        # Se il sito ignora il parametro, la pagina e' identica alla precedente
        firma = tuple((r["ora"], r["prezzo"], r["quantita"]) for r in righe[:3])
        if firma == firma_prec:
            print(f"     pagina {pagina} uguale alla precedente: stop")
            break
        firma_prec = firma

        pagine_lette += 1
        tutti.extend(righe)
        print(f"     pagina {pagina}: {len(righe)} righe")
        time.sleep(PAUSA_TRA_PAGINE)

    # Il sito mostra il piu' recente in cima: se l'insieme e' decrescente lo
    # inverto per intero (cosi' i contratti dello stesso secondo restano
    # nell'ordine corretto).
    if len(tutti) > 1 and norm_ora(tutti[0]["ora"]) > norm_ora(tutti[-1]["ora"]):
        tutti.reverse()

    return tutti, summary, pagine_lette


# -- Statistiche --------------------------------------------------------------
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


# -- Telegram -----------------------------------------------------------------
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


def formatta_riepilogo(titolo: dict, contracts: list[dict], stats: dict,
                       summary: dict, pagine: int) -> str:
    now = datetime.now(ROME_TZ).strftime("%d/%m/%Y %H:%M")
    sep = "─" * 30
    inizio, fine = slot_label()
    link = build_url(titolo["isin"], con_slot=False)

    msg = (
        f"🔔 <b>{titolo['nome']} ({titolo['ticker']}) — TAH {inizio}</b>\n"
        f"📅 {now}\n{sep}\n"
    )

    if stats:
        v = stats["variazione"]
        emoji = "🟢" if v >= 0 else "🔴"
        msg += (
            f"1° contratto:  <b>{stats['apertura']:.4f}</b>\n"
            f"Ultimo slot:   {emoji} <b>{stats['chiusura']:.4f}</b> ({v:+.4f})\n"
            f"Min / Max:     {stats['minimo']:.4f} / {stats['massimo']:.4f}\n"
            f"Qtà {inizio}–{fine}:  <b>{fmt_int(stats['qtot'])}</b>\n"
        )
    if summary["num_contratti"]:
        msg += (
            f"Contratti TAH: {fmt_int(summary['num_contratti'])}  "
            f"| Qtà TAH: {fmt_int(summary['quantita_totale'])}\n"
        )

    msg += f"{sep}\n<b>Contratti {inizio}–{fine} ({len(contracts)} righe)</b>\n"
    msg += f"Primo: {norm_ora(contracts[0]['ora'])} | Ultimo: {norm_ora(contracts[-1]['ora'])}\n"

    # Avviso se sembra che la paginazione non abbia funzionato
    if pagine <= 1 and len(contracts) >= PAGINA_PIENA:
        msg += (
            "⚠️ <b>Possibile troncamento</b>: letta una sola pagina piena, "
            "potrebbero mancare i primi contratti.\n"
        )

    msg += f"🔗 <a href=\"{link}\">Apri su Borsa Italiana</a>"
    return msg


def invia_contratti(contracts: list[dict]) -> None:
    """Invia la tabella dei contratti spezzandola in blocchi."""
    intestazione = "Ora        Prezzo    Var%      Qtà\n"
    blocco = intestazione
    for c in contracts:
        ora  = norm_ora(c["ora"]).ljust(10)
        prez = c["prezzo"][:7].ljust(9)
        varp = c["variazione"][:7].ljust(9)
        qta  = c["quantita"][:6].rjust(5)
        riga = html.escape(f"{ora} {prez} {varp} {qta}") + "\n"

        if len(blocco) + len(riga) > LIMITE_BLOCCO:
            send_telegram(f"<code>{blocco}</code>")
            time.sleep(0.5)
            blocco = intestazione
        blocco += riga

    if blocco != intestazione:
        send_telegram(f"<code>{blocco}</code>")


# -- Main ---------------------------------------------------------------------
def main():
    inizio, fine = slot_label()
    print(f"[{datetime.now(ROME_TZ).strftime('%H:%M:%S')}] "
          f"Scraping TAH — {len(TITOLI)} titolo/i")

    for i, titolo in enumerate(TITOLI):
        print(f"  → {titolo['ticker']} ({titolo['isin']})")
        try:
            contracts, summary, pagine = fetch_contracts_tah(titolo["isin"])
            print(f"     {len(contracts)} contratti in {pagine} pagina/e "
                  f"(dichiarati: {summary['num_contratti']})")
            if contracts:
                print(f"     primo: {contracts[0]['ora']} | ultimo: {contracts[-1]['ora']}")

            if not contracts:
                send_telegram(
                    f"⚠️ <b>{titolo['nome']} ({titolo['ticker']})</b>\n"
                    f"Nessun contratto nel range {inizio}–{fine}.\n"
                    f"Borsa chiusa, assenza di scambi TAH o pagina non letta."
                )
            else:
                stats = calcola_statistiche(contracts)
                send_telegram(formatta_riepilogo(titolo, contracts, stats, summary, pagine))
                invia_contratti(contracts)
                print("     ✓ Messaggi inviati")

        except Exception as e:
            print(f"     ✗ Errore: {e}")
            try:
                send_telegram(
                    f"❌ <b>Errore {titolo['ticker']}</b>\n"
                    f"<code>{html.escape(type(e).__name__ + ': ' + str(e))}</code>"
                )
            except Exception:
                pass

        if i < len(TITOLI) - 1:
            time.sleep(PAUSA_TRA_TITOLI)

    print("Fine.")


if __name__ == "__main__":
    main()
