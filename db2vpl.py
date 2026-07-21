#!/bin/env python

import glob
import os
import sqlite3
import sys


def generate_vpl(translation):

    vpl_text = []

    # Construct the database path
    db_name = f"{translation.upper()}_bible.db"
    db_path = os.path.join("translations", db_name)

    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        sys.exit(1)

    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        # conn.set_trace_callback(print)
        cursor = conn.cursor()

        query = f"SELECT book, chapter, verse, text FROM {translation.lower()} ORDER BY book_id, chapter, verse;"

        cursor.execute(query)
        results = cursor.fetchall()

        if results:
            for row in results:
                vpl_text.append(f"{row[0]} {row[1]}:{row[2]} {row[3]}")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

    return "\n".join(vpl_text)


def get_translations():
    translations = []
    for db in sorted(glob.glob("translations/*.db")):
        translations.append(os.path.basename(db).replace("_bible.db", ""))
    return translations


def main():
    for translation in get_translations():
        with open(f"../sword-mods/{translation}.vpl", "w") as fh:
            fh.write(generate_vpl(translation))


if __name__ == "__main__":
    main()
