import os 
import sqlite3

def stats():
    # return db statistics db is in /data/facebook_posts.db


    db_path = "data/facebook_posts.db"
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print(f"Current working directory: {os.getcwd()}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get the number of tables
    cursor.execute("SELECT count(name) FROM sqlite_master WHERE type='table'")
    table_count = cursor.fetchone()[0]

    # Get the number of rows in each table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    row_counts = {}
    for table in tables:
        cursor.execute(f"SELECT count(*) FROM {table[0]}")
        row_counts[table[0]] = cursor.fetchone()[0]

    conn.close()

    return {
        "table_count": table_count,
        "row_counts": row_counts
    }

if __name__ == "__main__":
    s = stats()
    print(s)