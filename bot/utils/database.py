# bot/utils/database.py
import aiosqlite

DATABASE = "words.db"


class Database:
    _instance = None

    def __init__(self):
        if Database._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            Database._instance = self
            self.db = None

    @staticmethod
    async def get_instance():
        if Database._instance is None:
            Database()
            Database._instance.db = await aiosqlite.connect(DATABASE)
            await Database._instance.setup()
        return Database._instance

    async def setup(self):
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                word TEXT,
                meaning TEXT,
                added_at TEXT,
                intervals_remaining TEXT
            )
            """
        )
        await self.db.commit()

    async def execute(self, query, params=()):
        async with self.db.execute(query, params) as cursor:
            await self.db.commit()
            return cursor

    async def fetchall(self, query, params=()):
        async with self.db.execute(query, params) as cursor:
            return await cursor.fetchall()

    async def fetchone(self, query, params=()):
        async with self.db.execute(query, params) as cursor:
            return await cursor.fetchone()
