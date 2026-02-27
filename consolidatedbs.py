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
        conn.execute(f"ATTACH DATABASE ? AS src", (str(db_path),))
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {translation} AS
            SELECT * FROM src.{translation}
        """)
        conn.execute("DETACH DATABASE src")

    conn.commit()
    conn.close()
    print(f"Written to {output}")


if __name__ == "__main__":
    merge_databases()
