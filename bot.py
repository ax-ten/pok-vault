import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, CallbackContext
from datetime import datetime, timedelta
from auction import AuctionDB, Valuta
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes


def authorized_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("Non sei autorizzato a eseguire questa azione.")
            logging.getLogger().error(f"Not authorized {func.__name__} {update.effective_user.name} ")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


# Timeout per l'asta (30 minuti)
AUCTION_TIMEOUT = timedelta(minutes=30)
EMOJIS = ["🔥", "💧", "🌲"]
user_state = {}


@authorized_only
async def start_auction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.getLogger().log(logging.WARNING, context._chat_id)
    user_id = update.message.from_user.id
    user_state[user_id] = {
            "state": "awaiting_photo",
            "photos": [],
            "card_names": []
        }
    await update.message.reply_text("Inviami la foto della prima carta per l'asta.")



async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce la ricezione delle foto per l'asta."""
    user_id = update.message.from_user.id
    if user_id not in user_state:
        return

    # Memorizza la foto
    photo = update.message.photo[-1].file_id
    user_state[user_id]["photo"] = photo

    try:
        card_names = update.message.caption.splitlines()
        if len(card_names) == 3:
            user_state[user_id]["card_names"] = card_names
            await finalize_auction(context, user_id)
            user_state[user_id] = {}
            return
            
    except Exception as e:
        raise e
    finally:
        # Passa alla fase successiva
        user_state[user_id]["state"] = "awaiting_names"
        await update.message.reply_text("Ora inviami i nomi delle tre carte, andando a caporigo.")



async def handle_card_names(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce la ricezione dei nomi delle carte."""
    user_id = update.message.from_user.id
    if user_id not in user_state or user_state[user_id]["state"] != "awaiting_names":
        return

    card_names = update.message.text.splitlines()
    if len(card_names) == 3:
        user_state[user_id]["card_names"] = card_names
        await finalize_auction(context, user_id)
    else:
        await update.message.reply_text("Errore: invia esattamente tre nomi di carte separati da newlines.")



async def finalize_auction(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Crea le aste nel database e invia il messaggio di asta nel gruppo."""
    card_names = user_state[user_id]["card_names"]
    
    message_text = "#Asta iniziata! Scegli una carta per fare un'offerta:\n"
    keyboard = []
    for i, card_name in enumerate(card_names):
        message_text += f"{EMOJIS[i]} → {card_name}: 0\n"
        keyboard.append(InlineKeyboardButton(f'{EMOJIS[i]}', callback_data=f"offer_{card_name}"))
    
    photo = user_state[user_id]["photo"]
    reply_markup = InlineKeyboardMarkup([keyboard])
    message = await context.bot.send_photo(
        chat_id=GROUP_ID, 
        photo=photo, 
        caption=message_text, 
        reply_markup=reply_markup)
    
    for card_name in card_names:
        AuctionDB.add_active_auction(card_name, message_id=message.message_id)
    
    # Cancella lo stato temporaneo dell'utente
    del user_state[user_id]



async def handle_offer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = query.from_user
    i, card_name = query.data.split("_")

    auction = AuctionDB.get_active_auction(card_name)
    if not auction:
        await query.answer("L'asta per questa carta è già terminata.")
        return

    auction_id, last_bid = auction
    new_offer = last_bid + 1

    balance = AuctionDB.get_user_balance(user.id)
    if balance is None:
        AuctionDB.add_to_wallet(user.id, 0)
    if balance < new_offer:
        await query.answer("Saldo insufficiente per fare questa offerta.")
        return

    # Aggiorna l'offerta e il saldo dell'utente
    AuctionDB.update_bid(auction_id, new_offer, user.id)
    message_text = f"{EMOJIS[i]} {card_name} - {new_offer} (da {user.username})\n"
    await query.edit_message_text(text=message_text, reply_markup=query.message.reply_markup)



@authorized_only
async def set_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("Utilizzo: /portafogli @utente [importo]")
        return
    
    try:
        amount = int(context.args[-1])
    except ValueError:
        await update.message.reply_text("L'importo deve essere un numero intero.")
        return

    user_id, username = get_tagged_user(update)
    AuctionDB.set_user_balance(user_id, amount)
    await update.message.reply_text(f"{username} ora ha {amount}₽")



def get_tagged_user(update: Update):
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type == "text_mention":
                return entity.user.id, entity.user.username 
            if entity.type == "mention":
                pass
                # w = UsernameToChatAPI("https://localhost:1234/", "RationalGymsGripOverseas", application.bot)



# class CustomContext(CallbackContext):
#     @property
#     def wrapper(self) -> UsernameToChatAPI:
#         return self.bot_data["wrapper"]

#     async def resolve_username(self, username: str) -> Chat:
#         return await self.wrapper.resolve(username)



@authorized_only
async def end_auction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import re
    # Controlla se il comando è una risposta a un messaggio di apertura dell'asta
    if update.message.reply_to_message is None:
        await update.message.reply_text("Per terminare un'asta, rispondi al messaggio di apertura dell'asta con il comando /termina.")
        return

    original_message_text = update.message.reply_to_message.text
    auction_id = re.search(r"Asta numero: (\d+)",original_message_text)

    # Chiudi l'asta e determina il vincitore
    result = AuctionDB.end_auction(auction_id)

    if result:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result)
    else:
        await update.message.reply_text("Asta non trovata o errore nella chiusura.")



@authorized_only
async def gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Utilizzo: /gift [amount]")
        return
    
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Per favore, inserisci un importo valido.")
        return

    keyboard = [[InlineKeyboardButton(f"{amount}{Valuta.Pokédollari.value}", callback_data=f"gift_{amount}")]]

    await context.bot.send_message(
        chat_id=GROUP_ID, 
        text="Clicca qui sotto per ricevere un regalino.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id  
    amount = int(query.data.split('_')[1])

    wallet = AuctionDB.add_to_wallet(user_id, amount)
    p = Valuta.Pokédollari.value

    logging.getLogger().warning(f"{query.from_user.name} ha riscattato {amount}{p}, ne ha {wallet}{p}")
    await query.answer(f"Hai ricevuto {amount}{p}! Ora ne hai {wallet}")


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Risponde con tutte le informazioni del messaggio inviato."""

    # Ottieni l'intero messaggio come dizionario
    message_dict = update.message.to_dict()
    
    # Stampa in console per debug
    print("Messaggio ricevuto (dizionario completo):")
    print(json.dumps(message_dict, indent=2, ensure_ascii=False))
    
    if context.args:
        argument = context.args[0]
        info_text = f"Hai passato come argomento: {argument}\n"
    else:
        info_text = "Non è stato passato alcun argomento.\n"
    message = update.message

    info_text = (
        f"ID utente: {message.from_user.id}\n"
        f"Nome utente: @{message.from_user.username}\n"
        f"Nome completo: {message.from_user.full_name}\n"
        f"ID chat: {message.chat.id}\n"
        f"Tipo chat: {message.chat.type}\n"
        f"Testo del messaggio: {message.text}\n"
        f"ID messaggio: {message.message_id}\n"
        f"Data del messaggio: {message.date}\n"
    )

    # Informazioni aggiuntive, se presenti
    if message.reply_to_message:
        info_text += f"Risposta al messaggio ID: {message.reply_to_message.message_id}\n"
    if message.photo:
        info_text += f"ID della foto: {message.photo[-1].file_id}\n"
    if message.caption:
        info_text += f"Didascalia: {message.caption}\n"
    if message.location:
        info_text += f"Posizione: ({message.location.latitude}, {message.location.longitude})\n"
    if message.document:
        info_text += f"ID documento: {message.document.file_id}\n"

    await message.reply_text(info_text)



async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.getLogger().error(msg="Exception:", exc_info=context.error)



import json
def read_json():
    with open('token.json') as f:
        data = json.load(f)
    return data['bot_token'], data['mana_vault'], list(data['authorized'].values())



def main() -> None:
    """Avvia il bot."""
    global TOKEN, GROUP_ID, AUTHORIZED_USERS, application
    # Configurazione del logging
    TOKEN, GROUP_ID, AUTHORIZED_USERS = read_json()

    logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.WARNING)
    logging.info("Bot avviato")

    AuctionDB.initialize_db()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("asta", start_auction))
    application.add_handler(CommandHandler("portafogli", set_wallet))
    application.add_handler(CommandHandler("termina", end_auction_handler))    
    application.add_handler(CommandHandler("gift", gift))

    application.add_handler(CallbackQueryHandler(button, pattern="^gift_"))
    application.add_handler(CallbackQueryHandler(handle_offer, pattern="^offer_"))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(MessageHandler(filters.PHOTO & filters.User(AUTHORIZED_USERS), handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & filters.User(AUTHORIZED_USERS), handle_card_names))

    application.add_error_handler(error_handler)

    application.run_polling()

if __name__ == "__main__":
    main()

