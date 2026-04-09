import asyncio
import json
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer

# ================== НАСТРОЙКИ ==================
TOKEN = os.getenv("TOKEN")          # ← Замени
CHAT_ID = int(os.getenv("CHAT_ID"))                   # ← Твой ID группы                

if not TOKEN or not CHAT_ID:
    raise ValueError("Не заданы TOKEN или CHAT_ID!")

DATA_FILE = "tag_data.json"
# ===============================================

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"poll_employment_id": None, "poll_roles_id": None, "user_votes": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === ВАРИАНТЫ (12 ролей — лимит Telegram) ===
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
    roles = [r for r in roles if r and r != "---"][:3]   # максимум 3 роли
    tag = ""
    if employment and employment != "---":
        tag += f"[{employment}]"
    if roles:
        tag += ",".join(roles)
    return tag[:16]   # жёсткий лимит Telegram

# ================== НАСТРОЙКА ОПРОСОВ ==================
@dp.message(Command("setup_tags"))
async def cmd_setup(message: Message):
    if message.chat.id != CHAT_ID:
        return await message.answer("❌ Только в основной группе")

    # Получаем ID топика (если команда вызвана в топике)
    thread_id = getattr(message, 'message_thread_id', None)

    try:
        # === Опрос по занятости ===
        emp_poll = await bot.send_poll(
            chat_id=CHAT_ID,
            message_thread_id=thread_id,
            question="📋 Ваша текущая занятость (выберите ОДИН вариант)",
            options=EMPLOYMENT_OPTIONS,
            is_anonymous=False,
            allows_multiple_answers=False,
            allows_revoting=True,
        )

        
        await bot.pin_chat_message(
            chat_id=CHAT_ID,
            message_id=emp_poll.message_id,
            disable_notification=True
        )
        data["poll_employment_id"] = emp_poll.poll.id

        # === Опрос по должностям ===
        role_poll = await bot.send_poll(
            chat_id=CHAT_ID,
            message_thread_id=thread_id,
            question="🎨 Ваши должности (можно несколько)",
            options=ROLE_OPTIONS,
            is_anonymous=False,
            allows_multiple_answers=True,
            allows_revoting=True,
        )

        await bot.pin_chat_message(
            chat_id=CHAT_ID,
            message_id=role_poll.message_id,
            disable_notification=True
        )
        data["poll_roles_id"] = role_poll.poll.id

        save_data(data)

        await message.answer(
            "✅ Опросы созданы **в этом топике**!\n\n"
            "Голосуйте — список статусов будет обновляться автоматически.",
            message_thread_id=thread_id
        )

        await update_status_message(thread_id=thread_id)

    except Exception as e:
        error_text = f"❌ Ошибка при создании опросов:\n{str(e)}"
        await message.answer(error_text, message_thread_id=thread_id)

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
    else:  # роли
        votes["roles"] = [get_code(ROLE_OPTIONS[i]) for i in option_ids]

    save_data(data)

    # Пытаемся поставить тег
    tag = build_tag(votes.get("employment"), votes.get("roles", []))
    try:
        await bot.set_chat_member_tag(
            chat_id=CHAT_ID,
            user_id=user_id,
            tag=tag if tag else ""
        )
        print(f"✅ Тег обновлён для {user_id}: {tag or '(пустой)'}")
    except Exception as e:
        error_str = str(e)
        print(f"❌ Ошибка тега для {user_id}: {error_str}")

# ================== КОМАНДЫ ==================
@dp.message(Command("check_rights"))
async def cmd_check_rights(message: Message):
    if message.chat.id != CHAT_ID:
        return
    try:
        member = await bot.get_chat_member(CHAT_ID, bot.id)
        await message.answer(
            f"Статус: {member.status}\n"
            f"can_manage_tags: {getattr(member, 'can_manage_tags', False)}\n"
            f"can_be_edited: {getattr(member, 'can_be_edited', False)}"
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

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
    await message.answer("Начинаю обновление тегов для всех проголосовавших...")
    count = 0
    for uid_str, votes in data["user_votes"].items():
        try:
            user_id = int(uid_str)
            tag = build_tag(votes.get("employment"), votes.get("roles", []))
            await bot.set_chat_member_tag(
                chat_id=CHAT_ID,
                user_id=user_id,
                tag=tag if tag else ""
            )
            count += 1
        except:
            pass
    await message.answer(f"✅ Обновлено тегов: {count}")

# ================== ЗАПУСК ==================
async def main():
    print("🤖 Бот запущен. ID бота:", bot.id)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())