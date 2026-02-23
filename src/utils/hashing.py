"""Short hash ID generation with collision checking."""

import secrets

import aiosqlite


async def generate_hash_id(db: aiosqlite.Connection, length: int = 4) -> str:
    """Generate a unique short hex hash ID.

    Uses *length* bytes (default 4 = 8 hex characters) for ~4 billion
    possible values.  Checks the ``bugs`` table for collisions and retries
    up to 10 times before raising ``RuntimeError``.
    """
    for _ in range(10):
        hash_id = secrets.token_hex(length)
        async with db.execute(
            "SELECT 1 FROM bugs WHERE hash_id = ?", (hash_id,)
        ) as cursor:
            if await cursor.fetchone() is None:
                return hash_id
    raise RuntimeError("Failed to generate unique hash ID after 10 attempts")
