import asyncio
import logging
import os
import random
import string
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    CallbackQuery,
)

import database as db

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "HypedDealsSupport").strip().lstrip("@")
REVIEWS_CHANNEL = os.getenv("REVIEWS_CHANNEL", "HypedDealsReviews").strip().lstrip("@")

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("LotusGarantBot")

# Инициализация диспетчера
dp = Dispatcher(storage=MemoryStorage())

# Список поддерживаемых валют
CURRENCIES: Dict[str, Dict[str, Any]] = {
    "rub": {"code": "RUB", "name": "Рубли", "flag": "🇷🇺", "symbol": "₽", "min": 10},
    "uah": {"code": "UAH", "name": "Гривны", "flag": "🇺🇦", "symbol": "₴", "min": 5},
    "byn": {"code": "BYN", "name": "Буны", "flag": "🇧🇾", "symbol": "Br", "min": 1},
    "kzt": {"code": "KZT", "name": "Тенге", "flag": "🇰🇿", "symbol": "₸", "min": 50},
    "gram": {"code": "GRAM", "name": "GRAM", "flag": "💎", "symbol": "GRAM", "min": 0.1},
    "usdt": {"code": "USDT", "name": "USDT", "flag": "💵", "symbol": "USDT", "min": 0.5},
    "stars": {"code": "STARS", "name": "Stars", "flag": "⭐", "symbol": "⭐", "min": 50},
}


def get_curr_info(code_or_key: str) -> Dict[str, Any]:
    key = str(code_or_key).lower()
    if key in CURRENCIES:
        return CURRENCIES[key]
    for c in CURRENCIES.values():
        if c["code"].upper() == str(code_or_key).upper():
            return c
    return {"code": code_or_key, "name": code_or_key, "flag": "💰", "symbol": code_or_key, "min": 1}


# Машина состояний (FSM) для создания сделки
class CreateDealStates(StatesGroup):
    waiting_for_lang = State()
    waiting_for_role = State()
    waiting_for_currency = State()
    waiting_for_amount = State()
    waiting_for_nft_link = State()


# Машина состояний для отзыва
class ReviewStates(StatesGroup):
    waiting_for_review = State()


# Машина состояний для реквизитов
class RequisiteStates(StatesGroup):
    waiting_for_requisite_value = State()


def generate_deal_id(length: int = 10) -> str:
    """Генерация уникального буквенно-цифрового хеша сделки (например, muunnkr37q)."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


# ------------------ Клавиатуры ------------------

def get_main_menu_keyboard(support_user: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Главная клавиатура бота."""
    if lang == "en":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Create Deal", callback_data="create_deal")],
                [
                    InlineKeyboardButton(text="💰 Balance", callback_data="balance"),
                    InlineKeyboardButton(text="📋 My Deals", callback_data="my_deals"),
                ],
                [
                    InlineKeyboardButton(text="🪪 Requisites", callback_data="requisites"),
                    InlineKeyboardButton(text="👥 Referrals", callback_data="referrals"),
                ],
                [
                    InlineKeyboardButton(text="💬 Reviews", callback_data="reviews"),
                    InlineKeyboardButton(text="🌐 Language / Язык", callback_data="lang"),
                ],
                [
                    InlineKeyboardButton(
                        text="🆘 Tech Support ↗",
                        url=f"https://t.me/{support_user}",
                    )
                ],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Создать сделку", callback_data="create_deal")],
            [
                InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
                InlineKeyboardButton(text="📋 Мои сделки", callback_data="my_deals"),
            ],
            [
                InlineKeyboardButton(text="🪪 Мои реквизиты", callback_data="requisites"),
                InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
            ],
            [
                InlineKeyboardButton(text="💬 Отзывы", callback_data="reviews"),
                InlineKeyboardButton(text="🌐 Язык / Lang", callback_data="lang"),
            ],
            [
                InlineKeyboardButton(
                    text="🆘 Техподдержка ↗",
                    url=f"https://t.me/{support_user}",
                )
            ],
        ]
    )


def get_role_selection_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Шаг 1: Выбор роли в сделке (Продавец / Покупатель)."""
    if lang == "en":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👑 I am Seller", callback_data="role_seller")],
                [InlineKeyboardButton(text="🛍 I am Buyer", callback_data="role_buyer")],
                [InlineKeyboardButton(text="◀️ Back to menu", callback_data="back_to_menu")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 Я продавец", callback_data="role_seller")],
            [InlineKeyboardButton(text="🛍 Я покупатель", callback_data="role_buyer")],
            [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")],
        ]
    )


def get_currency_selection_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Шаг 2: Выбор валюты сделки."""
    cancel_btn = "◀️ Cancel" if lang == "en" else "◀️ Отмена"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Рубли (RUB)", callback_data="curr_rub"),
                InlineKeyboardButton(text="🇺🇦 Гривны (UAH)", callback_data="curr_uah"),
            ],
            [
                InlineKeyboardButton(text="🇧🇾 Буны (BYN)", callback_data="curr_byn"),
                InlineKeyboardButton(text="🇰🇿 Тенге (KZT)", callback_data="curr_kzt"),
            ],
            [
                InlineKeyboardButton(text="💎 GRAM", callback_data="curr_gram"),
                InlineKeyboardButton(text="💵 USDT", callback_data="curr_usdt"),
            ],
            [
                InlineKeyboardButton(text="⭐ Stars", callback_data="curr_stars"),
            ],
            [InlineKeyboardButton(text=cancel_btn, callback_data="back_to_menu")],
        ]
    )


def get_seller_deal_keyboard(deal_id: str, support_user: str, is_creator: bool = False, lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для ПРОДАВЦА (передает подарок).
    """
    if lang == "en":
        buttons = [
            [InlineKeyboardButton(text="📦 Transfer gift to manager ↗", url=f"https://t.me/{support_user}")],
            [InlineKeyboardButton(text="✅ Done - gift transferred to manager", callback_data=f"seller_gift_done_{deal_id}")],
            [InlineKeyboardButton(text="🆘 Technical Support ↗", url=f"https://t.me/{support_user}")],
        ]
        if is_creator:
            buttons.append([InlineKeyboardButton(text="📨 Share deal in chat", switch_inline_query=f"#{deal_id}")])
        buttons.append([InlineKeyboardButton(text="❌ Cancel deal", callback_data=f"cancel_deal_{deal_id}")])
        buttons.append([InlineKeyboardButton(text="◀️ Back to menu", callback_data="back_to_menu")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    buttons = [
        [InlineKeyboardButton(text="📦 Передать подарок менеджеру ↗", url=f"https://t.me/{support_user}")],
        [InlineKeyboardButton(text="✅ Готово - подарок передан менеджеру", callback_data=f"seller_gift_done_{deal_id}")],
        [InlineKeyboardButton(text="🆘 Техническая поддержка ↗", url=f"https://t.me/{support_user}")],
    ]
    if is_creator:
        buttons.append([InlineKeyboardButton(text="📨 Поделиться сделкой в чате", switch_inline_query=f"#{deal_id}")])
    buttons.append([InlineKeyboardButton(text="❌ Отказаться от сделки", callback_data=f"cancel_deal_{deal_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_buyer_waiting_keyboard(deal_id: str, support_user: str, is_creator: bool = False, lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для ПОКУПАТЕЛЯ в ожидании передачи подарка продавцом.
    """
    wait_text = "⏳ Waiting for seller..." if lang == "en" else "⏳ Ожидание передачи подарка..."
    support_text = "🆘 Technical Support ↗" if lang == "en" else "🆘 Техническая поддержка ↗"
    share_text = "📨 Share deal in chat" if lang == "en" else "📨 Поделиться сделкой в чате"
    cancel_text = "❌ Cancel deal" if lang == "en" else "❌ Отказаться от сделки"
    menu_text = "◀️ Back to menu" if lang == "en" else "◀️ Назад в меню"

    buttons = [
        [InlineKeyboardButton(text=wait_text, callback_data="buyer_waiting_notice")],
        [InlineKeyboardButton(text=support_text, url=f"https://t.me/{support_user}")],
    ]
    if is_creator:
        buttons.append([InlineKeyboardButton(text=share_text, switch_inline_query=f"#{deal_id}")])
    buttons.append([InlineKeyboardButton(text=cancel_text, callback_data=f"cancel_deal_{deal_id}")])
    buttons.append([InlineKeyboardButton(text=menu_text, callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_buyer_deal_keyboard(deal_id: str, support_user: str, is_creator: bool = False, lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для ПОКУПАТЕЛЯ (после того, как продавец передал подарок).
    """
    confirm_text = "✅ Confirm gift receipt from manager" if lang == "en" else "✅ Подтвердить передачу подарка менеджеру"
    support_text = "🆘 Technical Support ↗" if lang == "en" else "🆘 Техническая поддержка ↗"
    share_text = "📨 Share deal in chat" if lang == "en" else "📨 Поделиться сделкой в чате"
    cancel_text = "❌ Cancel deal" if lang == "en" else "❌ Отказаться от сделки"
    menu_text = "◀️ Back to menu" if lang == "en" else "◀️ Назад в меню"

    buttons = [
        [InlineKeyboardButton(text=confirm_text, callback_data=f"finish_deal_{deal_id}")],
        [InlineKeyboardButton(text=support_text, url=f"https://t.me/{support_user}")],
    ]
    if is_creator:
        buttons.append([InlineKeyboardButton(text=share_text, switch_inline_query=f"#{deal_id}")])
    buttons.append([InlineKeyboardButton(text=cancel_text, callback_data=f"cancel_deal_{deal_id}")])
    buttons.append([InlineKeyboardButton(text=menu_text, callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_deal_completed_keyboard(deal_id: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура после завершения сделки: оставить отзыв или в меню."""
    review_text = "💬 Leave Review" if lang == "en" else "💬 Оставить отзыв"
    menu_text = "◀️ Main Menu" if lang == "en" else "◀️ Главное меню"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=review_text, callback_data=f"leave_review_{deal_id}")],
            [InlineKeyboardButton(text=menu_text, callback_data="back_to_menu")],
        ]
    )


def get_back_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Кнопка возврата в меню."""
    btn_text = "◀️ Back to menu" if lang == "en" else "◀️ Назад в меню"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=btn_text, callback_data="back_to_menu")]]
    )


def get_balance_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура раздела баланса."""
    if lang == "en":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💸 Withdraw Funds", callback_data="withdraw_funds")],
                [InlineKeyboardButton(text="📜 Transactions", callback_data="transactions")],
                [InlineKeyboardButton(text="◀️ Back to menu", callback_data="back_to_menu")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💸 Вывод средств", callback_data="withdraw_funds")],
            [InlineKeyboardButton(text="📜 Транзакции", callback_data="transactions")],
            [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")],
        ]
    )


def get_requisites_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура раздела реквизитов для быстрого добавления."""
    if lang == "en":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="💳 Card RUB", callback_data="set_req_rub"),
                    InlineKeyboardButton(text="🇺🇦 Card UAH", callback_data="set_req_uah"),
                ],
                [
                    InlineKeyboardButton(text="🇧🇾 Card BYN", callback_data="set_req_byn"),
                    InlineKeyboardButton(text="🇰🇿 Card KZT", callback_data="set_req_kzt"),
                ],
                [
                    InlineKeyboardButton(text="💎 Wallet GRAM", callback_data="set_req_gram"),
                    InlineKeyboardButton(text="💵 Wallet USDT", callback_data="set_req_usdt"),
                ],
                [
                    InlineKeyboardButton(text="⭐ Username Stars", callback_data="set_req_stars"),
                ],
                [InlineKeyboardButton(text="◀️ Back to menu", callback_data="back_to_menu")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Карта RUB", callback_data="set_req_rub"),
                InlineKeyboardButton(text="🇺🇦 Карта UAH", callback_data="set_req_uah"),
            ],
            [
                InlineKeyboardButton(text="🇧🇾 Карта BYN", callback_data="set_req_byn"),
                InlineKeyboardButton(text="🇰🇿 Карта KZT", callback_data="set_req_kzt"),
            ],
            [
                InlineKeyboardButton(text="💎 Кошелёк GRAM", callback_data="set_req_gram"),
                InlineKeyboardButton(text="💵 Кошелёк USDT", callback_data="set_req_usdt"),
            ],
            [
                InlineKeyboardButton(text="⭐ Юзернейм Stars", callback_data="set_req_stars"),
            ],
            [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")],
        ]
    )


# ------------------ Тексты ------------------

def get_welcome_text(support_user: str, lang: str = "ru") -> str:
    if lang == "en":
        return (
            "💼 <b>Welcome to Lotus Dels</b> 🤝\n\n"
            "⚡️ <b>Your trusted P2P escrow:</b>\n"
            "1️⃣ Automated deals with NFTs and gifts\n"
            "2️⃣ 🛡 Complete protection for both parties\n"
            "3️⃣ 🌐 Referral program — 50% of service fee\n"
            f"4️⃣ 📦 Goods transfer via manager: @{support_user}\n\n"
            "💡 <i>Choose an action below 👇</i>"
        )
    return (
        "💼 <b>Добро пожаловать в Lotus Dels</b> 🤝\n\n"
        "⚡️ <b>Ваш надёжный P2P-гарант:</b>\n"
        "1️⃣ Автоматические сделки с NFT и подарками\n"
        "2️⃣ 🛡 Полная защита обеих сторон\n"
        "3️⃣ 🌐 Реферальная программа — 50% от комиссии\n"
        f"4️⃣ 📦 Передача товаров через менеджера: @{support_user}\n\n"
        "💡 <i>Выберите действие ниже 👇</i>"
    )


# ------------------ Обработка команды /start ------------------

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    args = message.text.split(maxsplit=1)
    param = args[1].strip() if len(args) > 1 else ""

    # Реферальная система
    referrer_id = None
    if param.startswith("ref_"):
        ref_str = param.replace("ref_", "")
        if ref_str.isdigit():
            referrer_id = int(ref_str)

    await db.get_or_create_user(user_id, username, full_name, referrer_id)

    # Переход по сделке: deal_<ID>
    if param.startswith("deal_"):
        deal_id = param.replace("deal_", "").strip()
        deal = await db.get_deal(deal_id)

        if not deal:
            await message.answer("❌ Сделка не найдена или уже удалена.", reply_markup=get_back_keyboard())
            return

        # Проверка: нельзя подключиться к своей сделке
        if deal["creator_id"] == user_id:
            await message.answer("❌ Вы не можете подключиться к своей же сделке.", parse_mode="HTML")
            return

        if deal["status"] == "cancelled":
            await message.answer("❌ Эта сделка была отменена.", reply_markup=get_back_keyboard())
            return

        if deal["status"] == "completed":
            await message.answer("✅ Эта сделка уже успешно завершена.", reply_markup=get_back_keyboard())
            return

        # При подключении сразу связываем партнера со сделкой
        await db.accept_deal(deal_id, user_id)

        creator_role = deal.get("creator_role", "seller")
        gift_sent = deal.get("gift_sent", 0)
        creator_user = await db.get_user(deal["creator_id"])
        creator_username = f"@{creator_user['username']}" if (creator_user and creator_user.get("username")) else deal["creator_name"]
        creator_deals = creator_user.get("completed_deals", 0) if creator_user else 0
        curr = get_curr_info(deal.get("currency", "RUB"))

        # ЛОГИКА РОЛЕЙ:
        # Если создатель создал сделку как "Продавец" (creator_role == 'seller'):
        # -> Создатель = ПРОДАВЕЦ (передает подарок менеджеру)
        # -> Подключившийся партнер = ПОКУПАТЕЛЬ (подтверждает получение)
        # Если создатель создал сделку как "Покупатель" (creator_role == 'buyer'):
        # -> Создатель = ПОКУПАТЕЛЬ (подтверждает получение)
        # -> Подключившийся партнер = ПРОДАВЕЦ (передает подарок менеджеру)

        user_lang = await db.get_user_language(user_id)
        creator_lang = await db.get_user_language(deal["creator_id"])

        if creator_role == "seller":
            # Создатель = ПРОДАВЕЦ. Партнер подключается как ПОКУПАТЕЛЬ.
            # 1. Уведомляем создателя (продавца)
            try:
                visitor_name = f"@{username}" if username else full_name
                if creator_lang == "en":
                    c_text = (
                        f"🔔 Buyer {visitor_name} joined your deal <b>#{deal_id}</b>!\n\n"
                        f"📦 Transfer gift to manager @{SUPPORT_USERNAME} and click «Done - gift transferred to manager» below:"
                    )
                else:
                    c_text = (
                        f"🔔 Покупатель {visitor_name} подключился к вашей сделке <b>#{deal_id}</b>!\n\n"
                        f"📦 Передайте подарок менеджеру @{SUPPORT_USERNAME} и нажмите «Готово - подарок передан менеджеру» ниже:"
                    )
                await message.bot.send_message(
                    chat_id=deal["creator_id"],
                    text=c_text,
                    reply_markup=get_seller_deal_keyboard(deal_id, SUPPORT_USERNAME, is_creator=True, lang=creator_lang),
                    parse_mode="HTML"
                )
            except Exception:
                pass

            # 2. Показываем подключившемуся покупателю карточку покупателя
            buyer_kb = (
                get_buyer_deal_keyboard(deal_id, SUPPORT_USERNAME, is_creator=False, lang=user_lang)
                if gift_sent
                else get_buyer_waiting_keyboard(deal_id, SUPPORT_USERNAME, is_creator=False, lang=user_lang)
            )
            if user_lang == "en":
                wait_text = (
                    "🔜 After the seller transfers goods to the manager — confirm gift receipt with the button below."
                    if gift_sent
                    else f"⏳ Please wait for the seller to transfer the gift to manager @{SUPPORT_USERNAME}.\nYou will be able to confirm receipt once transferred."
                )
                card_text = (
                    f"✅ <b>You joined deal #{deal_id} as buyer.</b>\n\n"
                    f"<blockquote>"
                    f"👤 <b>Seller:</b> {creator_username}\n"
                    f"📌 <b>Seller ID:</b> {deal['creator_id']}\n"
                    f"📈 <b>Seller completed deals:</b> {creator_deals}\n"
                    f"📦 <b>Description:</b> {deal['item_link']}\n"
                    f"{curr['flag']} <b>Currency:</b> {deal['currency']}\n"
                    f"💰 <b>Amount:</b> {deal['amount']:.1f}\n"
                    f"📊 <b>Service fee (3%):</b> {deal.get('fee', 0.0):.1f} {deal['currency']}\n"
                    f"💳 <b>Manager requisites (payment destination):</b> ‼️ TEMPORARILY UNAVAILABLE ‼️\n"
                    f"</blockquote>\n\n"
                    f"🛡 All payments and item delivery are handled ONLY via manager @{SUPPORT_USERNAME}.\n"
                    f"{wait_text}"
                )
            else:
                wait_text = (
                    "🔜 После передачи товара продавцом менеджеру — подтвердите передачу подарка кнопкой ниже."
                    if gift_sent
                    else f"⏳ Ожидайте, пока продавец передаст подарок менеджеру @{SUPPORT_USERNAME}.\nПосле передачи вы сможете подтвердить сделку."
                )
                card_text = (
                    f"✅ <b>Вы подключились к сделке #{deal_id} как покупатель.</b>\n\n"
                    f"<blockquote>"
                    f"👤 <b>Продавец:</b> {creator_username}\n"
                    f"📌 <b>ID продавца:</b> {deal['creator_id']}\n"
                    f"📈 <b>Сделок у продавца:</b> {creator_deals}\n"
                    f"📦 <b>Описание:</b> {deal['item_link']}\n"
                    f"{curr['flag']} <b>Валюта:</b> {deal['currency']}\n"
                    f"💰 <b>Сумма:</b> {deal['amount']:.1f}\n"
                    f"📊 <b>Комиссия сервиса (3%):</b> {deal.get('fee', 0.0):.1f} {deal['currency']}\n"
                    f"💳 <b>Реквизиты менеджера (куда придёт оплата):</b> ‼️ ВРЕМЕННО НЕ ДОСТУПНО ‼️\n"
                    f"</blockquote>\n\n"
                    f"🛡 Вся оплата и передача товара проходит ТОЛЬКО через менеджера @{SUPPORT_USERNAME}.\n"
                    f"{wait_text}"
                )
            await message.answer(
                card_text,
                reply_markup=buyer_kb,
                parse_mode="HTML",
                disable_web_page_preview=False
            )

        else:
            # Создатель = ПОКУПАТЕЛЬ. Партнер подключается как ПРОДАВЕЦ.
            # 1. Уведомляем создателя (покупателя)
            creator_buyer_kb = (
                get_buyer_deal_keyboard(deal_id, SUPPORT_USERNAME, is_creator=True, lang=creator_lang)
                if gift_sent
                else get_buyer_waiting_keyboard(deal_id, SUPPORT_USERNAME, is_creator=True, lang=creator_lang)
            )
            try:
                visitor_name = f"@{username}" if username else full_name
                if creator_lang == "en":
                    c_text = (
                        f"🔔 Seller {visitor_name} joined your deal <b>#{deal_id}</b>!\n\n"
                        f"⏳ Please wait for the seller to transfer the gift to manager @{SUPPORT_USERNAME}."
                    )
                else:
                    c_text = (
                        f"🔔 Продавец {visitor_name} подключился к вашей сделке <b>#{deal_id}</b>!\n\n"
                        f"⏳ Ожидайте, пока продавец передаст подарок менеджеру @{SUPPORT_USERNAME}."
                    )
                await message.bot.send_message(
                    chat_id=deal["creator_id"],
                    text=c_text,
                    reply_markup=creator_buyer_kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass

            # 2. Показываем подключившемуся продавцу карточку продавца
            if user_lang == "en":
                card_text = (
                    f"✅ <b>You joined deal #{deal_id} as seller.</b>\n\n"
                    f"<blockquote>"
                    f"👤 <b>Buyer:</b> {creator_username}\n"
                    f"📌 <b>Buyer ID:</b> {deal['creator_id']}\n"
                    f"📈 <b>Buyer completed deals:</b> {creator_deals}\n"
                    f"📦 <b>Description:</b> {deal['item_link']}\n"
                    f"{curr['flag']} <b>Currency:</b> {deal['currency']}\n"
                    f"💰 <b>Amount:</b> {deal['amount']:.1f}\n"
                    f"📊 <b>Service fee (3%):</b> {deal.get('fee', 0.0):.1f} {deal['currency']}\n"
                    f"💳 <b>Manager requisites (payment destination):</b> ‼️ TEMPORARILY UNAVAILABLE ‼️\n"
                    f"</blockquote>\n\n"
                    f"🛡 All payments and item delivery are handled ONLY via manager @{SUPPORT_USERNAME}.\n"
                    f"🔜 After payment is confirmed by buyer — transfer the gift to manager."
                )
            else:
                card_text = (
                    f"✅ <b>Вы подключились к сделке #{deal_id} как продавец.</b>\n\n"
                    f"<blockquote>"
                    f"👤 <b>Покупатель:</b> {creator_username}\n"
                    f"📌 <b>ID покупателя:</b> {deal['creator_id']}\n"
                    f"📈 <b>Сделок у покупателя:</b> {creator_deals}\n"
                    f"📦 <b>Описание:</b> {deal['item_link']}\n"
                    f"{curr['flag']} <b>Валюта:</b> {deal['currency']}\n"
                    f"💰 <b>Сумма:</b> {deal['amount']:.1f}\n"
                    f"📊 <b>Комиссия сервиса (3%):</b> {deal.get('fee', 0.0):.1f} {deal['currency']}\n"
                    f"💳 <b>Реквизиты менеджера (куда придёт оплата):</b> ‼️ ВРЕМЕННО НЕ ДОСТУПНО ‼️\n"
                    f"</blockquote>\n\n"
                    f"🛡 Вся оплата и передача товара проходит ТОЛЬКО через менеджера @{SUPPORT_USERNAME}.\n"
                    f"🔜 После подтверждения оплаты покупателем — передайте товар менеджеру."
                )
            await message.answer(
                card_text,
                reply_markup=get_seller_deal_keyboard(deal_id, SUPPORT_USERNAME, is_creator=False, lang=user_lang),
                parse_mode="HTML",
                disable_web_page_preview=False
            )

        return

    # Обычный старт
    user_lang = await db.get_user_language(user_id)
    await message.answer(
        get_welcome_text(SUPPORT_USERNAME, lang=user_lang),
        reply_markup=get_main_menu_keyboard(SUPPORT_USERNAME, lang=user_lang),
        parse_mode="HTML",
    )


# ------------------ Сценарий «Создать сделку» (FSM) ------------------

@dp.callback_query(F.data == "create_deal")
async def start_create_deal(callback: CallbackQuery, state: FSMContext):
    """Шаг 1: Выбор языка сделки."""
    await state.clear()
    user_id = callback.from_user.id
    user_lang = await db.get_user_language(user_id)

    text = (
        "🌐 <b>Выберите язык сделки / Select deal language:</b>\n\n"
        "На каком языке оформить сделку?\n"
        "Which language would you like to use for this deal?"
    )
    back_btn = "◀️ Back to menu" if user_lang == "en" else "◀️ Назад в меню"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="deal_lang_ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="deal_lang_en"),
            ],
            [
                InlineKeyboardButton(text=back_btn, callback_data="back_to_menu")
            ]
        ]
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(CreateDealStates.waiting_for_lang)
    await callback.answer()


@dp.callback_query(F.data.in_(["deal_lang_ru", "deal_lang_en"]))
async def select_deal_language(callback: CallbackQuery, state: FSMContext):
    """Шаг 2: Выбор роли."""
    deal_lang = "ru" if callback.data == "deal_lang_ru" else "en"
    await state.update_data(deal_lang=deal_lang)

    if deal_lang == "en":
        text = (
            "📦 <b>New deal</b>\n\n"
            "💬 <b>What is your role in this deal?</b>\n\n"
            "👑 <b>Seller</b> — you sell goods/services and receive payment.\n"
            "🛒 <b>Buyer</b> — you pay and receive goods/services."
        )
    else:
        text = (
            "📦 <b>Новая сделка</b>\n\n"
            "💬 <b>Кем вы выступаете в этой сделке?</b>\n\n"
            "👑 <b>Продавец</b> — вы продаёте товар/услугу и получаете оплату.\n"
            "🛒 <b>Покупатель</b> — вы платите и получаете товар/услугу."
        )
    try:
        await callback.message.edit_text(text, reply_markup=get_role_selection_keyboard(deal_lang), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_role_selection_keyboard(deal_lang), parse_mode="HTML")
    await state.set_state(CreateDealStates.waiting_for_role)
    await callback.answer()


@dp.callback_query(F.data.in_(["role_seller", "role_buyer"]))
async def select_deal_role(callback: CallbackQuery, state: FSMContext):
    """Шаг 3: Выбор валюты."""
    role = "seller" if callback.data == "role_seller" else "buyer"
    await state.update_data(creator_role=role)
    data = await state.get_data()
    deal_lang = data.get("deal_lang") or await db.get_user_language(callback.from_user.id)

    text = "💱 <b>Choose currency for payment:</b>" if deal_lang == "en" else "💱 <b>Выберите валюту для оплаты сделки:</b>"
    try:
        await callback.message.edit_text(text, reply_markup=get_currency_selection_keyboard(deal_lang), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_currency_selection_keyboard(deal_lang), parse_mode="HTML")
    await state.set_state(CreateDealStates.waiting_for_currency)
    await callback.answer()


@dp.callback_query(F.data.startswith("curr_"))
async def select_deal_currency(callback: CallbackQuery, state: FSMContext):
    """Шаг 4: Ввод суммы."""
    curr_key = callback.data.replace("curr_", "")
    curr = CURRENCIES.get(curr_key, CURRENCIES["rub"])
    await state.update_data(currency=curr["code"])
    data = await state.get_data()
    deal_lang = data.get("deal_lang") or await db.get_user_language(callback.from_user.id)

    if deal_lang == "en":
        text = (
            f"{curr['flag']} <b>Enter deal amount in {curr['name']} ({curr['code']}):</b>\n\n"
            "ℹ️ <b>Service fee: 3%</b>\n"
            "<i>A 3% fee is automatically deducted for the escrow service.</i>\n\n"
            "<i>For example: 1000 or 2500</i>"
        )
    else:
        text = (
            f"{curr['flag']} <b>Укажите сумму сделки в {curr['name']} ({curr['code']}):</b>\n\n"
            "ℹ️ <b>Комиссия сервиса: 3%</b>\n"
            "<i>От суммы сделки автоматически удерживается 3% в пользу сервиса-гаранта.</i>\n\n"
            "<i>Например: 1000 или 2500</i>"
        )
    cancel_kb = get_back_keyboard(deal_lang)
    try:
        await callback.message.edit_text(text, reply_markup=cancel_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=cancel_kb, parse_mode="HTML")
    await state.set_state(CreateDealStates.waiting_for_amount)
    await callback.answer()


@dp.message(CreateDealStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    """Шаг 5: Валидация суммы и расчет комиссии 3%."""
    text = message.text.strip().replace(",", ".")
    data = await state.get_data()
    curr_code = data.get("currency", "RUB")
    deal_lang = data.get("deal_lang") or await db.get_user_language(message.from_user.id)

    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        err_msg = (
            f"❌ Enter a valid positive number for amount in {curr_code}:"
            if deal_lang == "en"
            else f"❌ Введите корректное положительное число для суммы в {curr_code}:"
        )
        await message.answer(err_msg, parse_mode="HTML")
        return

    fee = round(amount * 0.03, 2)
    payout = round(amount - fee, 2)

    await state.update_data(amount=amount, fee=fee, payout=payout)

    if deal_lang == "en":
        step_msg = (
            f"💰 <b>Deal amount:</b> {amount:.2f} {curr_code}\n"
            f"📊 <b>Service fee (3%):</b> {fee:.2f} {curr_code}\n"
            f"💵 <b>To be received by seller:</b> {payout:.2f} {curr_code}\n\n"
            "📦 <b>Send link to NFT or gift:</b>\n"
            "<i>For example: </i>t.me/nft/FreshSocks-98543"
        )
    else:
        step_msg = (
            f"💰 <b>Сумма сделки:</b> {amount:.2f} {curr_code}\n"
            f"📊 <b>Комиссия сервиса (3%):</b> {fee:.2f} {curr_code}\n"
            f"💵 <b>К получению продавцом:</b> {payout:.2f} {curr_code}\n\n"
            "📦 <b>Отправьте ссылку на NFT или подарок:</b>\n"
            "<i>Например: </i>t.me/nft/FreshSocks-98543"
        )

    await message.answer(
        step_msg,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await state.set_state(CreateDealStates.waiting_for_nft_link)


@dp.message(CreateDealStates.waiting_for_nft_link)
async def process_nft_link(message: Message, state: FSMContext):
    """Шаг 6: Создание карточки сделки."""
    data = await state.get_data()
    deal_lang = data.get("deal_lang") or await db.get_user_language(message.from_user.id)
    item_link = message.text.strip()
    if not item_link:
        err_msg = "❌ Please send a valid link to NFT or gift:" if deal_lang == "en" else "❌ Пожалуйста, отправьте корректную ссылку на NFT или подарок:"
        await message.answer(err_msg)
        return

    amount = data["amount"]
    currency = data.get("currency", "RUB")
    fee = data.get("fee", round(amount * 0.03, 2))
    payout = data.get("payout", round(amount - fee, 2))
    creator_role = data.get("creator_role", "seller")
    await state.clear()

    deal_id = generate_deal_id(10)
    user_id = message.from_user.id
    creator_name = message.from_user.full_name or message.from_user.username or "Участник"

    await db.create_deal(
        deal_id=deal_id,
        creator_id=user_id,
        creator_name=creator_name,
        amount=amount,
        item_link=item_link,
        creator_role=creator_role,
        currency=currency,
        fee=fee,
        language=deal_lang
    )

    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    direct_link = f"https://t.me/{bot_username}?start=deal_{deal_id}"

    curr = get_curr_info(currency)

    if deal_lang == "en":
        role_label = "Seller" if creator_role == "seller" else "Buyer"
        counterpart_label = "buyer" if creator_role == "seller" else "seller"
        card_text = (
            f"✅ Deal <b>#{deal_id}</b> successfully created!\n\n"
            f"🛒 <b>Role:</b> {role_label}\n"
            f"{curr['flag']} <b>Currency:</b> {currency}\n"
            f"💰 <b>Deal amount:</b> {amount:.2f} {currency}\n"
            f"📊 <b>Service fee (3%):</b> {fee:.2f} {currency}\n"
            f"💵 <b>To be received by seller:</b> {payout:.2f} {currency}\n"
            f"📦 <b>Description:</b>\n{item_link}\n\n"
            f"🔗 <b>Invite link for {counterpart_label}:</b>\n"
            f"{direct_link}\n\n"
            f"Or invite via inline: type <code>@{bot_username} #{deal_id}</code> in any chat"
        )
    else:
        role_label = "Продавец" if creator_role == "seller" else "Покупатель"
        counterpart_label = "покупателя" if creator_role == "seller" else "продавца"
        card_text = (
            f"✅ Сделка <b>#{deal_id}</b> успешно создана!\n\n"
            f"🛒 <b>Роль:</b> {role_label}\n"
            f"{curr['flag']} <b>Валюта:</b> {currency}\n"
            f"💰 <b>Сумма сделки:</b> {amount:.2f} {currency}\n"
            f"📊 <b>Комиссия сервиса (3%):</b> {fee:.2f} {currency}\n"
            f"💵 <b>К получению продавцом:</b> {payout:.2f} {currency}\n"
            f"📦 <b>Описание:</b>\n{item_link}\n\n"
            f"🔗 <b>Ссылка для {counterpart_label}:</b>\n"
            f"{direct_link}\n\n"
            f"Или пригласите через инлайн: введите <code>@{bot_username} #{deal_id}</code> в любом чате"
        )

    # Если создатель — продавец, он сразу получает свои кнопки продавца + шеринг
    # Если создатель — покупатель, он ожидает пока продавец передаст подарок менеджеру
    if creator_role == "seller":
        kb = get_seller_deal_keyboard(deal_id, SUPPORT_USERNAME, is_creator=True, lang=deal_lang)
    else:
        kb = get_buyer_waiting_keyboard(deal_id, SUPPORT_USERNAME, is_creator=True, lang=deal_lang)

    await message.answer(
        card_text,
        reply_markup=kb,
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ------------------ Действие продавца: Готово - подарок передан менеджеру ------------------

@dp.callback_query(F.data.startswith("seller_gift_done_"))
async def seller_gift_done_handler(callback: CallbackQuery):
    deal_id = callback.data.replace("seller_gift_done_", "").strip()
    deal = await db.get_deal(deal_id)

    if not deal:
        await callback.answer("Сделка не найдена.", show_alert=True)
        return

    if deal["status"] == "completed":
        await callback.answer("Эта сделка уже завершена.", show_alert=True)
        return

    await db.mark_gift_sent(deal_id)

    creator_role = deal.get("creator_role", "seller")
    buyer_id = deal["buyer_id"] if creator_role == "seller" else deal["creator_id"]

    seller_lang = await db.get_user_language(callback.from_user.id)
    alert_msg = (
        "Done. Notification sent to buyer for confirmation."
        if seller_lang == "en"
        else "Готово. Покупателю отправлено уведомление для подтверждения."
    )
    await callback.answer(alert_msg, show_alert=True)

    if buyer_id:
        buyer_lang = await db.get_user_language(buyer_id)
        if buyer_lang == "en":
            notif_text = (
                f"🎁 <b>Seller reported that the gift was transferred to manager @{SUPPORT_USERNAME} for deal #{deal_id}!</b>\n\n"
                "After confirming receipt with the manager, click the confirmation button below:"
            )
        else:
            notif_text = (
                f"🎁 <b>Продавец сообщил, что передал подарок менеджеру @{SUPPORT_USERNAME} по сделке #{deal_id}!</b>\n\n"
                "После подтверждения получения товара менеджером нажмите кнопку подтверждения ниже:"
            )
        try:
            await callback.bot.send_message(
                chat_id=buyer_id,
                text=notif_text,
                reply_markup=get_buyer_deal_keyboard(deal_id, SUPPORT_USERNAME, is_creator=(creator_role == "buyer"), lang=buyer_lang),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить покупателя {buyer_id}: {e}")


@dp.callback_query(F.data == "buyer_waiting_notice")
async def buyer_waiting_notice_handler(callback: CallbackQuery):
    lang = await db.get_user_language(callback.from_user.id)
    msg = (
        "⏳ Seller is still transferring the gift to the manager. Please wait."
        if lang == "en"
        else "⏳ Продавец ещё передаёт подарок менеджеру. Ожидайте уведомления."
    )
    await callback.answer(msg, show_alert=True)


# ------------------ Действие покупателя: Подтвердить получение подарка менеджеру ------------------

@dp.callback_query(F.data.startswith("finish_deal_"))
async def finish_deal_handler(callback: CallbackQuery):
    deal_id = callback.data.replace("finish_deal_", "").strip()
    deal = await db.get_deal(deal_id)
    lang = await db.get_user_language(callback.from_user.id)

    if not deal:
        await callback.answer("Deal not found." if lang == "en" else "Сделка не найдена.", show_alert=True)
        return

    if deal["status"] == "completed":
        await callback.answer("Deal already completed." if lang == "en" else "Эта сделка уже завершена.", show_alert=True)
        return

    if deal["status"] == "cancelled":
        await callback.answer("Deal was cancelled." if lang == "en" else "Эта сделка была отменена.", show_alert=True)
        return

    creator_role = deal.get("creator_role", "seller")
    caller_id = callback.from_user.id

    # Покупатель и продавец
    if creator_role == "seller":
        seller_id = deal["creator_id"]
        buyer_id = deal["buyer_id"]
    else:
        seller_id = deal["buyer_id"]
        buyer_id = deal["creator_id"]

    if buyer_id and caller_id != buyer_id:
        err_msg = (
            "Only the buyer can confirm gift transfer."
            if lang == "en"
            else "Подтвердить передачу подарка менеджеру может только покупатель."
        )
        await callback.answer(err_msg, show_alert=True)
        return

    # Завершаем сделку
    await db.complete_deal(deal_id)

    seller_lang = await db.get_user_language(seller_id) if seller_id else "ru"
    buyer_lang = await db.get_user_language(buyer_id) if buyer_id else "ru"

    # 1. Продавцу
    if seller_id:
        comp_seller = (
            f"🎉 <b>Deal #{deal_id} successfully completed!</b>\n\nThank you for trusting us ❤️"
            if seller_lang == "en"
            else f"🎉 <b>Сделка #{deal_id} успешно завершена!</b>\n\nСпасибо за доверие ❤️"
        )
        try:
            await callback.bot.send_message(
                chat_id=seller_id,
                text=comp_seller,
                reply_markup=get_deal_completed_keyboard(deal_id, lang=seller_lang),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление продавцу {seller_id}: {e}")

    # 2. Покупателю
    comp_buyer = (
        f"🎉 <b>Deal #{deal_id} successfully completed!</b>\n\nThank you for trusting us ❤️"
        if buyer_lang == "en"
        else f"🎉 <b>Сделка #{deal_id} успешно завершена!</b>\n\nСпасибо за доверие ❤️"
    )
    try:
        await callback.message.edit_text(
            comp_buyer,
            reply_markup=get_deal_completed_keyboard(deal_id, lang=buyer_lang),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            comp_buyer,
            reply_markup=get_deal_completed_keyboard(deal_id, lang=buyer_lang),
            parse_mode="HTML"
        )

    await callback.answer()


# ------------------ Оставить отзыв о сделке ------------------

@dp.callback_query(F.data.startswith("leave_review_"))
async def leave_review_handler(callback: CallbackQuery, state: FSMContext):
    deal_id = callback.data.replace("leave_review_", "").strip()
    await state.update_data(review_deal_id=deal_id)
    lang = await db.get_user_language(callback.from_user.id)

    if lang == "en":
        text = (
            "✍️ <b>Leave a Review</b>\n\n"
            "Write your review about the escrow service and deal in response to this message:"
        )
    else:
        text = (
            "✍️ <b>Оставить отзыв о сделке</b>\n\n"
            "Напишите ваш отзыв о сервисе и сделке ответным сообщением в этот чат:"
        )
    cancel_kb = get_back_keyboard(lang)
    try:
        await callback.message.edit_text(text, reply_markup=cancel_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=cancel_kb, parse_mode="HTML")
    await state.set_state(ReviewStates.waiting_for_review)
    await callback.answer()


@dp.message(ReviewStates.waiting_for_review)
async def process_review_text(message: Message, state: FSMContext):
    data = await state.get_data()
    deal_id = data.get("review_deal_id", "unknown")
    user_id = message.from_user.id
    review_text = message.text.strip()
    lang = await db.get_user_language(user_id)
    await state.clear()

    await db.add_review(user_id, deal_id, review_text)

    if lang == "en":
        thanks_text = (
            "❤️ <b>Thank you for your review!</b>\n\n"
            f"Your feedback has been saved and will appear in our reviews channel @{REVIEWS_CHANNEL}."
        )
    else:
        thanks_text = (
            "❤️ <b>Спасибо за ваш отзыв!</b>\n\n"
            f"Ваш отзыв успешно сохранён и будет опубликован в канале отзывов @{REVIEWS_CHANNEL}."
        )
    await message.answer(thanks_text, reply_markup=get_back_keyboard(lang), parse_mode="HTML")


# ------------------ Отмена / Отказ от сделки («❌ Отказаться от сделки») ------------------

@dp.callback_query(F.data.startswith("cancel_deal_"))
async def cancel_deal_handler(callback: CallbackQuery):
    deal_id = callback.data.replace("cancel_deal_", "").strip()
    deal = await db.get_deal(deal_id)
    lang = await db.get_user_language(callback.from_user.id)

    if not deal:
        await callback.answer("Deal not found." if lang == "en" else "Сделка не найдена.", show_alert=True)
        return

    if deal["status"] == "completed":
        await callback.answer("Deal already completed." if lang == "en" else "Сделка уже успешно завершена.", show_alert=True)
        return

    user_id = callback.from_user.id
    success = await db.cancel_deal(deal_id, user_id)

    if success:
        text = (
            f"❌ You cancelled deal <b>#{deal_id}</b>."
            if lang == "en"
            else f"❌ Вы отказались от сделки <b>#{deal_id}</b>. Сделка отменена."
        )
        await callback.message.edit_text(text, reply_markup=get_back_keyboard(lang), parse_mode="HTML")

        # Уведомляем второго участника об отмене сделки
        other_id = deal["buyer_id"] if user_id == deal["creator_id"] else deal["creator_id"]
        if other_id:
            other_lang = await db.get_user_language(other_id)
            other_text = (
                f"🔔 Partner cancelled deal <b>#{deal_id}</b>."
                if other_lang == "en"
                else f"🔔 Партнёр отказался от сделки <b>#{deal_id}</b>. Сделка отменена."
            )
            try:
                await callback.bot.send_message(
                    chat_id=other_id,
                    text=other_text,
                    reply_markup=get_back_keyboard(other_lang),
                    parse_mode="HTML"
                )
            except Exception:
                pass
    else:
        await callback.answer("Deal already cancelled or completed." if lang == "en" else "Сделка уже отменена или завершена.", show_alert=True)
    await callback.answer()


# ------------------ Обработка инлайн-режима (Inline Query) ------------------

@dp.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    raw_query = inline_query.query.strip()
    clean_query = raw_query.lstrip("#").replace("deal_", "").strip()

    bot_info = await inline_query.bot.get_me()
    bot_username = bot_info.username
    results = []

    if clean_query:
        deal = await db.get_deal(clean_query)
        if deal and deal["status"] in ["created", "accepted"]:
            deal_id = deal["deal_id"]
            join_url = f"https://t.me/{bot_username}?start=deal_{deal_id}"
            creator_role = deal.get("creator_role", "seller")
            d_lang = deal.get("language", "ru")
            curr = get_curr_info(deal.get("currency", "RUB"))

            if d_lang == "en":
                role_label = "Seller" if creator_role == "seller" else "Buyer"
                invite_text = (
                    f"🤝 <b>Invitation to deal #{deal_id}</b>\n\n"
                    f"🛒 <b>Creator role:</b> {role_label}\n"
                    f"{curr['flag']} <b>Amount:</b> {deal['amount']:.2f} {deal['currency']}\n"
                    f"📊 <b>Service fee:</b> 3%\n"
                    f"📦 <b>Item / NFT:</b> {deal['item_link']}\n\n"
                    f"<i>Click the button below to open the deal:</i>"
                )
                btn_text = "👉 Open Deal"
                card_title = f"🤝 Deal #{deal_id} — {deal['amount']:.2f} {deal['currency']}"
                card_desc = f"Item: {deal['item_link'][:40]} | Click to send"
            else:
                role_label = "Продавец" if creator_role == "seller" else "Покупатель"
                invite_text = (
                    f"🤝 <b>Приглашение в сделку #{deal_id}</b>\n\n"
                    f"🛒 <b>Роль создателя:</b> {role_label}\n"
                    f"{curr['flag']} <b>Сумма:</b> {deal['amount']:.2f} {deal['currency']}\n"
                    f"📊 <b>Комиссия сервиса:</b> 3%\n"
                    f"📦 <b>Товар / NFT:</b> {deal['item_link']}\n\n"
                    f"<i>Нажмите кнопку ниже, чтобы перейти к сделке:</i>"
                )
                btn_text = "👉 Открыть сделку"
                card_title = f"🤝 Сделка #{deal_id} — {deal['amount']:.2f} {deal['currency']}"
                card_desc = f"Товар: {deal['item_link'][:40]} | Нажмите для отправки"

            invite_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=join_url)]]
            )

            card = InlineQueryResultArticle(
                id=deal_id,
                title=card_title,
                description=card_desc,
                input_message_content=InputTextMessageContent(
                    message_text=invite_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                ),
                reply_markup=invite_keyboard,
            )
            results.append(card)

    if not results:
        user_deals = await db.get_user_active_created_deals(inline_query.from_user.id)
        for d in user_deals:
            deal_id = d["deal_id"]
            join_url = f"https://t.me/{bot_username}?start=deal_{deal_id}"
            creator_role = d.get("creator_role", "seller")
            d_lang = d.get("language", "ru")
            curr = get_curr_info(d.get("currency", "RUB"))

            if d_lang == "en":
                role_label = "Seller" if creator_role == "seller" else "Buyer"
                invite_text = (
                    f"🤝 <b>Invitation to deal #{deal_id}</b>\n\n"
                    f"🛒 <b>Creator role:</b> {role_label}\n"
                    f"{curr['flag']} <b>Amount:</b> {d['amount']:.2f} {d['currency']}\n"
                    f"📊 <b>Service fee:</b> 3%\n"
                    f"📦 <b>Item / NFT:</b> {d['item_link']}\n\n"
                    f"<i>Click the button below to open the deal:</i>"
                )
                btn_text = "👉 Open Deal"
                card_title = f"🤝 Your deal #{deal_id} ({d['amount']:.2f} {d['currency']})"
                card_desc = "Send invitation to deal partner"
            else:
                role_label = "Продавец" if creator_role == "seller" else "Покупатель"
                invite_text = (
                    f"🤝 <b>Приглашение в сделку #{deal_id}</b>\n\n"
                    f"🛒 <b>Роль создателя:</b> {role_label}\n"
                    f"{curr['flag']} <b>Сумма:</b> {d['amount']:.2f} {d['currency']}\n"
                    f"📊 <b>Комиссия сервиса:</b> 3%\n"
                    f"📦 <b>Товар / NFT:</b> {d['item_link']}\n\n"
                    f"<i>Нажмите кнопку ниже, чтобы перейти к сделке:</i>"
                )
                btn_text = "👉 Открыть сделку"
                card_title = f"🤝 Ваша сделка #{deal_id} ({d['amount']:.2f} {d['currency']})"
                card_desc = "Отправить приглашение партнеру по сделке"

            invite_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=join_url)]]
            )

            card = InlineQueryResultArticle(
                id=f"active_{deal_id}",
                title=card_title,
                description=card_desc,
                input_message_content=InputTextMessageContent(
                    message_text=invite_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                ),
                reply_markup=invite_keyboard,
            )
            results.append(card)

    if not results:
        hint_card = InlineQueryResultArticle(
            id="hint_no_deals",
            title="ℹ️ Нет активных сделок для отправки",
            description="Создайте сделку в боте или введите #ID_сделки",
            input_message_content=InputTextMessageContent(
                message_text=(
                    f"💼 <b>Гарант-бот Lotus Dels</b>\n\n"
                    f"Для создания сделки перейдите в бота: @{bot_username}"
                ),
                parse_mode="HTML",
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🤖 Открыть бота", url=f"https://t.me/{bot_username}")]]
            ),
        )
        results.append(hint_card)

    await inline_query.answer(results=results, cache_time=1, is_personal=True)


# ------------------ Раздел «Баланс» ------------------

@dp.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    user = await db.get_or_create_user(user_id, callback.from_user.username, callback.from_user.full_name)

    rub = user.get("balance_rub", 0.0)
    uah = user.get("balance_uah", 0.0)
    byn = user.get("balance_byn", 0.0)
    kzt = user.get("balance_kzt", 0.0)
    gram = user.get("balance_gram", 0.0)
    usdt = user.get("balance_usdt", 0.0)
    stars = user.get("balance_stars", 0.0)
    completed = user.get("completed_deals", 0)

    if lang == "en":
        text = (
            "💰 <b>Balance:</b>\n\n"
            f"💳 RUB — {rub:.1f}\n"
            f"🇺🇦 UAH — {uah:.1f}\n"
            f"🇧🇾 BYN — {byn:.1f}\n"
            f"🇰🇿 KZT — {kzt:.1f}\n"
            f"💎 GRAM — {gram:.1f}\n"
            f"💵 USDT — {usdt:.1f}\n"
            f"⭐ Stars — {stars:.1f}\n\n"
            "❗️ <i>To withdraw funds, at least 2 completed deals are required</i>\n\n"
            f"📈 Completed deals: {completed}"
        )
    else:
        text = (
            "💰 <b>Баланс:</b>\n\n"
            f"💳 RUB — {rub:.1f}\n"
            f"🇺🇦 UAH — {uah:.1f}\n"
            f"🇧🇾 BYN — {byn:.1f}\n"
            f"🇰🇿 KZT — {kzt:.1f}\n"
            f"💎 GRAM — {gram:.1f}\n"
            f"💵 USDT — {usdt:.1f}\n"
            f"⭐ Stars — {stars:.1f}\n\n"
            "❗️ <i>Для вывода средств необходимо минимум 2 завершённые сделки</i>\n\n"
            f"📈 Завершённых сделок: {completed}"
        )

    try:
        await callback.message.edit_text(text, reply_markup=get_balance_keyboard(lang), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_balance_keyboard(lang), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "withdraw_funds")
async def withdraw_funds_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    user = await db.get_or_create_user(user_id)
    if user.get("completed_deals", 0) < 2:
        msg = (
            "❗️ To withdraw funds, at least 2 completed deals are required."
            if lang == "en"
            else "❗️ Для вывода средств необходимо минимум 2 завершённые сделки."
        )
        await callback.answer(msg, show_alert=True)
    else:
        msg = "Withdrawal request submitted to administrator." if lang == "en" else "Заявка на вывод отправлена администратору."
        await callback.answer(msg, show_alert=True)


@dp.callback_query(F.data == "transactions")
async def transactions_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    text = (
        "📜 <b>Transaction history:</b>\n\nNo transactions yet."
        if lang == "en"
        else "📜 <b>История транзакций:</b>\n\nУ вас пока нет транзакций."
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_back_keyboard(lang), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_back_keyboard(lang), parse_mode="HTML")
    await callback.answer()


# ------------------ Раздел «Мои сделки» ------------------

@dp.callback_query(F.data == "my_deals")
async def show_my_deals(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    deals = await db.get_user_deals(user_id)

    if not deals:
        text = "📋 You have no deals." if lang == "en" else "📋 У вас нет сделок."
        keyboard = get_back_keyboard(lang)
    else:
        text = "📋 <b>Your deals:</b>\n\n" if lang == "en" else "📋 <b>Ваши сделки:</b>\n\n"
        buttons = []
        for d in deals[:10]:
            creator_role = d.get("creator_role", "seller")
            if d["creator_id"] == user_id:
                if lang == "en":
                    role = "Seller" if creator_role == "seller" else "Buyer"
                else:
                    role = "Продавец" if creator_role == "seller" else "Покупатель"
            else:
                if lang == "en":
                    role = "Buyer" if creator_role == "seller" else "Seller"
                else:
                    role = "Покупатель" if creator_role == "seller" else "Продавец"

            if lang == "en":
                status_map = {
                    "created": "🟡 Pending",
                    "accepted": "🟢 In progress",
                    "completed": "✅ Completed",
                    "cancelled": "❌ Cancelled",
                }
            else:
                status_map = {
                    "created": "🟡 В ожидании",
                    "accepted": "🟢 В процессе",
                    "completed": "✅ Завершена",
                    "cancelled": "❌ Отменена",
                }
            st_text = status_map.get(d["status"], d["status"])
            curr = get_curr_info(d.get("currency", "RUB"))
            amt_lbl = "Amount" if lang == "en" else "Сумма"
            st_lbl = "Status" if lang == "en" else "Статус"
            text += (
                f"• <b>#{d['deal_id']}</b> ({role})\n"
                f"  {amt_lbl}: {d['amount']:.2f} {curr['code']}\n"
                f"  {st_lbl}: {st_text}\n\n"
            )
            # Если сделка активна:
            if d["status"] in ["created", "accepted"]:
                is_seller = (creator_role == "seller" and d["creator_id"] == user_id) or (creator_role == "buyer" and d["buyer_id"] == user_id)
                if is_seller:
                    tr_text = f"📦 Transfer #{d['deal_id']} ↗" if lang == "en" else f"📦 Передать #{d['deal_id']} ↗"
                    dn_text = f"✅ Done #{d['deal_id']}" if lang == "en" else f"✅ Готово #{d['deal_id']}"
                    buttons.append([InlineKeyboardButton(text=tr_text, url=f"https://t.me/{SUPPORT_USERNAME}")])
                    buttons.append([InlineKeyboardButton(text=dn_text, callback_data=f"seller_gift_done_{d['deal_id']}")])
                else:
                    cf_text = f"✅ Confirm #{d['deal_id']}" if lang == "en" else f"✅ Подтвердить #{d['deal_id']}"
                    buttons.append([InlineKeyboardButton(text=cf_text, callback_data=f"finish_deal_{d['deal_id']}")])
                cn_text = f"❌ Cancel #{d['deal_id']}" if lang == "en" else f"❌ Отказаться #{d['deal_id']}"
                buttons.append([InlineKeyboardButton(text=cn_text, callback_data=f"cancel_deal_{d['deal_id']}")])

        back_text = "◀️ Back to menu" if lang == "en" else "◀️ Назад в меню"
        buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_menu")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ------------------ Раздел «Мои реквизиты» ------------------

REQ_CONFIG_RU = {
    "req_rub": ("Карта (RUB)", "номер карты (например: 2200 1234 5678 9012)"),
    "req_uah": ("Карта (UAH)", "номер карты (например: 4149 1234 5678 9012)"),
    "req_byn": ("Карта (BYN)", "номер карты (например: 4000 1234 5678 9012)"),
    "req_kzt": ("Карта (KZT)", "номер карты (например: 4400 1234 5678 9012)"),
    "req_gram": ("Кошелёк (GRAM)", "адрес кошелька TON / GRAM"),
    "req_usdt": ("Кошелёк (USDT)", "адрес кошелька USDT (TRC-20 / TON)"),
    "req_stars": ("Юзернейм (Stars)", "ваш юзернейм в Telegram (например: @username)"),
}

REQ_CONFIG_EN = {
    "req_rub": ("Card (RUB)", "card number (e.g.: 2200 1234 5678 9012)"),
    "req_uah": ("Card (UAH)", "card number (e.g.: 4149 1234 5678 9012)"),
    "req_byn": ("Card (BYN)", "card number (e.g.: 4000 1234 5678 9012)"),
    "req_kzt": ("Card (KZT)", "card number (e.g.: 4400 1234 5678 9012)"),
    "req_gram": ("Wallet (GRAM)", "TON / GRAM wallet address"),
    "req_usdt": ("Wallet (USDT)", "USDT (TRC-20 / TON) wallet address"),
    "req_stars": ("Username (Stars)", "your Telegram username (e.g.: @username)"),
}


@dp.callback_query(F.data == "requisites")
async def show_requisites(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    user = await db.get_or_create_user(user_id, callback.from_user.username, callback.from_user.full_name)

    not_linked = "Not linked" if lang == "en" else "Не привязана"
    not_linked_m = "Not linked" if lang == "en" else "Не привязан"

    req_rub = user.get("req_rub") or not_linked
    req_uah = user.get("req_uah") or not_linked
    req_byn = user.get("req_byn") or not_linked
    req_kzt = user.get("req_kzt") or not_linked
    req_gram = user.get("req_gram") or not_linked_m
    req_usdt = user.get("req_usdt") or not_linked_m
    req_stars = user.get("req_stars") or not_linked_m

    if lang == "en":
        text = (
            "🪪 <b>Your payout requisites:</b>\n\n"
            f"💳 <b>Cards (RUB):</b> <code>{req_rub}</code>\n"
            f"🇺🇦 <b>Cards (UAH):</b> <code>{req_uah}</code>\n"
            f"🇧🇾 <b>Cards (BYN):</b> <code>{req_byn}</code>\n"
            f"🇰🇿 <b>Cards (KZT):</b> <code>{req_kzt}</code>\n"
            f"💎 <b>Wallet (GRAM):</b> <code>{req_gram}</code>\n"
            f"💵 <b>Wallet (USDT):</b> <code>{req_usdt}</code>\n"
            f"⭐ <b>Username (Stars):</b> <code>{req_stars}</code>\n\n"
            "💡 <i>Click a button below to bind or change your requisites:</i>"
        )
    else:
        text = (
            "🪪 <b>Ваши реквизиты для вывода:</b>\n\n"
            f"💳 <b>Карты (RUB):</b> <code>{req_rub}</code>\n"
            f"🇺🇦 <b>Карты (UAH):</b> <code>{req_uah}</code>\n"
            f"🇧🇾 <b>Карты (BYN):</b> <code>{req_byn}</code>\n"
            f"🇰🇿 <b>Карты (KZT):</b> <code>{req_kzt}</code>\n"
            f"💎 <b>Кошелёк (GRAM):</b> <code>{req_gram}</code>\n"
            f"💵 <b>Кошелёк (USDT):</b> <code>{req_usdt}</code>\n"
            f"⭐ <b>Юзернейм (Stars):</b> <code>{req_stars}</code>\n\n"
            "💡 <i>Нажмите на кнопку ниже, чтобы привязать или изменить реквизиты:</i>"
        )

    try:
        await callback.message.edit_text(text, reply_markup=get_requisites_keyboard(lang), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_requisites_keyboard(lang), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("set_req_"))
async def prompt_set_requisite(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    req_key = callback.data.replace("set_", "").strip()
    cfg = REQ_CONFIG_EN if lang == "en" else REQ_CONFIG_RU
    name, example = cfg.get(req_key, ("Requisites" if lang == "en" else "Реквизиты", "value" if lang == "en" else "значение"))
    await state.update_data(current_req_key=req_key)

    if lang == "en":
        text = (
            f"🪪 <b>Linking requisites: {name}</b>\n\n"
            f"Send {example} in reply to this message:"
        )
        cancel_text = "◀️ Cancel"
    else:
        text = (
            f"🪪 <b>Привязка реквизитов: {name}</b>\n\n"
            f"Отправьте {example} ответным сообщением:"
        )
        cancel_text = "◀️ Отмена"

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=cancel_text, callback_data="requisites")]]
    )
    try:
        await callback.message.edit_text(text, reply_markup=cancel_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=cancel_kb, parse_mode="HTML")
    await state.set_state(RequisiteStates.waiting_for_requisite_value)
    await callback.answer()


@dp.message(RequisiteStates.waiting_for_requisite_value)
async def process_requisite_value(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    data = await state.get_data()
    req_key = data.get("current_req_key", "req_rub")
    value = message.text.strip()
    await state.clear()

    await db.update_user_requisite(user_id, req_key, value)

    cfg = REQ_CONFIG_EN if lang == "en" else REQ_CONFIG_RU
    name, _ = cfg.get(req_key, ("Requisites" if lang == "en" else "Реквизиты", ""))

    if lang == "en":
        thanks_text = (
            f"✅ <b>{name} saved successfully:</b>\n"
            f"<code>{value}</code>"
        )
        back_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🪪 To requisites", callback_data="requisites")],
                [InlineKeyboardButton(text="◀️ Main menu", callback_data="back_to_menu")],
            ]
        )
    else:
        thanks_text = (
            f"✅ <b>{name} успешно сохранены:</b>\n"
            f"<code>{value}</code>"
        )
        back_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🪪 К реквизитам", callback_data="requisites")],
                [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_menu")],
            ]
        )
    await message.answer(thanks_text, reply_markup=back_kb, parse_mode="HTML")


# ------------------ Раздел «Рефералы» ------------------

@dp.callback_query(F.data == "referrals")
async def show_referrals(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    bot_info = await callback.bot.get_me()
    ref_count = await db.get_referral_stats(user_id)
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    if lang == "en":
        text = (
            "👥 <b>Referral Program:</b>\n\n"
            "Invite users and earn 50% of the service fee from each of their completed deals!\n\n"
            f"🔗 <b>Your referral link:</b>\n{ref_link}\n\n"
            f"👥 Invited: {ref_count} users\n"
            "💰 Earned: 0.0 RUB"
        )
    else:
        text = (
            "👥 <b>Реферальная программа:</b>\n\n"
            "Приглашайте пользователей и получайте 50% от комиссии сервиса с каждой их сделки!\n\n"
            f"🔗 <b>Ваша реферальная ссылка:</b>\n{ref_link}\n\n"
            f"👥 Приглашено: {ref_count} чел.\n"
            "💰 Заработано: 0.0 RUB"
        )
    try:
        await callback.message.edit_text(text, reply_markup=get_back_keyboard(lang), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_back_keyboard(lang), parse_mode="HTML")
    await callback.answer()


# ------------------ Раздел «Отзывы» ------------------

@dp.callback_query(F.data == "reviews")
async def show_reviews(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    reviews_url = f"https://t.me/{REVIEWS_CHANNEL}"

    if lang == "en":
        text = (
            "💬 <b>Reviews:</b>\n\n"
            f"You can read all verified reviews in our official channel:\n"
            f"👉 <b>t.me/{REVIEWS_CHANNEL}</b>\n\n"
            f"To submit a review, contact our manager @{SUPPORT_USERNAME} or leave feedback after completing a deal."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📢 Reviews Channel ↗", url=reviews_url)],
                [InlineKeyboardButton(text="◀️ Back to menu", callback_data="back_to_menu")],
            ]
        )
    else:
        text = (
            "💬 <b>Отзывы о сервисе:</b>\n\n"
            f"Ознакомиться со всеми отзывами вы можете в нашем официальном канале:\n"
            f"👉 <b>t.me/{REVIEWS_CHANNEL}</b>\n\n"
            f"Также оставить отзыв можно через менеджера @{SUPPORT_USERNAME} или после завершения сделки."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📢 Канал с отзывами ↗", url=reviews_url)],
                [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")],
            ]
        )
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ------------------ Раздел «Язык / Lang» ------------------

@dp.callback_query(F.data == "lang")
async def show_lang(callback: CallbackQuery):
    user_id = callback.from_user.id
    curr_lang = await db.get_user_language(user_id)
    text = (
        "🌐 <b>Выберите язык интерфейса / Select interface language:</b>\n\n"
        f"Текущий язык / Current language: <b>{'🇷🇺 Русский' if curr_lang == 'ru' else '🇬🇧 English'}</b>"
    )
    ru_label = "🇷🇺 Русский ✅" if curr_lang == "ru" else "🇷🇺 Русский"
    en_label = "🇬🇧 English ✅" if curr_lang == "en" else "🇬🇧 English"
    back_label = "◀️ Back to menu" if curr_lang == "en" else "◀️ Назад в меню"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ru_label, callback_data="lang_ru")],
            [InlineKeyboardButton(text=en_label, callback_data="lang_en")],
            [InlineKeyboardButton(text=back_label, callback_data="back_to_menu")],
        ]
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.in_(["lang_ru", "lang_en"]))
async def select_lang(callback: CallbackQuery):
    user_id = callback.from_user.id
    new_lang = "ru" if callback.data == "lang_ru" else "en"
    await db.set_user_language(user_id, new_lang)

    if new_lang == "en":
        alert_msg = "Language changed to English! 🇬🇧"
    else:
        alert_msg = "Язык переключен на Русский! 🇷🇺"

    await callback.answer(alert_msg, show_alert=True)

    try:
        await callback.message.edit_text(
            get_welcome_text(SUPPORT_USERNAME, lang=new_lang),
            reply_markup=get_main_menu_keyboard(SUPPORT_USERNAME, lang=new_lang),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            get_welcome_text(SUPPORT_USERNAME, lang=new_lang),
            reply_markup=get_main_menu_keyboard(SUPPORT_USERNAME, lang=new_lang),
            parse_mode="HTML",
        )


# ------------------ Возврат в главное меню ------------------

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await db.get_user_language(callback.from_user.id)
    try:
        await callback.message.edit_text(
            get_welcome_text(SUPPORT_USERNAME, lang=lang),
            reply_markup=get_main_menu_keyboard(SUPPORT_USERNAME, lang=lang),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            get_welcome_text(SUPPORT_USERNAME, lang=lang),
            reply_markup=get_main_menu_keyboard(SUPPORT_USERNAME, lang=lang),
            parse_mode="HTML",
        )
    await callback.answer()


# ------------------ Запуск бота ------------------

async def main():
    if not BOT_TOKEN:
        logger.error("ОШИБКА: BOT_TOKEN не указан в файле .env!")
        return

    # Инициализация базы данных SQLite
    await db.init_db()

    bot = Bot(token=BOT_TOKEN)
    bot_info = await bot.get_me()
    logger.info(f"Бот @{bot_info.username} (ID: {bot_info.id}) успешно авторизован.")

    # Проверка поддержки инлайн-режима
    if not bot_info.supports_inline_queries:
        logger.warning(
            "\n" + "=" * 70 + "\n"
            "ВНИМАНИЕ! У бота ВЫКЛЮЧЕН инлайн-режим (supports_inline_queries = False)!\n"
            "Из-за этого в Telegram при нажатии кнопки 'Поделиться в чате' ничего не появляется!\n"
            "Чтобы включить:\n"
            "1. Перейдите в Telegram в бота @BotFather\n"
            "2. Отправьте команду /setinline\n"
            f"3. Выберите вашего бота (@{bot_info.username})\n"
            "4. Введите текст плейсхолдера (например: Введите #ID_сделки...)\n"
            + "=" * 70 + "\n"
        )

    logger.info("Запуск polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
