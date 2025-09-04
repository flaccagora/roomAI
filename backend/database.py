import sqlite3
import os

from dotenv import load_dotenv  
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO)


class DB():
    def __init__(self, path=None):
        # Use a file-based sqlite DB in current working dir by default
        # Choose path from explicit arg or DB_PATH env, defaulting to 'facebook_posts.db'
        db_path = path or os.getenv('DB_PATH', 'facebook_posts.db')
        # Allow usage across threads in FastAPI context
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.c = self.conn.cursor()

        # Create table if not exists (facebook_posts)
        self.c.execute("""
        CREATE TABLE IF NOT EXISTS facebook_posts (
            url TEXT,
            time TEXT,
            user TEXT,
            text TEXT,
            topReactionsCount INTEGER,
            feedbackId TEXT,
            id TEXT PRIMARY KEY,
            legacyId TEXT,
            attachments TEXT,
            likesCount INTEGER,
            sharesCount INTEGER,
            commentsCount INTEGER,
            facebookId TEXT,
            groupTitle TEXT,
            inputUrl TEXT,
            status TEXT,
            motivo TEXT
        )
        """)
        self.conn.commit()

        # Create scheduler_config singleton table to persist scheduler state
        self.c.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                active INTEGER DEFAULT 0,
                minutes INTEGER,
                webhook TEXT,
                last_run_time TEXT
            )
            """
        )
        # Ensure a singleton row exists
        self.c.execute("INSERT OR IGNORE INTO scheduler_config (id, active) VALUES (1, 0)")
        self.conn.commit()

        # Ensure optional columns for time-of-day scheduling exist
        try:
            cols = {r[1] for r in self.c.execute("PRAGMA table_info(scheduler_config)").fetchall()}
            if 'minutes_day' not in cols:
                self.c.execute("ALTER TABLE scheduler_config ADD COLUMN minutes_day INTEGER")
            if 'minutes_night' not in cols:
                self.c.execute("ALTER TABLE scheduler_config ADD COLUMN minutes_night INTEGER")
            if 'day_start_hour' not in cols:
                self.c.execute("ALTER TABLE scheduler_config ADD COLUMN day_start_hour INTEGER DEFAULT 8")
            if 'night_start_hour' not in cols:
                self.c.execute("ALTER TABLE scheduler_config ADD COLUMN night_start_hour INTEGER DEFAULT 20")
            self.conn.commit()
        except Exception:
            pass

        # Create table for accepted posts
        self.c.execute("""
        CREATE TABLE IF NOT EXISTS good_facebook_posts (
            url TEXT,
            time TEXT,
            user TEXT,
            text TEXT,
            topReactionsCount INTEGER,
            feedbackId TEXT,
            id TEXT PRIMARY KEY,
            legacyId TEXT,
            attachments TEXT,
            likesCount INTEGER,
            sharesCount INTEGER,
            commentsCount INTEGER,
            facebookId TEXT,
            groupTitle TEXT,
            inputUrl TEXT,
            status TEXT
        )
        """)
        self.conn.commit()

    def add_items_to_db(self, items, table="facebook_posts"):
        """Insert a list of item dicts into the named table. The table is
        expected to have the same columns as created above. Missing subkeys
        are tolerated and will become NULL in the DB.
        """
        count = 0
        for item in items:
                
            try:
                if item.get('id') == None:
                    raise Exception("Item id is None")
                user = item.get('user') if isinstance(item.get('user'), dict) else None
                user_id = user.get('id') if user else None
                attachments = None
                if item.get('attachments') and isinstance(item.get('attachments'), list) and len(item.get('attachments')):
                    # store the first attachment url
                    a = item.get('attachments')[0]
                    if isinstance(a, dict):
                        attachments = a.get('url')
                params = (
                    item.get('url'),
                    item.get('time'),
                    user_id,
                    item.get('text'),
                    item.get('topReactionsCount'),
                    item.get('feedbackId'),
                    item.get('id'),
                    item.get('legacyId'),
                    attachments,
                    item.get('likesCount'),
                    item.get('sharesCount'),
                    item.get('commentsCount'),
                    item.get('facebookId'),
                    item.get('groupTitle'),
                    item.get('inputUrl'),
                    item.get('status')
                )
                self.c.execute(f"""
                INSERT OR IGNORE INTO {table} (
                    url, time, user, text, topReactionsCount, feedbackId,
                    id, legacyId, attachments, likesCount, sharesCount, commentsCount,
                    facebookId, groupTitle, inputUrl, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, params)
            except Exception as e:
                count += 1
                logging.exception("Failed to insert item into %s: %s", table, e)
        self.conn.commit()
        return count

    def update_item_field(self, id, field, value):
        self.c.execute("UPDATE facebook_posts SET {} = ? WHERE id = ?".format(field), (value, id))
        self.conn.commit()
        return

    def fetch_items(self, table="facebook_posts", limit=50, offset=0, search=None):
        """Fetch items from a given table with optional text search, pagination.
        Returns a list of dict rows.
        """
        # Basic guardrails
        if table not in ("facebook_posts", "good_facebook_posts"):
            raise ValueError("Invalid table")
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        
        if table == "good_facebook_posts":
            base = f"SELECT id, url, time, text, attachments, likesCount, commentsCount, inputUrl FROM {table}"
        else:
            base = f"SELECT id, url, time, text, attachments, likesCount, commentsCount, inputUrl, status, motivo FROM {table}"
        params = []
        if search:
            base += " WHERE text LIKE ?"
            params.append(f"%{search}%")
        base += " ORDER BY time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.c.execute(base, params).fetchall()
        return [dict(r) for r in rows]

    def fetch_items_with_null_status(self, limit=100, offset=0):
        """Fetch facebook_posts rows where status IS NULL."""
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        base = (
            "SELECT id, url, time, text, attachments, likesCount, commentsCount, inputUrl, status, motivo "
            "FROM facebook_posts WHERE status IS NULL ORDER BY time DESC LIMIT ? OFFSET ?"
        )
        rows = self.c.execute(base, [limit, offset]).fetchall()
        return [dict(r) for r in rows]

    # ----------------------
    # Persistence helpers
    # ----------------------
    def fetch_good_ids(self):
        """Return a list of ids already present in good_facebook_posts."""
        rows = self.c.execute("SELECT id FROM good_facebook_posts").fetchall()
        return [r[0] for r in rows]

    def get_scheduler_config(self):
        """Return scheduler config singleton as a dict including time-of-day fields."""
        row = self.c.execute(
            "SELECT active, minutes, webhook, last_run_time, minutes_day, minutes_night, day_start_hour, night_start_hour FROM scheduler_config WHERE id = 1"
        ).fetchone()
        if not row:
            return {"active": 0, "minutes": None, "webhook": None, "last_run_time": None,
                    "minutes_day": None, "minutes_night": None, "day_start_hour": 8, "night_start_hour": 20}
        d = dict(row)
        # sqlite3.Row supports key access, but ensure plain dict with python types
        return {
            "active": int(d.get("active") or 0),
            "minutes": d.get("minutes"),
            "webhook": d.get("webhook"),
            "last_run_time": d.get("last_run_time"),
            "minutes_day": d.get("minutes_day"),
            "minutes_night": d.get("minutes_night"),
            "day_start_hour": d.get("day_start_hour") if d.get("day_start_hour") is not None else 8,
            "night_start_hour": d.get("night_start_hour") if d.get("night_start_hour") is not None else 20,
        }

    def upsert_scheduler_config(self, active=None, minutes=None, webhook=None, last_run_time=None,
                                minutes_day=None, minutes_night=None, day_start_hour=None, night_start_hour=None):
        """Upsert fields into the singleton scheduler_config row (id=1)."""
        # Read current
        current = self.get_scheduler_config()
        new_vals = {
            "active": int(active) if active is not None else current.get("active", 0),
            "minutes": minutes if minutes is not None else current.get("minutes"),
            "webhook": webhook if webhook is not None else current.get("webhook"),
            "last_run_time": last_run_time if last_run_time is not None else current.get("last_run_time"),
            "minutes_day": minutes_day if minutes_day is not None else current.get("minutes_day"),
            "minutes_night": minutes_night if minutes_night is not None else current.get("minutes_night"),
            "day_start_hour": day_start_hour if day_start_hour is not None else current.get("day_start_hour", 8),
            "night_start_hour": night_start_hour if night_start_hour is not None else current.get("night_start_hour", 20),
        }
        self.c.execute(
            """
            INSERT INTO scheduler_config (id, active, minutes, webhook, last_run_time, minutes_day, minutes_night, day_start_hour, night_start_hour)
            VALUES (1, :active, :minutes, :webhook, :last_run_time, :minutes_day, :minutes_night, :day_start_hour, :night_start_hour)
            ON CONFLICT(id) DO UPDATE SET
                active=excluded.active,
                minutes=excluded.minutes,
                webhook=excluded.webhook,
                last_run_time=excluded.last_run_time,
                minutes_day=excluded.minutes_day,
                minutes_night=excluded.minutes_night,
                day_start_hour=excluded.day_start_hour,
                night_start_hour=excluded.night_start_hour
            """,
            new_vals,
        )
        self.conn.commit()
        return new_vals

    def set_last_run_time(self, ts: str | None):
        self.upsert_scheduler_config(last_run_time=ts)

    def get_last_run_time(self):
        return self.get_scheduler_config().get("last_run_time")

    def close(self):
        try:
            self.c.close()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    db = DB()
    db.close()