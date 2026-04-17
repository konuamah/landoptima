import os
import psycopg2
from contextlib import contextmanager
from urllib.parse import urlparse


def get_db_config_from_url(url: str = None) -> dict:
    if url is None:
        url = os.environ.get("DATABASE_URL", "")
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") or "landoptima",
        "user": parsed.username or "landoptima",
        "password": parsed.password or "landoptima",
    }


DB_CONFIG = get_db_config_from_url()


@contextmanager
def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_cursor(cursor_factory=None):
    with get_db_connection() as conn:
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
