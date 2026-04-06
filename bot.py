import os
import logging
import anthropic
from datetime import datetime
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── CONFIG DA VARIABILI AMBIENTE ──
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM")         # tua email Gmail
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD") # password app Gmail
EMAIL_TO = "beatrice.mercatali@controlmercatali.it,marco.sutera@controlmercatali.it"

# ── STORAGE IN MEMORIA (per sessione) ──
# { chat_id: { "messaggi": [...], "foto": [...] } }
sessioni = {}

def get_sessione(chat_id):
    if chat_id not in sessioni:
        sessioni[chat_id] = {
            "messaggi": [],
            "foto": [],
            "data_inizio": datetime.now().strftime("%d/%m/%Y")
        }
    return sessioni[chat_id]


# ── /start ──
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = (
        "👷 *Bot Diario Cantiere — Control*\n"
        "Cantiere: Cimolai Monfalcone\n\n"
        "Scrivi liberamente durante la giornata.\n"
        "Manda anche foto di anomalie o cricche.\n\n"
        "Comandi disponibili:\n"
        "📋 /report — Genera e invia email ai titolari\n"
        "👀 /anteprima — Vedi il report senza inviare\n"
        "🗑 /reset — Cancella i messaggi di oggi\n"
        "📝 /stato — Vedi quanti messaggi hai registrato"
    )
    await update.message.reply_text(testo, parse_mode="Markdown")


# ── Raccolta messaggi normali ──
async def raccogli_messaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)
    ora = datetime.now().strftime("%H:%M")
    testo = update.message.text or ""
    if testo:
        sessione["messaggi"].append(f"[{ora}] {testo}")
        n = len(sessione["messaggi"])
        await update.message.reply_text(
            f"✅ Annotazione #{n} salvata",
            reply_to_message_id=update.message.message_id
        )


# ── Raccolta foto ──
async def raccogli_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)
    ora = datetime.now().strftime("%H:%M")

    # Prendi la foto più grande
    foto = update.message.photo[-1]
    file = await context.bot.get_file(foto.file_id)
    foto_bytes = await file.download_as_bytearray()

    caption = update.message.caption or ""
    sessione["foto"].append({
        "bytes": bytes(foto_bytes),
        "caption": caption,
        "ora": ora,
        "file_id": foto.file_id
    })

    if caption:
        sessione["messaggi"].append(f"[{ora}] 📷 Foto: {caption}")

    await update.message.reply_text(
        f"📷 Foto salvata ({len(sessione['foto'])} totali)",
        reply_to_message_id=update.message.message_id
    )


# ── /stato ──
async def cmd_stato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)
    n_msg = len(sessione["messaggi"])
    n_foto = len(sessione["foto"])

    if n_msg == 0 and n_foto == 0:
        await update.message.reply_text("📭 Nessuna annotazione ancora oggi.")
        return

    anteprima = "\n".join(sessione["messaggi"][-5:])
    testo = (
        f"📊 *Stato sessione — {sessione['data_inizio']}*\n\n"
        f"• Annotazioni: {n_msg}\n"
        f"• Foto: {n_foto}\n\n"
        f"*Ultime note:*\n`{anteprima}`"
    )
    await update.message.reply_text(testo, parse_mode="Markdown")


# ── /reset ──
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessioni[chat_id] = {
        "messaggi": [],
        "foto": [],
        "data_inizio": datetime.now().strftime("%d/%m/%Y")
    }
    await update.message.reply_text("🗑 Sessione azzerata. Nuova giornata!")


# ── Genera testo email con Claude ──
def genera_testo_email(messaggi, n_foto, data):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    diario = "\n".join(messaggi) if messaggi else "Nessuna annotazione testuale."

    prompt = f"""Sei un assistente tecnico specializzato in controlli non distruttivi (NDT).

Genera un'email di report giornaliero professionale in italiano per i titolari dell'azienda Control.

DATI:
- Azienda: Control
- Cantiere: Cimolai Monfalcone  
- Data: {data}
- Foto allegate: {n_foto}

DIARIO DEL GIORNO (messaggi inviati dal capocantiere durante la giornata):
{diario}

ISTRUZIONI:
- Struttura il report in modo chiaro e professionale
- Prima riga: "Oggetto: ..." 
- Poi il corpo dell'email con sezioni logiche (operatori, attività NDT, anomalie se presenti, note)
- Usa terminologia tecnica NDT corretta
- Se ci sono anomalie o non conformità, evidenziale chiaramente
- Tono diretto, da professionista del settore
- Se ci sono foto menziona che sono allegate
- Concludi con firma del capocantiere per conto di Control
- Max 300 parole"""

    risposta = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return risposta.content[0].text


# ── Invia email ──
def invia_email(soggetto, corpo, foto_list, destinatari):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = destinatari
    msg["Subject"] = soggetto

    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    for i, f in enumerate(foto_list):
        img = MIMEImage(f["bytes"])
        nome = f"foto_{i+1}_{f['ora'].replace(':','')}.jpg"
        img.add_header("Content-Disposition", "attachment", filename=nome)
        if f["caption"]:
            img.add_header("X-Caption", f["caption"])
        msg.attach(img)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, destinatari.split(","), msg.as_string())


# ── /anteprima ──
async def cmd_anteprima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)

    if not sessione["messaggi"] and not sessione["foto"]:
        await update.message.reply_text(
            "📭 Nessuna annotazione oggi. Inizia a scrivere!"
        )
        return

    await update.message.reply_text("⏳ Genero l'anteprima...")

    try:
        data = datetime.now().strftime("%A %d %B %Y")
        testo = genera_testo_email(
            sessione["messaggi"],
            len(sessione["foto"]),
            data
        )
        # Tronca se troppo lungo per Telegram
        if len(testo) > 3800:
            testo = testo[:3800] + "\n\n[...troncato per anteprima]"

        await update.message.reply_text(
            f"📋 *ANTEPRIMA EMAIL*\n\n```\n{testo}\n```\n\n"
            f"_Foto allegate: {len(sessione['foto'])}_\n\n"
            f"Usa /report per inviare.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Errore anteprima: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


# ── /report ──
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)

    if not sessione["messaggi"] and not sessione["foto"]:
        await update.message.reply_text(
            "📭 Nessuna annotazione oggi. Inizia a scrivere!"
        )
        return

    await update.message.reply_text("⏳ Genero il report con Claude...")

    try:
        data = datetime.now().strftime("%A %d %B %Y")
        testo_email = genera_testo_email(
            sessione["messaggi"],
            len(sessione["foto"]),
            data
        )

        # Estrai oggetto
        righe = testo_email.strip().split("\n")
        soggetto = f"Report giornaliero – Cimolai Monfalcone – {datetime.now().strftime('%d/%m/%Y')}"
        corpo = testo_email
        for r in righe:
            if r.lower().startswith("oggetto:"):
                soggetto = r.replace("Oggetto:", "").replace("oggetto:", "").strip()
                corpo = "\n".join(righe[righe.index(r)+1:]).strip()
                break

        if EMAIL_FROM and EMAIL_PASSWORD:
            await update.message.reply_text("📧 Invio email...")
            invia_email(soggetto, corpo, sessione["foto"], EMAIL_TO)
            await update.message.reply_text(
                f"✅ *Report inviato!*\n\n"
                f"📨 A: Beatrice & Marco\n"
                f"📋 Oggetto: {soggetto}\n"
                f"📷 Foto: {len(sessione['foto'])}\n\n"
                f"Usa /reset per iniziare una nuova giornata.",
                parse_mode="Markdown"
            )
        else:
            # Senza email configurata, manda solo anteprima
            await update.message.reply_text(
                f"📋 *Report generato* (email non configurata)\n\n```\n{testo_email[:2000]}\n```",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Errore report: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


# ── MAIN ──
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("anteprima", cmd_anteprima))
    app.add_handler(CommandHandler("stato", cmd_stato))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, raccogli_messaggio))
    app.add_handler(MessageHandler(filters.PHOTO, raccogli_foto))

    logger.info("Bot Control Cantiere avviato!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
