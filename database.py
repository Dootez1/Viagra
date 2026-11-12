import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "deals.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance_rub REAL DEFAULT 0.0,
                balance_crypto REAL DEFAULT 0.0,
                balance_stars REAL DEFAULT 0.0,
                completed_deals INTEGER DEFAULT 0,
                referrer_id INTEGER DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                deal_id TEXT PRIMARY KEY,
                creator_id INTEGER NOT NULL,
                creator_name TEXT NOT NULL,
                creator_role TEXT DEFAULT 'seller',
                buyer_id INTEGER DEFAULT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'RUB',
                fee REAL DEFAULT 0.0,
                item_link TEXT NOT NULL,
                status TEXT DEFAULT 'created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Миграции для существующих колонок
        try:
            await db.execute("ALTER TABLE deals ADD COLUMN creator_role TEXT DEFAULT 'seller'")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE deals ADD COLUMN fee REAL DEFAULT 0.0")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE deals ADD COLUMN gift_sent INTEGER DEFAULT 0")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE deals ADD COLUMN language TEXT DEFAULT 'ru'")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE deals ADD COLUMN is_paid INTEGER DEFAULT 0")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE deals ADD COLUMN image_url TEXT DEFAULT NULL")
        except Exception:
            pass

        for col in ["balance_uah", "balance_byn", "balance_kzt", "balance_gram", "balance_usdt"]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} REAL DEFAULT 0.0")
            except Exception:
                pass

        for col in ["req_rub", "req_uah", "req_byn", "req_kzt", "req_gram", "req_usdt", "req_stars"]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT NULL")
            except Exception:
                pass

        try:
            await db.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ru'")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                deal_id TEXT,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()


async def get_or_create_user(user_id: int, username: str = None, full_name: str = None, referrer_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                await db.execute(
                    "INSERT INTO users (user_id, username, full_name, referrer_id) VALUES (?, ?, ?, ?)",
                    (user_id, username, full_name, referrer_id if referrer_id and referrer_id != user_id else None)
                )
                await db.commit()
                async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as c2:
                    return dict(await c2.fetchone())
            else:
                # Обновим имя и юзернейм если изменились
                if (username and user["username"] != username) or (full_name and user["full_name"] != full_name):
                    await db.execute(
                        "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
                        (username or user["username"], full_name or user["full_name"], user_id)
                    )
                    await db.commit()
            return dict(user)


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_deal(
    deal_id: str,
    creator_id: int,
    creator_name: str,
    amount: float,
    item_link: str,
    creator_role: str = "seller",
    currency: str = "RUB",
    fee: float = 0.0,
    language: str = "ru",
    image_url: str = None
) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO deals (deal_id, creator_id, creator_name, creator_role, amount, currency, fee, item_link, status, language, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'created', ?, ?)
            """,
            (deal_id, creator_id, creator_name, creator_role, amount, currency, fee, item_link, language, image_url)
        )
        await db.commit()
        async with db.execute("SELECT * FROM deals WHERE deal_id = ?", (deal_id,)) as cursor:
            return dict(await cursor.fetchone())


async def get_deal(deal_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM deals WHERE deal_id = ?", (deal_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_user_deals(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM deals WHERE creator_id = ? OR buyer_id = ? ORDER BY created_at DESC",
            (user_id, user_id)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_user_active_created_deals(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM deals WHERE creator_id = ? AND status = 'created' ORDER BY created_at DESC LIMIT 5",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def cancel_deal(deal_id: str, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "UPDATE deals SET status = 'cancelled' WHERE deal_id = ? AND (creator_id = ? OR buyer_id = ?) AND status IN ('created', 'accepted')",
            (deal_id, user_id, user_id)
        ) as cursor:
            await db.commit()
            return cursor.rowcount > 0


async def accept_deal(deal_id: str, counterpart_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deals SET buyer_id = ?, status = 'accepted' WHERE deal_id = ?",
            (counterpart_id, deal_id)
        )
        await db.commit()


async def update_deal_buyer(deal_id: str, buyer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deals SET buyer_id = ? WHERE deal_id = ?",
            (buyer_id, deal_id)
        )
        await db.commit()


async def complete_deal(deal_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM deals WHERE deal_id = ?", (deal_id,)) as cursor:
            deal = await cursor.fetchone()
            if deal:
                await db.execute(
                    "UPDATE deals SET status = 'completed', is_paid = 1, gift_sent = 1 WHERE deal_id = ?",
                    (deal_id,)
                )
                # Увеличиваем счетчик завершенных сделок для обеих сторон
                creator_id = deal["creator_id"]
                buyer_id = deal["buyer_id"]
                await db.execute("UPDATE users SET completed_deals = completed_deals + 1 WHERE user_id = ?", (creator_id,))
                if buyer_id and buyer_id != creator_id:
                    await db.execute("UPDATE users SET completed_deals = completed_deals + 1 WHERE user_id = ?", (buyer_id,))
                await db.commit()


async def get_referral_stats(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)) as cursor:
            count = (await cursor.fetchone())[0]
            return count


async def mark_gift_sent(deal_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE deals SET gift_sent = 1 WHERE deal_id = ?", (deal_id,))
        await db.commit()


async def add_review(user_id: int, deal_id: str, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO reviews (user_id, deal_id, text) VALUES (?, ?, ?)",
            (user_id, deal_id, text)
        )
        await db.commit()


async def update_user_requisite(user_id: int, req_type: str, value: str):
    allowed = ["req_rub", "req_uah", "req_byn", "req_kzt", "req_gram", "req_usdt", "req_stars"]
    if req_type not in allowed:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {req_type} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()


async def set_user_language(user_id: int, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()


async def get_user_language(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row["language"]:
                return row["language"]
            return "ru"


async def mark_deal_paid(deal_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE deals SET is_paid = 1 WHERE deal_id = ?", (deal_id,))
        await db.commit()


def get_balance_column(curr_key: str) -> str:
    curr = str(curr_key).lower().strip()
    mapping = {
        "rub": "balance_rub",
        "uah": "balance_uah",
        "byn": "balance_byn",
        "kzt": "balance_kzt",
        "gram": "balance_gram",
        "usdt": "balance_usdt",
        "stars": "balance_stars",
        "crypto": "balance_crypto",
    }
    return mapping.get(curr, "balance_rub")


async def set_user_balance(user_id: int, curr_key: str, amount: float):
    col = get_balance_column(curr_key)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {col} = ? WHERE user_id = ?", (round(amount, 2), user_id))
        await db.commit()


async def change_user_balance(user_id: int, curr_key: str, delta: float) -> float:
    col = get_balance_column(curr_key)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"SELECT {col} FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            current = row[col] if row and row[col] is not None else 0.0
        new_val = max(0.0, round(current + delta, 2))
        await db.execute(f"UPDATE users SET {col} = ? WHERE user_id = ?", (new_val, user_id))
        await db.commit()
        return new_val


async def set_user_deals_count(user_id: int, count: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET completed_deals = ? WHERE user_id = ?", (max(0, int(count)), user_id))
        await db.commit()


async def add_user_deals_count(user_id: int, count: int, currency: str = "RUB") -> int:
    import string, random
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT completed_deals, username, full_name FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            curr_deals = user["completed_deals"] if user and user["completed_deals"] is not None else 0
            u_name = user["full_name"] if user and user["full_name"] else (user["username"] if user and user["username"] else "Участник")
        
        new_cnt = max(0, curr_deals + int(count))
        await db.execute("UPDATE users SET completed_deals = ? WHERE user_id = ?", (new_cnt, user_id))
        
        # Insert completed deals so user's 'My deals' list is populated
        chars = string.ascii_lowercase + string.digits
        for _ in range(min(count, 15)):
            d_id = "".join(random.choices(chars, k=10))
            amt = random.choice([1500.0, 2500.0, 3200.0, 4800.0, 5000.0])
            await db.execute(
                """
                INSERT OR IGNORE INTO deals (deal_id, creator_id, creator_name, creator_role, amount, currency, fee, item_link, status, is_paid, gift_sent)
                VALUES (?, ?, ?, 'seller', ?, ?, ?, 'Telegram NFT Gift', 'completed', 1, 1)
                """,
                (d_id, user_id, u_name, amt, currency, round(amt * 0.03, 2))
            )
        await db.commit()
        return new_cnt


async def find_user_by_identifier(identifier: str):
    clean = str(identifier).strip().lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if clean.isdigit():
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (int(clean),)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        async with db.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (clean,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
    return None
