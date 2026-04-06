# Control Cantiere Bot — Setup

## Variabili d'ambiente da configurare su Railway

| Variabile | Valore |
|-----------|--------|
| `TELEGRAM_TOKEN` | Il token del tuo bot (da BotFather) |
| `ANTHROPIC_API_KEY` | La tua API key di Anthropic |
| `EMAIL_FROM` | La tua email Gmail (es. tua@gmail.com) |
| `EMAIL_PASSWORD` | Password app Gmail (vedi sotto) |

## Come ottenere la Password App Gmail

1. Vai su myaccount.google.com
2. Sicurezza → Verifica in due passaggi (deve essere attiva)
3. Cerca "Password per le app"
4. Crea una nuova password → seleziona "Posta" + "Altro"
5. Copia la password di 16 caratteri generata

## Deploy su Railway

1. Vai su railway.app e crea account gratuito
2. "New Project" → "Deploy from GitHub repo"  
   (oppure "Deploy from template" → Python)
3. Carica questi file nel repo
4. Vai su Variables e aggiungi le 4 variabili sopra
5. Deploy automatico!

## Comandi del bot

- Scrivi liberamente → ogni messaggio viene salvato con orario
- Manda foto → vengono allegate al report
- `/stato` → vedi quante note hai oggi
- `/anteprima` → vedi il report senza inviare
- `/report` → genera il report con Claude e manda email a Beatrice e Marco
- `/reset` → nuova giornata
