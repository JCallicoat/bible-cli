#!/bin/env python3

import sqlite3
from pathlib import Path


def merge_databases():
    translations_dir = Path(__file__).parent / "bible_cli" / "translations"
    output = translations_dir / "bible.db"

    conn = sqlite3.connect(output)

    for db_path in sorted(translations_dir.glob("*_bible.db")):
        translation = db_path.stem.replace("_bible", "").lower()
        print(f"Merging {translation}...")
        conn.execute("ATTACH DATABASE ? AS src", (str(db_path),))
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {translation} AS
            SELECT * FROM src.{translation}
        """)
        conn.execute("DETACH DATABASE src")

        print(f"Indexing {translation}...")
        conn.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_{translation}_pk
            ON {translation} (book_id, chapter, verse)
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{translation}_book
            ON {translation} (book)
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{translation}_book_chapter
            ON {translation} (book, chapter)
        """)

    conn.commit()
    conn.close()
    print(f"Written to {output}")


if __name__ == "__main__":
    merge_databases()
