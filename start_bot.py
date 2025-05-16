#importam librariile necesare
import os               # pentru a lucra cu fisiere si directoare
import time             # pentru gestionarea timpului (expirarea codului QR)
import asyncio          # pentru operatiuni asincrone (functii asincrone)
import qrcode           # pentru a genera coduri QR       

# importam librariile necesare pentru botul de pe Telegram
from telegram import Update # pentru a lucra cu actualizari si mesaje Telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Tokenul API pentru botul Telegram, cu scopul accesarii botului
API_TOKEN = "7057441924:AAFXGrj8Qcwtv187uhaoqJJFlNF_vXV8WB4"

# Fisierul in care sunt stocate placutele de inmatriculare autorizate + codurile personale
PLATE_FILE = "plates.txt"

# Folder temporar in care salvam codurile QR generate, ce vor fi invalidate dupa 30 de secunde
TEMP_QR_FOLDER = "temp_qr"

# Durata de valabilitate a codului QR in secunde
QR_VALIDITY = 30

# Dictionar pentru a stoca placutele de inmatriculare si codurile personale
# Format: {placuta: cod}
PLATE_CODES = {}

# Starea fiecarui utilizator (ex: daca trebuie sa introduca codul si / sau placuta pentru a accesa botului)
USER_STATE = {}  # user_id: "awaiting_code" / "awaiting_plate" / "authorized"

# Aici se stocheaza utilizatorii autorizati
AUTHORIZED_USERS = {}

# Citeste din fisierul "plates.txt" toate placutele si codurile aferente
def load_plates():
    codes = {}
    try:
        with open(PLATE_FILE, 'r') as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) == 2:
                    plate, code = parts
                    codes[plate.strip().upper()] = code.strip()
    except FileNotFoundError:
        pass
    return codes

# Incarcam placutele in memorie la pornirea botului
PLATE_CODES = load_plates()

# Functie care invalideaza / sterge codul QR dupa 30 de secunde (timpul stabilit)
async def schedule_deletion(app: Application, chat_id, message_id, filename):
    await asyncio.sleep(QR_VALIDITY)
    await app.bot.delete_message(chat_id=chat_id, message_id=message_id)
    if os.path.exists(filename):
        os.remove(filename)

# Comanda /start - incepe interactiunea cu botul in aplicatia Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    USER_STATE[user_id] = "awaiting_code" # setam starea utilizatorului ca "asteapta codul personal"
    await update.message.reply_text("🔒 Introdu codul tau secret pt. a incepe:")

# Gestioneaza orice mesaj text trimis de utilizator (exceptie facand comenzile)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip() # mesajul trimis de utilizator
    # Verificam daca utilizatorul a trimis un mesaj text
    chat_id = update.effective_chat.id

    # Daca utilizatorul nu are o stare (autorizat sau nu), incepem prin a cere codul personal
    if user_id not in USER_STATE:
        USER_STATE[user_id] = "awaiting_code"
        await update.message.reply_text("🔒 Introdu codul tau secret pt. a începe:")
        return

    # Aici se afla starea curenta a utilizatorului
    state = USER_STATE[user_id]

    # Starea in care botul asteapta codul personal
    if state == "awaiting_code":
        if text in PLATE_CODES.values(): # daca codul introdus exista in lista
            USER_STATE[user_id] = "awaiting_plate" # trecem la psaul urmator
            context.user_data["secret_code"] = text # salvam codul pentru verificare ulterioara
            await update.message.reply_text("✅ Cod acceptat. Trimite nr tau de inmatriculare:")
        else:
            await update.message.reply_text("❌ Cod incorect. Incearca din nou.")

    # Starea in care botul asteapta numarul de inmatriculare
    elif state == "awaiting_plate":
        plate = text.upper()
        expected_code = context.user_data.get("secret_code")
        if PLATE_CODES.get(plate) == expected_code:
            AUTHORIZED_USERS[user_id] = plate
            USER_STATE[user_id] = "authorized"
            await update.message.reply_text(f"✅ Nr validat: {plate}. Trimite /getqr pentru a primi un cod QR.")
        else:
            await update.message.reply_text("❌ Nr nevalid sau cod incorect.")

    # Starea in care utilizatorul este deja autorizat
    elif state == "authorized":
        await update.message.reply_text("✅ Esti deja autorizat. Trimite /getqr pentru a primi codul QR.")

# Comanda /getqr - genereaza si trimite un cod QR pentru utilizatorul autorizat
async def get_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Daca utilizatorul nu este autorizat complet (placuta + cod), ii cerem sa introduca datele
    if USER_STATE.get(user_id) != "authorized":
        await update.message.reply_text("⚠️ Trebuie sa introduci mai întai codul si nr de inmatriculare.")
        return

    plate = AUTHORIZED_USERS[user_id]
    code = PLATE_CODES.get(plate)
    timestamp = int(time.time()) # folosit pentru a arata valabilitatea QR-ului
    # Generam codul QR in formatul: placuta|cod|timestamp
    qr_data = f"{plate}|{code}|{timestamp}"  # QR format

    # Verificam daca folderul pentru codurile QR temporare exista, altfel il cream
    if not os.path.exists(TEMP_QR_FOLDER):
        os.makedirs(TEMP_QR_FOLDER)
    filename = os.path.join(TEMP_QR_FOLDER, f"{user_id}.png")

    # Generam codul QR si il salvam in fisier
    qr = qrcode.make(qr_data)
    qr.save(filename)

    # Trimitem codul QR utilizatorului
    msg = await context.bot.send_photo(chat_id=chat_id, photo=open(filename, 'rb'),
                                       caption="⏱️ Cod QR valid 30 secunde")

    # Programam invalidarea si stergerea codului QR dupa 30 de secunde
    await schedule_deletion(context.application, chat_id, msg.message_id, filename)

# Functia principala care porneste botul
def main():
    app = Application.builder().token(API_TOKEN).build()

    # Asociem comenzile si mesajele cu functiile corespunzatoare
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getqr", get_qr))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Botul rulează...")
    app.run_polling() # asculta si raspunde continuu la mesaje

# Pornim aplicatia
if __name__ == "__main__":
    main()
