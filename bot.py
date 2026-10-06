import asyncio
import os
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

DB = "deals.db"
dp = Dispatcher()


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            creator_username TEXT,
            deal_type TEXT NOT NULL,
            nft TEXT NOT NULL,
            price TEXT NOT NULL,
            participant TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


class DealForm(StatesGroup):
    deal_type = State()
    nft = State()
    price = State()
    participant = State()
    confirmation = State()


def type_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Покупка", callback_data="type:Покупка")
    kb.button(text="💰 Продажа", callback_data="type:Продажа")
    kb.button(text="🔄 Обмен", callback_data="type:Обмен")
    kb.adjust(1)
    return kb.as_markup()


def confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Создать сделку", callback_data="confirm:create")
    kb.button(text="✏️ Изменить", callback_data="confirm:edit")
    kb.button(text="❌ Отмена", callback_data="confirm:cancel")
    kb.adjust(1)
    return kb.as_markup()


def deal_kb(deal_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Обновить статус", callback_data=f"status:{deal_id}")
    kb.button(text="❌ Отменить сделку", callback_data=f"cancel:{deal_id}")
    kb.adjust(1)
    return kb.as_markup()


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🤝 Добро пожаловать!\n\n"
        "Для создания сделки используйте /deal.\n"
        "Для просмотра своих сделок используйте /mydeals."
    )


@dp.message(Command("deal"))
async def deal(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(DealForm.deal_type)
    await message.answer("🤝 Создание сделки\n\nВыберите тип:", reply_markup=type_kb())


@dp.callback_query(DealForm.deal_type, F.data.startswith("type:"))
async def choose_type(call: CallbackQuery, state: FSMContext):
    value = call.data.split(":", 1)[1]
    await state.update_data(deal_type=value)
    await state.set_state(DealForm.nft)
    await call.message.edit_text(f"Тип сделки: {value}\n\n🖼 Отправьте ссылку или название NFT:")
    await call.answer()


@dp.message(DealForm.nft)
async def nft(message: Message, state: FSMContext):
    await state.update_data(nft=message.text or "")
    await state.set_state(DealForm.price)
    await message.answer("💵 Укажите цену сделки (например: 100 TON):")


@dp.message(DealForm.price)
async def price(message: Message, state: FSMContext):
    await state.update_data(price=message.text or "")
    await state.set_state(DealForm.participant)
    await message.answer("👤 Укажите @username второго участника:")


@dp.message(DealForm.participant)
async def participant(message: Message, state: FSMContext):
    await state.update_data(participant=message.text or "")
    data = await state.get_data()
    await state.set_state(DealForm.confirmation)
    await message.answer(
        "📋 Данные сделки\n\n"
        f"Тип: {data['deal_type']}\n"
        f"NFT: {data['nft']}\n"
        f"Цена: {data['price']}\n"
        f"Участник: {data['participant']}\n\n"
        "Проверьте данные перед созданием.",
        reply_markup=confirm_kb()
    )


@dp.callback_query(DealForm.confirmation, F.data == "confirm:create")
async def create(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    con = db()
    cur = con.execute(
        """INSERT INTO deals
        (creator_id, creator_username, deal_type, nft, price, participant, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (call.from_user.id, call.from_user.username or "", data["deal_type"],
         data["nft"], data["price"], data["participant"],
         "Ожидает участников", datetime.utcnow().isoformat(timespec="seconds"))
    )
    deal_id = cur.lastrowid
    con.commit()
    con.close()
    await state.clear()
    await call.message.edit_text(
        "✅ Сделка создана\n\n"
        f"🎫 Номер сделки: #{deal_id}\n"
        f"Тип: {data['deal_type']}\n"
        f"NFT: {data['nft']}\n"
        f"Цена: {data['price']}\n"
        f"Участник: {data['participant']}\n\n"
        "📌 Статус: Ожидает участников",
        reply_markup=deal_kb(deal_id)
    )
    await call.answer("Сделка создана")


@dp.callback_query(DealForm.confirmation, F.data == "confirm:edit")
async def edit(call: CallbackQuery, state: FSMContext):
    await state.set_state(DealForm.nft)
    await call.message.edit_text("✏️ Изменение сделки.\n\n🖼 Отправьте NFT заново:")
    await call.answer()


@dp.callback_query(DealForm.confirmation, F.data == "confirm:cancel")
async def cancel_creation(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Создание сделки отменено.")
    await call.answer()


@dp.callback_query(F.data.startswith("status:"))
async def status(call: CallbackQuery):
    deal_id = int(call.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    con.close()
    if not row:
        await call.answer("Сделка не найдена", show_alert=True)
        return
    await call.message.edit_text(
        f"🎫 Сделка #{row['id']}\n\n"
        f"Тип: {row['deal_type']}\n"
        f"NFT: {row['nft']}\n"
        f"Цена: {row['price']}\n"
        f"Участник: {row['participant']}\n\n"
        f"📌 Статус: {row['status']}",
        reply_markup=deal_kb(row["id"])
    )
    await call.answer()


@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_deal(call: CallbackQuery):
    deal_id = int(call.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM deals WHERE id = ? AND creator_id = ?",
                      (deal_id, call.from_user.id)).fetchone()
    if not row:
        con.close()
        await call.answer("Отменить эту сделку нельзя", show_alert=True)
        return
    con.execute("UPDATE deals SET status = ? WHERE id = ?", ("Отменена", deal_id))
    con.commit()
    con.close()
    await call.message.edit_text(f"❌ Сделка #{deal_id} отменена.")
    await call.answer("Отменено")


@dp.message(Command("mydeals"))
async def mydeals(message: Message):
    con = db()
    rows = con.execute(
        "SELECT * FROM deals WHERE creator_id = ? ORDER BY id DESC LIMIT 10",
        (message.from_user.id,)
    ).fetchall()
    con.close()
    if not rows:
        await message.answer("У вас пока нет сделок.")
        return
    text = "📋 Ваши последние сделки:\n\n"
    for row in rows:
        text += f"#{row['id']} — {row['deal_type']}\nNFT: {row['nft']}\nСтатус: {row['status']}\n\n"
    await message.answer(text)


async def main():
    init_db()
    bot = Bot(TOKEN)
    print("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
