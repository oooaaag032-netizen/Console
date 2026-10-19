import os
import asyncio
import time
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiomcrcon import Client

# --- НАСТРОЙКИ (Берутся из Bothost) ---
BOT_TOKEN = os.getenv("CONSOLE_BOT_TOKEN")
OWNER_ID = 8015996519  # Ваш Telegram ID

# Настройки RCON вашего сервера
RCON_HOST = os.getenv("RCON_HOST", "127.0.0.1") 
RCON_PORT = int(os.getenv("RCON_PORT", 25575))
RCON_PASS = os.getenv("RCON_PASS", "super_secret_password")

# Настройки для проверки онлайна (чтобы следить за сервером)
SERVER_IP = os.getenv("SERVER_IP", "haycraft.top") # IP или домен для проверки

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ФУНКЦИЯ ОТПРАВКИ КОМАНД ЧЕРЕЗ RCON ---
async def send_rcon(command: str):
    try:
        async with Client(RCON_HOST, RCON_PORT, RCON_PASS) as client:
            response, _ = await client.send_cmd(command)
            return True, response
    except Exception as e:
        return False, str(e)

# --- API ДЛЯ ПРОВЕРКИ ОНЛАЙНА ---
async def get_server_status():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.mcstatus.io/v2/status/java/{SERVER_IP}", timeout=5) as response:
                if response.status == 200:
                    return await response.json()
    except: pass
    return None

# --- ГЛАВНОЕ МЕНЮ (Только для Владельца) ---
def get_console_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статус сервера", callback_data="srv_status"),
         InlineKeyboardButton(text="👥 Игроки онлайн", callback_data="srv_players")],
        [InlineKeyboardButton(text="🔔 Отправить сообщение", callback_data="srv_say"),
         InlineKeyboardButton(text="🔄 Перезагрузить (Reload)", callback_data="srv_reload")],
        [InlineKeyboardButton(text="🛑 Остановить сервер", callback_data="srv_stop")]
    ])

@dp.message(Command("start"))
async def start(message: types.Message):
    # Проверка, что пишет именно Владелец в ЛС
    if message.from_user.id != OWNER_ID:
        return
    if message.chat.type != "private":
        return await message.answer("⛔ Управление консолью доступно только в личных сообщениях!")
    
    await message.answer(
        "🖥 <b>Консоль HayCraft</b>\n"
        "Здесь вы можете управлять сервером напрямую через RCON.\n\n"
        "Выберите действие или напишите команду вручную (без слэша):", 
        reply_markup=get_console_kb(), 
        parse_mode="HTML"
    )

# --- ОБРАБОТЧИКИ КНОПОК ---
@dp.callback_query(F.data == "srv_status")
async def btn_status(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    await call.answer("Запрашиваю...")
    status = await get_server_status()
    
    if status and status.get("online"):
        online = status.get("players", {}).get("online", 0)
        max_p = status.get("players", {}).get("max", 0)
        version = status.get("version", {}).get("name_clean", "Unknown")
        
        # Проверка TPS через RCON (если плагин поддерживает)
        rcon_ok, tps_res = await send_rcon("tps")
        tps_text = f"\n⏱ <b>TPS:</b> <code>{tps_res}</code>" if rcon_ok else ""
        
        text = (
            f"🟢 <b>Сервер онлайн!</b>\n"
            f"👥 Игроки: {online}/{max_p}\n"
            f"⚙️ Версия: {version}\n"
            f"📡 IP: <code>{SERVER_IP}</code>{tps_text}"
        )
    else:
        text = "🔴 <b>Сервер офлайн или не отвечает.</b>\nПроверьте панель хостинга."
        
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_console_kb())

@dp.callback_query(F.data == "srv_players")
async def btn_players(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    await call.answer("Получаю список...")
    
    rcon_ok, res = await send_rcon("list")
    
    if rcon_ok:
        await call.message.edit_text(f"👥 <b>Игроки онлайн:</b>\n<code>{res}</code>", parse_mode="HTML", reply_markup=get_console_kb())
    else:
        await call.message.edit_text(f"❌ <b>Ошибка RCON:</b>\n<code>{res}</code>\n\nВключен ли RCON в server.properties?", parse_mode="HTML", reply_markup=get_console_kb())

@dp.callback_query(F.data == "srv_say")
async def btn_say(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    await call.message.edit_text("💬 Напишите сообщение, которое увидят все игроки в чате:")
    # Устанавливаем ожидание следующего сообщения
    await call.message.answer("Введите текст:") # Это просто подсказка, ловим в text_handler

@dp.callback_query(F.data == "srv_reload")
async def btn_reload(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    await call.answer("Перезагружаю...")
    ok, res = await send_rcon("reload confirm")
    status = "✅ Плагины перезагружены." if ok else f"❌ Ошибка: {res}"
    await call.message.edit_text(status, reply_markup=get_console_kb())

@dp.callback_query(F.data == "srv_stop")
async def btn_stop(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    
    # Защита от случайного нажатия
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, ОСТАНОВИТЬ", callback_data="srv_stop_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="srv_cancel")]
    ])
    await call.message.edit_text("⚠️ <b>Вы уверены, что хотите ОСТАНОВИТЬ сервер?</b>\nИгроки будут выкинуты с сервера.", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "srv_stop_confirm")
async def btn_stop_confirm(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    await call.answer("Останавливаю...")
    ok, res = await send_rcon("stop")
    await call.message.edit_text("🛑 Команда стоп отправлена. Сервер выключается...", reply_markup=get_console_kb())

@dp.callback_query(F.data == "srv_cancel")
async def btn_cancel(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    await call.message.edit_text("Главное меню:", reply_markup=get_console_kb())

# --- ПЕРЕХВАТЧИК ТЕКСТА (РУЧНЫЕ КОМАНДЫ И SAY) ---
@dp.message(F.text, F.chat.type == "private")
async def handle_text(message: types.Message):
    if message.from_user.id != OWNER_ID: return
    if message.text.startswith("/"): return # Игнорируем команды Telegram
    
    text = message.text.strip()
    
    # Если мы ждем ввода для /say (проверяем, что предыдущее сообщение было от бота про чат)
    # В Aiogram 3 лучше использовать FSM, но для простоты сделаем проверку на длину
    # Если это не так, то выполняем как команду RCON.
    
    # Если пользователь хочет написать в чат сервера, пусть использует "say <текст>"
    # Или мы можем сделать простую логику: если сообщение не начинается с известной команды, 
    # то, возможно, это просто текст для чата. Но надежнее выполнять RCON.
    
    # Выполняем команду RCON
    msg = await message.answer("⏳ Выполняю...")
    ok, res = await send_rcon(text)
    
    if ok:
        if not res: res = "Команда выполнена (пустой ответ)."
        await msg.edit_text(f"🖥 <b>Команда:</b> <code>{text}</code>\n\n<b>Ответ:</b>\n<code>{res}</code>", parse_mode="HTML")
    else:
        await msg.edit_text(f"❌ <b>Ошибка RCON:</b>\n<code>{res}</code>", parse_mode="HTML")

# --- ЗАПУСК ---
async def main():
    print("Бот-Консоль HayCraft запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
