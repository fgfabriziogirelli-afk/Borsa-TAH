# 📊 Scraper TAH Borsa Italiana → Telegram

Invia automaticamente ogni giorno lavorativo alle **18:10** i contratti
del primo slot TAH (18:00–18:05) direttamente su Telegram.
Gira su **GitHub Actions** — gratuito, nessun PC o server necessario.

---

## PARTE 1 — Telegram (5 minuti)

Non hai bisogno di un canale. Puoi ricevere i messaggi in due modi:

### Opzione A — Chat privata con il bot (più semplice, solo per te)

1. Apri Telegram, cerca **@BotFather** e scrivigi
2. Manda il comando `/newbot`
3. Scegli un nome es. `Borsa TAH Bot` e un username es. `borsatah_bot`
4. BotFather ti risponde con il **token**, tipo:
   ```
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```
   → **Copialo e salvalo**, ti servirà dopo

5. Ora scrivi un qualsiasi messaggio al tuo bot (es. "ciao") — serve per
   attivarlo e far comparire il tuo chat_id

6. Apri nel browser questo URL (sostituisci il TOKEN):
   ```
   https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrSTUvwxYZ/getUpdates
   ```
7. Vedrai un JSON. Cerca questa parte:
   ```json
   "chat": { "id": 987654321, ...}
   ```
   → Quel numero `987654321` è il tuo **Chat ID** — salvalo

---

### Opzione B — Canale Telegram (per condividere con più persone)

1. Crea un canale Telegram (può essere privato o pubblico)
2. Aggiungi il bot al canale come **Amministratore**
3. Per ottenere il Chat ID del canale:
   - Se il canale è **pubblico** (es. `@miocanale`): il Chat ID è semplicemente `@miocanale`
   - Se il canale è **privato**: manda un messaggio nel canale, poi apri
     `https://api.telegram.org/bot<TOKEN>/getUpdates` e cerca `"chat":{"id":`
     — il numero sarà negativo tipo `-1001234567890`

---

## PARTE 2 — GitHub (5 minuti)

### 1. Crea un account GitHub (se non ce l'hai)
Vai su [github.com](https://github.com) → Sign up → account gratuito

### 2. Crea il repository

- Vai su [github.com/new](https://github.com/new)
- Nome repository: `borsa-tah-scraper`
- Visibilità: **Public** (serve per Actions gratuiti illimitati)
- Clicca **Create repository**

### 3. Carica i file

Nella pagina del repository appena creato:
- Clicca **"uploading an existing file"** (link piccolo sotto il titolo)
- Trascina tutti e 4 i file dello zip in questa cartella:
  ```
  scraper.py
  requirements.txt
  README.md
  ```
- Poi crea la struttura per il workflow:
  - Clicca **Add file → Create new file**
  - Nel campo nome scrivi esattamente: `.github/workflows/scraper.yml`
  - Copia e incolla il contenuto del file `scraper.yml` dallo zip
  - Clicca **Commit changes**

### 4. Aggiungi i secrets (token e chat id)

Vai su: **Settings** (in alto nel repository) →
**Secrets and variables** → **Actions** → **New repository secret**

Aggiungi questi due secrets:

| Nome               | Valore                                    |
|--------------------|-------------------------------------------|
| `TELEGRAM_TOKEN`   | Il token del bot (da BotFather)           |
| `TELEGRAM_CHAT_ID` | Il tuo Chat ID o `@nomecanale`            |

---

## PARTE 3 — Abilita e testa

### Abilita GitHub Actions
- Vai su **Actions** nel repository
- Se compare il pulsante **"I understand my workflows, go ahead and enable them"** — cliccalo

### Fai un test manuale subito
- **Actions** → **TAH Borsa Italiana Scraper** → **Run workflow** → **Run workflow**
- Dopo ~30 secondi guarda i log: se vedi `✓ Messaggio inviato` funziona tutto
- Controlla Telegram — deve essere arrivato il messaggio

Da quel momento gira **automaticamente ogni giorno lavorativo alle 18:10** senza
che tu faccia nulla.

---

## Aggiungere altri titoli

Apri `scraper.py` e modifica la sezione `TITOLI`:

```python
TITOLI = [
    {"isin": "IT0005239360", "ticker": "UCG",  "nome": "UNICREDIT"},
    {"isin": "IT0000072618", "ticker": "ISP",  "nome": "INTESA SANPAOLO"},
    {"isin": "IT0003128367", "ticker": "ENI",  "nome": "ENI"},
    {"isin": "IT0003242622", "ticker": "ENEL", "nome": "ENEL"},
]
```

Ogni titolo riceve un messaggio Telegram separato.
Per trovare l'ISIN di un titolo: cerca il nome su Borsa Italiana,
nella scheda del titolo trovi l'ISIN (inizia sempre con IT...).

---

## Struttura file

```
borsa-tah-scraper/
├── scraper.py                   ← logica scraping + Telegram
├── requirements.txt             ← librerie Python
├── README.md                    ← questa guida
└── .github/
    └── workflows/
        └── scraper.yml          ← scheduler automatico
```

---

## Note utili

- **GitHub Actions gratuiti**: 2.000 minuti/mese — per 1 run/giorno
  da ~30 secondi bastano abbondantemente
- **L'orario non è garantito al secondo**: GitHub può ritardare
  di 5–15 minuti in caso di traffico elevato
- **Borsa chiusa**: il workflow salta automaticamente le festività
  (Natale, Pasqua, ecc.) configurate nel file scraper.yml
- **Se qualcosa non funziona**: vai su Actions → clicca sul run
  fallito → espandi i log → mandami lo screenshot
