import os
import re
import asyncio
import logging

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
# ЛОГИ
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


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
# ПРОВЕРКА НАСТРОЕК
# =========================

if not ADMIN_BOT_TOKEN:
    raise RuntimeError("ADMIN_BOT_TOKEN не задан")

if not MAIN_BOT_TOKEN:
    raise RuntimeError("MAIN_BOT_TOKEN не задан")

if not ADMIN_IDS:
    logger.warning(
        "ADMIN_IDS пустой. Кнопка «Ответить» не будет доступна администраторам."
    )


# =========================
# БОТЫ
# =========================

admin_bot = Bot(token=ADMIN_BOT_TOKEN)
main_bot = Bot(token=MAIN_BOT_TOKEN)

dp = Dispatcher()


# =========================
# СОСТОЯНИЕ ОТВЕТОВ
# =========================

# admin_id -> user_id
waiting_for_reply = {}


# =========================
# КОМАНДА /id
# =========================

@dp.message(Command("id"))
async def show_ids(message: Message):
    user_id = message.from_user.id if message.from_user else "unknown"

    await message.answer(
        f"Ваш Telegram ID: {user_id}\n"
        f"ID этого чата: {message.chat.id}"
    )

    logger.info(
        "Команда /id | chat_id=%s | user_id=%s",
        message.chat.id,
        user_id
    )


# =========================
# КНОПКА «ОТВЕТИТЬ»
# =========================

@dp.callback_query(F.data.startswith("reply:"))
async def reply_button(callback: CallbackQuery):

    if not callback.from_user:
        await callback.answer("Не удалось определить администратора.")
        return

    admin_id = callback.from_user.id

    logger.info(
        "Нажата кнопка «Ответить» | admin_id=%s | data=%s",
        admin_id,
        callback.data
    )

    # Проверяем администратора
    if admin_id not in ADMIN_IDS:
        await callback.answer(
            "У вас нет доступа.",
            show_alert=True
        )
        return

    try:
        user_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка: неправильный ID пользователя.",
            show_alert=True
        )
        return

    # Запоминаем, кому отвечать
    waiting_for_reply[admin_id] = user_id

    await callback.answer("Готово")

    if callback.message:
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

    text = message.text or message.caption or ""

    logger.info(
        "Сообщение в админ-группе | chat_id=%s | from_id=%s | "
        "is_bot=%s | text=%r",
        message.chat.id,
        message.from_user.id if message.from_user else None,
        message.from_user.is_bot if message.from_user else None,
        text
    )

    # =========================
    # ОТВЕТ АДМИНИСТРАТОРА
    # =========================

    if message.from_user and not message.from_user.is_bot:

        admin_id = message.from_user.id

        if admin_id in waiting_for_reply:

            user_id = waiting_for_reply.pop(admin_id)

            # Дополнительная проверка прав
            if ADMIN_IDS and admin_id not in ADMIN_IDS:
                logger.warning(
                    "Попытка ответа от неразрешённого администратора: %s",
                    admin_id
                )
                return

            # Нужен именно текст
            if not message.text:
                await message.answer(
                    "❗ Пожалуйста, отправьте именно текстовый ответ."
                )

                waiting_for_reply[admin_id] = user_id
                return

            logger.info(
                "Отправляем ответ пользователю | admin_id=%s | user_id=%s",
                admin_id,
                user_id
            )

            try:
                # Ответ отправляет ОСНОВНОЙ бот
                await main_bot.send_message(
                    chat_id=user_id,
                    text=message.text
                )

                await message.answer(
                    "✅ Ответ отправлен пользователю."
                )

                logger.info(
                    "Ответ успешно отправлен | user_id=%s",
                    user_id
                )

            except Exception as error:
                logger.exception(
                    "Ошибка отправки ответа пользователю %s",
                    user_id
                )

                await message.answer(
                    "❌ Не удалось отправить сообщение пользователю.\n\n"
                    f"Ошибка: {error}"
                )

            return

    # =========================
    # ИЩЕМ НОВУЮ ЗАЯВКУ
    # =========================

    # Ищем:
    # Айди: 8201535974
    #
    # Допускаем разные пробелы и регистр.

    match = re.search(
        r"айди\s*:\s*(\d+)",
        text,
        flags=re.IGNORECASE
    )

    if not match:
        logger.info(
            "Это не заявка: строка «Айди: ...» не найдена."
        )
        return

    user_id = int(match.group(1))

    logger.info(
        "Найдена новая заявка | user_id=%s",
        user_id
    )

    # =========================
    # КНОПКА ОТВЕТА
    # =========================

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

    await message.answer(
        "💬 Управление заявкой:",
        reply_markup=keyboard,
        reply_to_message_id=message.message_id
    )

    logger.info(
        "Кнопка «Ответить» создана | user_id=%s",
        user_id
    )


# =========================
# ЗАПУСК
# =========================

async def main():

    logger.info("================================")
    logger.info("Admin bot starting...")
    logger.info("ADMIN_CHAT_ID = %s", ADMIN_CHAT_ID)
    logger.info("ADMIN_IDS = %s", ADMIN_IDS)
    logger.info("================================")

    print("Admin bot started")

    await dp.start_polling(admin_bot)


# =========================
# START
# =========================

if __name__ == "__main__":
    asyncio.run(main())
