from typing import Any
from pymongo import AsyncMongoClient
from app.config import get_settings

# main.py (lifespan) -> connect_to_database() / close_database()
# routes -> get_database() -> repositories
# This module owns the MongoDB connection. Routes never create their own
# client; they ask for the shared database and pass it to repositories, which
# are the only code that queries it.

# One shared client/database reference
# Module-level so every request reuses the same connection pool. They start
# as None, meaning "not connected yet".
_client: AsyncMongoClient | None = None
_database: Any | None = None

# Called once at application startup (see lifespan in main.py).
async def connect_to_database() -> None:
    global _client, _database

    if _client is not None:
        return  # Already connected

    settings = get_settings()
    # get_secret_value() reveals the connection string only here, where it
    # is actually needed.
    client = AsyncMongoClient(settings.mongodb_uri.get_secret_value())

    try:
        # Test the connection by pinging the server
        await client.admin.command("ping")
    except Exception:
        # The server is unreachable or rejected us: release the client's
        # resources and let the error stop startup.
        await client.close()
        raise

    # Only store the references once the ping has succeeded, so a failed
    # connection never leaves a half-working client behind.
    _client = client
    _database = _client[settings.mongodb_database]

# Used by routes to get the shared database handle.
def get_database() -> Any:
    # Fail with a clear message if startup never connected (for example,
    # when used outside the running app).
    if _database is None:
        raise RuntimeError("Database connection is not established. Call connect_to_database() first.")
    return _database

# Called once at application shutdown (see lifespan in main.py).
async def close_database() -> None:
    global _client, _database

    if _client is not None:
        await _client.close()
        _client = None
        _database = None
