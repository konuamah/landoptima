import os
import psycopg2
from contextlib import contextmanager

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
    "database": os.environ.get("DB_NAME", "landoptima"),
    "user": os.environ.get("DB_USER", "landoptima"),
    "password": os.environ.get("DB_PASSWORD", "landoptima"),
}


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
