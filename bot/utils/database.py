# bot/utils/database.py
import aiosqlite
import logging

DATABASE = "words.db"


class Database:
    _instance = None

    def __init__(self):
        if Database._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            Database._instance = self
            self.db = None
            logging.info("Database instance created")

    @staticmethod
    async def get_instance():
        if Database._instance is None:
            Database()
            Database._instance.db = await aiosqlite.connect(DATABASE)
            await Database._instance.setup()
            logging.info("Database connection established")
        return Database._instance

    async def setup(self):
        try:
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
            await self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS word_stats (
                    word_id INTEGER PRIMARY KEY,
                    attempts INTEGER DEFAULT 0,
                    correct INTEGER DEFAULT 0,
                    last_seen TEXT,
                    ease REAL DEFAULT 2.5
                )
                """
            )
            await self.db.commit()
            logging.info("Database tables setup completed")
        except Exception as e:
            logging.error(f"Error setting up database: {e}")
            raise

    async def execute(self, query, params=()):
        try:
            async with self.db.execute(query, params) as cursor:
                await self.db.commit()
                logging.debug(f"Executed query: {query} with params: {params}")
                return cursor
        except Exception as e:
            logging.error(f"Error executing query: {query} with params: {params}. Error: {e}")
            raise

    async def fetchall(self, query, params=()):
        async with self.db.execute(query, params) as cursor:
            return await cursor.fetchall()

    async def fetchone(self, query, params=()):
        async with self.db.execute(query, params) as cursor:
            return await cursor.fetchone()
