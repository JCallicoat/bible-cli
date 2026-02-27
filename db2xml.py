#!/bin/env python3

import argparse
import os
import sqlite3
import sys
import xml.etree.ElementTree as ET

BOOKS = [
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
    "Joshua",
    "Judges",
    "Ruth",
    "1 Samuel",
    "2 Samuel",
    "1 Kings",
    "2 Kings",
    "1 Chronicles",
    "2 Chronicles",
    "Ezra",
    "Nehemiah",
    "Esther",
    "Job",
    "Psalm",
    "Proverbs",
    "Ecclesiastes",
    "Song Of Solomon",
    "Isaiah",
    "Jeremiah",
    "Lamentations",
    "Ezekiel",
    "Daniel",
    "Hosea",
    "Joel",
    "Amos",
    "Obadiah",
    "Jonah",
    "Micah",
    "Nahum",
    "Habakkuk",
    "Zephaniah",
    "Haggai",
    "Zechariah",
    "Malachi",
    "Matthew",
    "Mark",
    "Luke",
    "John",
    "Acts",
    "Romans",
    "1 Corinthians",
    "2 Corinthians",
    "Galatians",
    "Ephesians",
    "Philippians",
    "Colossians",
    "1 Thessalonians",
    "2 Thessalonians",
    "1 Timothy",
    "2 Timothy",
    "Titus",
    "Philemon",
    "Hebrews",
    "James",
    "1 Peter",
    "2 Peter",
    "1 John",
    "2 John",
    "3 John",
    "Jude",
    "Revelation",
]


def main():
    parser = argparse.ArgumentParser(
        description="Export Bible translation to XML"
    )
    parser.add_argument(
        "translation", help="Bible translation (e.g. NET, KJV)"
    )
    parser.add_argument("output", help="Output XML file path")
    args = parser.parse_args()

    db_path = f"{args.translation.upper()}/{args.translation.upper()}_bible.db"
    table = args.translation.lower()

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.OperationalError as e:
        print(f"Error opening database: {e}", file=sys.stderr)
        sys.exit(1)

    bible_elem = ET.Element("bible")

    for book in BOOKS:
        book_elem = ET.SubElement(bible_elem, "b", n=book)

        try:
            cursor = conn.execute(
                f"SELECT chapter, verse, text FROM {table} WHERE book = '{book}' ORDER BY chapter, verse"
            )
        except sqlite3.OperationalError as e:
            print(f"Query error for book '{book}': {e}", file=sys.stderr)
            conn.close()
            sys.exit(1)

        last_chapter = None
        chapter_elem = None
        for chapter, verse, text in cursor:
            if chapter != last_chapter:
                chapter_elem = ET.SubElement(book_elem, "c", n=str(chapter))
                last_chapter = chapter
            verse_elem = ET.SubElement(chapter_elem, "v", n=str(verse))
            verse_elem.text = text

    conn.close()

    tree = ET.ElementTree(bible_elem)
    ET.indent(tree, space="  ")

    output_path = os.path.expanduser(args.output)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", xml_declaration=False)
        f.write("\n")
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
