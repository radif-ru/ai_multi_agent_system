"""Долгосрочная семантическая память на `sqlite-vec`.

См. `_docs/memory.md` §3, §5.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryUnavailable(RuntimeError):
    """`sqlite-vec` extension не загрузилась — долгосрочная память недоступна."""


def _serialize_vector(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SemanticMemory:
    """Слой над `sqlite3` + `sqlite_vec`.

    API синхронный по сути; внешние корутины оборачивают вызовы
    в `asyncio.to_thread`.
    """

    def __init__(self, *, db_path: Path, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be > 0")
        self._db_path = db_path
        self._dim = dimensions
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle --------------------------------------------------------

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        try:
            conn.enable_load_extension(True)
        except sqlite3.NotSupportedError as exc:
            conn.close()
            raise MemoryUnavailable(
                "sqlite build does not support extension loading"
            ) from exc
        try:
            import sqlite_vec  # type: ignore[import-not-found]

            sqlite_vec.load(conn)
        except Exception as exc:  # noqa: BLE001
            conn.close()
            raise MemoryUnavailable(f"sqlite-vec extension not available: {exc}") from exc
        conn.enable_load_extension(False)

        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS memory_chunks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                chat_id         INTEGER NOT NULL,
                conversation_id TEXT    NOT NULL,
                chunk_index     INTEGER NOT NULL,
                created_at      TEXT    NOT NULL,
                text            TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_memory_user ON memory_chunks(user_id);
            CREATE INDEX IF NOT EXISTS ix_memory_conv ON memory_chunks(conversation_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING vec0 (
                embedding float[{self._dim}]
            );
            """
        )
        conn.commit()
        self._conn = conn

    async def close(self) -> None:
        if self._conn is not None:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    # -- API --------------------------------------------------------------

    async def insert(
        self,
        text: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> int:
        if len(embedding) != self._dim:
            raise ValueError(
                f"embedding dimension mismatch: got {len(embedding)}, expected {self._dim}"
            )
        return await asyncio.to_thread(self._insert_sync, text, embedding, metadata)

    def _insert_sync(
        self,
        text: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> int:
        conn = self._require_conn()
        created_at = metadata.get("created_at") or _now_iso()
        try:
            cur = conn.execute(
                """
                INSERT INTO memory_chunks
                    (user_id, chat_id, conversation_id, chunk_index, created_at, text)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    int(metadata["user_id"]),
                    int(metadata["chat_id"]),
                    str(metadata["conversation_id"]),
                    int(metadata["chunk_index"]),
                    created_at,
                    text,
                ),
            )
            rowid = cur.lastrowid
            conn.execute(
                "INSERT INTO memory_vec (rowid, embedding) VALUES (?, ?);",
                (rowid, _serialize_vector(embedding)),
            )
            conn.commit()
            return int(rowid or 0)
        except Exception:
            conn.rollback()
            raise

    async def delete(self, rowid: int) -> None:
        await asyncio.to_thread(self._delete_sync, rowid)

    def _delete_sync(self, rowid: int) -> None:
        conn = self._require_conn()
        try:
            conn.execute("DELETE FROM memory_chunks WHERE id = ?;", (rowid,))
            conn.execute("DELETE FROM memory_vec WHERE rowid = ?;", (rowid,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    async def search(
        self,
        embedding: list[float],
        *,
        top_k: int,
        scope_user_id: int,
    ) -> list[dict[str, Any]]:
        if len(embedding) != self._dim:
            raise ValueError(
                f"embedding dimension mismatch: got {len(embedding)}, expected {self._dim}"
            )
        if top_k <= 0:
            return []
        return await asyncio.to_thread(
            self._search_sync, embedding, top_k, scope_user_id
        )

    def _search_sync(
        self, embedding: list[float], top_k: int, scope_user_id: int
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        # Перебор `k` шире, чем top_k, чтобы пост-фильтрация по user_id
        # не оставила нас ни с чем.
        k_inner = max(top_k * 4, top_k)
        rows = conn.execute(
            """
            WITH knn AS (
                SELECT rowid, distance
                FROM memory_vec
                WHERE embedding MATCH ? AND k = ?
            )
            SELECT mc.id, mc.text, mc.conversation_id, mc.created_at, knn.distance
            FROM knn
            JOIN memory_chunks mc ON mc.id = knn.rowid
            WHERE mc.user_id = ?
            ORDER BY knn.distance
            LIMIT ?;
            """,
            (_serialize_vector(embedding), k_inner, scope_user_id, top_k),
        ).fetchall()
        return [
            {
                "id": r[0],
                "text": r[1],
                "conversation_id": r[2],
                "created_at": r[3],
                "distance": r[4],
            }
            for r in rows
        ]

    # -- internals --------------------------------------------------------

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SemanticMemory.init() was not called")
        return self._conn
