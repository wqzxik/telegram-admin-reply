import os
import re
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply,
)


# =========================
# НАСТРОЙКИ
# =========================

ADMIN_BOT_TOKEN = os.environ["ADMIN_BOT_TOKEN"]
MAIN_BOT_TOKEN = os.environ["MAIN_BOT_TOKEN"]

ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])

ADMIN_IDS = {
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip()
}


# =========================
# БОТЫ
# =========================

admin_bot = Bot(token=ADMIN_BOT_TOKEN)
main_bot = Bot(token=MAIN_BOT_TOKEN)

dp = Dispatcher()


# Кто сейчас отвечает на какую заявку
waiting_for_reply = {}


# =========================
# КОМАНДА /id
# =========================

@dp.message(Command("id"))
async def show_ids(message: Message):
    await message.answer(
        f"Ваш Telegram ID: {message.from_user.id}\n"
        f"ID этого чата: {message.chat.id}"
    )


# =========================
# НАЖАТИЕ «ОТВЕТИТЬ»
# =========================

@dp.callback_query(F.data.startswith("reply:"))
async def reply_button(callback: CallbackQuery):

    admin_id = callback.from_user.id

    # Проверяем, разрешён ли этот администратор
    if admin_id not in ADMIN_IDS:
        await callback.answer(
            "У вас нет доступа.",
            show_alert=True
        )
        return

    # Получаем ID пользователя
    user_id = int(callback.data.split(":")[1])

    # Запоминаем, кому будет отправлен следующий ответ
    waiting_for_reply[admin_id] = user_id

    await callback.answer("Готово")

    await callback.message.answer(
        f"✍️ Напишите ответ пользователю.\n\n"
        f"ID пользователя: {user_id}",
        reply_markup=ForceReply(
            input_field_placeholder="Введите ответ..."
        )
    )


# =========================
# СООБЩЕНИЯ В АДМИНСКОЙ ГРУППЕ
# =========================

@dp.message(F.chat.id == ADMIN_CHAT_ID)
async def group_message(message: Message):

    # -------------------------
    # ЕСЛИ АДМИН ПИШЕТ ОТВЕТ
    # -------------------------

    if message.from_user and not message.from_user.is_bot:

        admin_id = message.from_user.id

        if admin_id in waiting_for_reply:

            user_id = waiting_for_reply.pop(admin_id)

            # Проверяем права ещё раз
            if ADMIN_IDS and admin_id not in ADMIN_IDS:
                return

            text = message.text

            if not text:
                await message.answer(
                    "❗ Пожалуйста, отправьте именно текстовый ответ."
                )

                waiting_for_reply[admin_id] = user_id
                return

            try:
                # ВАЖНО:
                # сообщение отправляется именно ОСНОВНЫМ Robochat-ботом
                await main_bot.send_message(
                    chat_id=user_id,
                    text=text
                )

                await message.answer(
                    "✅ Ответ отправлен пользователю."
                )

            except Exception as error:
                await message.answer(
                    "❌ Не удалось отправить сообщение пользователю.\n\n"
                    f"Ошибка: {error}"
                )

            return

    # -------------------------
    # ИЩЕМ НОВУЮ ЗАЯВКУ
    # -------------------------

    text = message.text or message.caption or ""

    # Ищем строку:
    # Айди: 8201535974
    match = re.search(
        r"Айди:\s*(\d+)",
        text
    )

    if not match:
        return

    user_id = int(match.group(1))

    # Создаём кнопку
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Ответить",
                    callback_data=f"reply:{user_id}"
                )
            ]
        ]
    )

    # Отправляем отдельное сообщение с кнопкой.
    # Мы НЕ пытаемся редактировать сообщение Robochat,
    # потому что оно отправлено другим ботом.
    await message.answer(
        "💬 Управление заявкой:",
        reply_markup=keyboard,
        reply_to_message_id=message.message_id
    )


# =========================
# ЗАПУСК
# =========================

async def main():

    print("Admin bot started")

    await dp.start_polling(admin_bot)


if __name__ == "__main__":
    asyncio.run(main())
