"""
SQLite-Datenbank für die Watchlist.
Asynchroner Zugriff via aiosqlite.
"""

import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from backend.config import get_settings

logger = logging.getLogger(__name__)

# SQL-Schema
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _db_path() -> str:
    """Gibt den Datenbankpfad zurück und stellt sicher, dass das Verzeichnis existiert."""
    path = get_settings().DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


async def init_db() -> None:
    """Datenbank initialisieren und Tabelle erstellen falls nötig."""
    db_path = _db_path()
    logger.info("Initialisiere Datenbank: %s", db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_CREATE_TABLE)
        await db.commit()
    logger.info("Datenbank bereit.")


async def get_watchlist() -> list[dict]:
    """Alle Einträge der Watchlist zurückgeben."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, ticker, name, added_at FROM watchlist ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "ticker": row["ticker"],
                "name": row["name"],
                "added_at": row["added_at"],
            }
            for row in rows
        ]


async def add_stock(ticker: str, name: str) -> dict:
    """
    Aktie zur Watchlist hinzufügen.
    Gibt den Status zurück (created / already_exists).
    """
    ticker = ticker.upper().strip()
    name = name.strip()

    async with aiosqlite.connect(_db_path()) as db:
        try:
            await db.execute(
                "INSERT INTO watchlist (ticker, name) VALUES (?, ?)",
                (ticker, name),
            )
            await db.commit()
            logger.info("Aktie hinzugefügt: %s (%s)", ticker, name)
            return {"status": "created", "ticker": ticker, "name": name}
        except aiosqlite.IntegrityError:
            logger.info("Aktie bereits vorhanden: %s", ticker)
            return {"status": "already_exists", "ticker": ticker, "name": name}


async def remove_stock(ticker: str) -> dict:
    """Aktie aus der Watchlist entfernen."""
    ticker = ticker.upper().strip()

    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            "DELETE FROM watchlist WHERE ticker = ?", (ticker,)
        )
        await db.commit()

        if cursor.rowcount > 0:
            logger.info("Aktie entfernt: %s", ticker)
            return {"status": "removed", "ticker": ticker}
        else:
            logger.info("Aktie nicht gefunden: %s", ticker)
            return {"status": "not_found", "ticker": ticker}
