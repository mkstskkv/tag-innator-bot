import asyncio
import json
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer

# ================== НАСТРОЙКИ ==================
TOKEN = os.getenv("TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

# === Volume для Railway ===
DATA_DIR = "/data"                                   # ← сюда монтируется Volume
DATA_FILE = os.path.join(DATA_DIR, "tag_data.json")

# Создаём папку /data, если её ещё нет
os.makedirs(DATA_DIR, exist_ok=True)

if not TOKEN or not CHAT_ID:
    raise ValueError("Не заданы TOKEN или CHAT_ID!")

# ===============================================

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Ошибка чтения {DATA_FILE}: {e}")
    return {"poll_employment_id": None, "poll_roles_id": None, "user_votes": {}}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Данные сохранены в {DATA_FILE}")
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")

data = load_data()

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === ВАРИАНТЫ ===
EMPLOYMENT_OPTIONS = [
    "WrS — Есть работа [в штате студии]",
    "WrF — Есть работа [фрилансер]",
    "Wr+ — Есть работа, но могу взять еще проект",
    "nWr — Безработный, Ищу работу",
]

ROLE_OPTIONS = [
    "Dir — реж анимации",
    "ScW — сценарист",
    "CnA — концепт артист",
    "2dA — 2д аниматор",
    "3dA — 3д аниматор",
    "StB — раскадровщик",
    "3dM — моделлер",
    "Rig — риггер",
    "Txt — текстурщик",
    "BgA — художник-фонарь",
    "Vfx — vfx-артист",
    "CgA — cg-artist",
]

def get_code(option_text: str) -> str:
    return option_text.split(" — ")[0]

def build_tag(employment: str | None, roles: list[str]) -> str:
    roles = [r for r in roles if r and r != "---"][:3]
    tag = ""
    if employment and employment != "---":
        tag += f"[{employment}]"
    if roles:
        tag += ",".join(roles)
    return tag[:16]


# ================== КОМАНДА ДЛЯ ПРОВЕРКИ VOLUME ==================
@dp.message(Command("check_volume"))
async def cmd_check_volume(message: Message):
    if message.chat.id != CHAT_ID:
        return

    files = os.listdir(DATA_DIR)
    file_size = os.path.getsize(DATA_FILE) if os.path.exists(DATA_FILE) else 0

    text = f"📁 **Проверка Volume**\n\n"
    text += f"Папка: `{DATA_DIR}`\n"
    text += f"Файлы в папке: {files}\n"
    text += f"Размер tag_data.json: {file_size / 1024:.1f} KB\n\n"
    text += f"Путь к файлу: `{DATA_FILE}`"

    await message.answer(text, parse_mode="Markdown")


# ================== НАСТРОЙКА ОПРОСОВ ==================
@dp.message(Command("setup_tags"))
async def cmd_setup(message: Message):
    if message.chat.id != CHAT_ID:
        return await message.answer("❌ Только в основной группе")

    thread_id = getattr(message, 'message_thread_id', None)

    try:
        emp_poll = await bot.send_poll(
            chat_id=CHAT_ID,
            message_thread_id=thread_id,
            question="📋 Ваша текущая занятость (выберите ОДИН вариант)",
            options=EMPLOYMENT_OPTIONS,
            is_anonymous=False,
            allows_multiple_answers=False,
        )

        await bot.pin_chat_message(chat_id=CHAT_ID, message_id=emp_poll.message_id, disable_notification=True)
        data["poll_employment_id"] = emp_poll.poll.id

        role_poll = await bot.send_poll(
            chat_id=CHAT_ID,
            message_thread_id=thread_id,
            question="🎨 Ваши должности (можно несколько)",
            options=ROLE_OPTIONS,
            is_anonymous=False,
            allows_multiple_answers=True,
        )

        await bot.pin_chat_message(chat_id=CHAT_ID, message_id=role_poll.message_id, disable_notification=True)
        data["poll_roles_id"] = role_poll.poll.id

        save_data(data)

        await message.answer(
            "✅ Опросы созданы в этом топике!\n\n"
            "Голосуйте — теги будут обновляться автоматически."
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка при создании опросов:\n{str(e)}")


# ================== ОБРАБОТКА ГОЛОСОВАНИЯ ==================
@dp.poll_answer()
async def on_poll_answer(poll_answer: PollAnswer):
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id
    option_ids = poll_answer.option_ids

    if poll_id not in (data.get("poll_employment_id"), data.get("poll_roles_id")):
        return

    uid = str(user_id)
    if uid not in data["user_votes"]:
        data["user_votes"][uid] = {"employment": None, "roles": []}

    votes = data["user_votes"][uid]

    if poll_id == data.get("poll_employment_id"):
        votes["employment"] = get_code(EMPLOYMENT_OPTIONS[option_ids[0]]) if option_ids else None
    else:
        votes["roles"] = [get_code(ROLE_OPTIONS[i]) for i in option_ids]

    save_data(data)

    tag = build_tag(votes.get("employment"), votes.get("roles", []))
    try:
        await bot.set_chat_member_tag(
            chat_id=CHAT_ID,
            user_id=user_id,
            tag=tag if tag else ""
        )
        print(f"✅ Тег обновлён для {user_id}: {tag or '(пустой)'}")
    except Exception as e:
        print(f"❌ Ошибка тега для {user_id}: {e}")


# ================== ДРУГИЕ КОМАНДЫ ==================
@dp.message(Command("my_tag"))
async def cmd_my_tag(message: Message):
    if message.chat.id != CHAT_ID:
        return
    uid = str(message.from_user.id)
    if uid not in data["user_votes"]:
        return await message.answer("Вы ещё не голосовали.")

    votes = data["user_votes"][uid]
    tag = build_tag(votes.get("employment"), votes.get("roles", []))
    await message.answer(
        f"Ваш тег: <b>{tag or 'нет'}</b>\n"
        f"Занятость: {votes.get('employment') or '—'}\n"
        f"Должности: {', '.join(votes.get('roles', [])) or '—'}",
        parse_mode="HTML"
    )


@dp.message(Command("refresh_all_tags"))
async def cmd_refresh_all_tags(message: Message):
    if message.chat.id != CHAT_ID:
        return
    await message.answer("Начинаю обновление тегов...")
    count = 0
    for uid_str, votes in data["user_votes"].items():
        try:
            await bot.set_chat_member_tag(
                chat_id=CHAT_ID,
                user_id=int(uid_str),
                tag=build_tag(votes.get("employment"), votes.get("roles", [])) or ""
            )
            count += 1
        except:
            pass
    await message.answer(f"✅ Обновлено тегов: {count}")


@dp.message(Command("check_rights"))
async def cmd_check_rights(message: Message):
    if message.chat.id != CHAT_ID:
        return
    member = await bot.get_chat_member(CHAT_ID, bot.id)
    await message.answer(
        f"Статус бота: {member.status}\n"
        f"can_manage_tags: {getattr(member, 'can_manage_tags', False)}"
    )


# ================== ЗАПУСК ==================
async def main():
    me = await bot.get_me()
    print(f"🤖 Бот запущен: @{me.username} | ID: {me.id}")
    print(f"📁 Данные сохраняются в: {DATA_FILE}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
