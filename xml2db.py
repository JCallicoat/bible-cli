#!/bin/env python

import argparse
import sqlite3
import xml.etree.ElementTree as ET
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Parse Bible XML and populate SQLite database"
    )
    parser.add_argument(
        "translation", help="Abbreviation for translation (e.g., KJV)"
    )
    parser.add_argument("xml_file", help="Path to the XML file")
    parser.add_argument("--db", help="Output database path")
    args = parser.parse_args()

    if not args.db:
        args.db = f"{args.translation.upper()}_bible.db"

    try:
        tree = ET.parse(args.xml_file)
    except (ET.ParseError, FileNotFoundError) as e:
        print(f"Error reading XML file: {e}", file=sys.stderr)
        sys.exit(1)

    root = tree.getroot()

    conn = sqlite3.connect(args.db)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {args.translation.lower()} (
            book_id int not null,
            book varchar(255) not null,
            chapter int not null,
            verse int not null,
            text varchar(1000) not null,
            primary key (book_id, chapter, verse)
        )
    """)
    conn.execute(f"DELETE FROM {args.translation.lower()}")

    rows = []
    book_id = 0

    for book_elem in root.findall("b"):
        book_id += 1
        book_name = book_elem.get("n")

        for chapter_elem in book_elem.findall("c"):
            chapter_num = int(chapter_elem.get("n"))

            for verse_elem in chapter_elem.findall("v"):
                verse_num = int(verse_elem.get("n"))
                text = (verse_elem.text or "").strip()
                rows.append((book_id, book_name, chapter_num, verse_num, text))

    conn.executemany(
        f"INSERT INTO {args.translation.lower()} (book_id, book, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    print(
        f"Done. Inserted {len(rows)} verses across {book_id} books into '{args.db}'."
    )


if __name__ == "__main__":
    main()
