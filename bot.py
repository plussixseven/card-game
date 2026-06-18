import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://your-app.railway.app")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    room_id = context.args[0] if context.args else "lobby"
    url = f"{WEB_APP_URL}?room={room_id}&uid={user.id}&name={user.first_name}"
    keyboard = [[InlineKeyboardButton(
        "🃏 Играть",
        web_app=WebAppInfo(url=url)
    )]]
    await update.message.reply_text(
        f"Привет, {user.first_name}! 🃏\n\nНажми кнопку чтобы войти в игру.\n"
        f"Комната: `{room_id}`\n\nПоделись командой с друзьями:\n`/start {room_id}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import uuid
    room_id = str(uuid.uuid4())[:8]
    user = update.effective_user
    url = f"{WEB_APP_URL}?room={room_id}&uid={user.id}&name={user.first_name}"
    keyboard = [[InlineKeyboardButton("🃏 Создать комнату", web_app=WebAppInfo(url=url))]]
    await update.message.reply_text(
        f"Новая комната создана!\nПоделись с друзьями:\n`/start {room_id}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_game))
    app.run_polling()


if __name__ == "__main__":
    main()
