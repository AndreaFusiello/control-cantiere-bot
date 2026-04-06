import os
import logging
import anthropic
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

sessioni = {}

def get_sessione(chat_id):
    if chat_id not in sessioni:
        sessioni[chat_id] = {
            "messaggi": [],
            "foto": [],
            "data_inizio": datetime.now().strftime("%d/%m/%Y")
        }
    return sessioni[chat_id]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = (
        "👷 *Bot Diario Cantiere — Control*\n"
        "Cantiere: Cimolai Monfalcone\n\n"
        "Scrivi liberamente durante la giornata.\n"
        "Manda anche foto di anomalie o cricche.\n\n"
        "Comandi:\n"
        "📋 /report — Genera il report pronto da copiare\n"
        "👀 /anteprima — Vedi il testo senza foto\n"
        "📊 /stato — Quante note hai oggi\n"
        "🗑 /reset — Nuova giornata"
    )
    await update.message.reply_text(testo, parse_mode="Markdown")


async def raccogli_messaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)
    ora = datetime.now().strftime("%H:%M")
    testo = update.message.text or ""
    if testo:
        sessione["messaggi"].append(f"[{ora}] {testo}")
        n = len(sessione["messaggi"])
        await update.message.reply_text(
            f"✅ Nota #{n} salvata",
            reply_to_message_id=update.message.message_id
        )


async def raccogli_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)
    ora = datetime.now().strftime("%H:%M")

    foto = update.message.photo[-1]
    caption = update.message.caption or ""

    sessione["foto"].append({
        "file_id": foto.file_id,
        "caption": caption,
        "ora": ora
    })

    if caption:
        sessione["messaggi"].append(f"[{ora}] Foto: {caption}")

    n_foto = len(sessione["foto"])
    await update.message.reply_text(
        f"📷 Foto #{n_foto} salvata" + (f" — {caption}" if caption else ""),
        reply_to_message_id=update.message.message_id
    )


async def cmd_stato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)
    n_msg = len(sessione["messaggi"])
    n_foto = len(sessione["foto"])

    if n_msg == 0 and n_foto == 0:
        await update.message.reply_text("📭 Nessuna annotazione ancora oggi.")
        return

    ultime = "\n".join(sessione["messaggi"][-5:])
    testo = (
        f"📊 *Stato — {sessione['data_inizio']}*\n\n"
        f"Annotazioni: {n_msg}\n"
        f"Foto: {n_foto}\n\n"
        f"*Ultime note:*\n{ultime}"
    )
    await update.message.reply_text(testo, parse_mode="Markdown")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessioni[chat_id] = {
        "messaggi": [],
        "foto": [],
        "data_inizio": datetime.now().strftime("%d/%m/%Y")
    }
    await update.message.reply_text("🗑 Sessione azzerata. Buona nuova giornata!")


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

DIARIO DEL GIORNO (messaggi del capocantiere):
{diario}

ISTRUZIONI:
- Prima riga esatta: "Oggetto: Report giornaliero – Cimolai Monfalcone – {data}"
- Riga vuota
- Poi corpo email con sezioni: operatori presenti, attività NDT svolte, anomalie/non conformità, note generali
- Usa terminologia tecnica NDT corretta
- Se ci sono anomalie evidenziale chiaramente
- Se ci sono foto scrivi "In allegato {n_foto} foto documentazione" in fondo al corpo
- Concludi con firma del capocantiere per conto di Control
- Tono professionale e diretto, max 300 parole"""

    risposta = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return risposta.content[0].text


async def cmd_anteprima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)

    if not sessione["messaggi"] and not sessione["foto"]:
        await update.message.reply_text("📭 Nessuna annotazione oggi.")
        return

    await update.message.reply_text("⏳ Genero anteprima...")

    try:
        data = datetime.now().strftime("%d/%m/%Y")
        testo = genera_testo_email(sessione["messaggi"], len(sessione["foto"]), data)
        await update.message.reply_text(
            f"👀 *ANTEPRIMA*\n\n{testo}\n\n_Usa /report per ricevere tutto con le foto_",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Errore anteprima: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessione = get_sessione(chat_id)

    if not sessione["messaggi"] and not sessione["foto"]:
        await update.message.reply_text("📭 Nessuna annotazione oggi.")
        return

    await update.message.reply_text("⏳ Genero il report con Claude...")

    try:
        data = datetime.now().strftime("%d/%m/%Y")
        testo_email = genera_testo_email(sessione["messaggi"], len(sessione["foto"]), data)

        # Manda il testo pronto
        await update.message.reply_text(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📋 *COPIA QUESTO TESTO*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{testo_email}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📧 *Invia a:*\n"
            "beatrice.mercatali@controlmercatali.it\n"
            "marco.sutera@controlmercatali.it",
            parse_mode="Markdown"
        )

        # Rimanda tutte le foto
        if sessione["foto"]:
            await update.message.reply_text(
                f"📷 *Ecco le {len(sessione['foto'])} foto — salvale e allegale:*",
                parse_mode="Markdown"
            )
            for i, f in enumerate(sessione["foto"]):
                caption_out = f"Foto {i+1}"
                if f["caption"]:
                    caption_out += f" — {f['caption']}"
                caption_out += f" (ore {f['ora']})"
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f["file_id"],
                    caption=caption_out
                )

        await update.message.reply_text(
            "✅ *Report pronto!*\n\n"
            "1. Tieni premuto sul testo → Copia\n"
            "2. Apri Gmail → Nuova email\n"
            "3. Incolla il testo\n"
            "4. Allega le foto\n"
            "5. Invia!\n\n"
            "Usa /reset per iniziare domani 👷",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Errore report: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


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
