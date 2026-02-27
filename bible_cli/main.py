#!/bin/env python3

import argparse
import difflib
import sqlite3
import sys

from pathlib import Path

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


def get_translations(conn):
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    )
    return [row[0].upper() for row in cursor.fetchall()]


def get_db_path():
    return Path(__file__).parent / "translations" / "bible.db"


def find_book(book):
    book = book.title().replace(" ", "").replace("Psalms", "Psalm")
    for b in BOOKS:
        if book in b.replace(" ", ""):
            return b
    return None


def build_verse_query(translation, book, chapter_verse):
    query = f"SELECT verse, text FROM {translation.lower()} WHERE book = ?"
    params = [book]

    if chapter_verse:
        verses = None
        chapter = chapter_verse

        if ":" in chapter_verse:
            chapter, verses = chapter_verse.split(":", 1)

        query += " AND chapter = ?"
        params.append(chapter)

        if verses:
            if "-" in verses:
                start, end = verses.split("-", 1)
                query += " AND verse >= ? AND verse <= ?"
                params.extend([start, end])
            else:
                query += " AND verse = ?"
                params.append(verses)

    query += " ORDER BY book_id, chapter, verse;"
    return (query, params)


def print_verses(conn, translation, book, chapter_verse, query, params):
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()

        if results:
            print(f"{book} {chapter_verse} - {translation.upper()}")
            for row in results:
                print(f"({row[0]}) {row[1]}")
            print()
        else:
            print("No matching verses found.")

    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)


def build_search_query(translation, search):
    query = f"SELECT book, chapter, verse, text FROM {translation.lower()} WHERE text LIKE ?"
    query += " ORDER BY book_id, chapter, verse;"
    return (query, [search])


def print_search(conn, translation, search, query, params):
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()

        if results:
            print(f'Search results for "{search}" - {translation.upper()}')
            for row in results:
                print(f"{row[0]} {row[1]}:{row[2]} {row[3]}")
        else:
            print(f'No results for "{search}" - {translation.upper()}')

        print()
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Query a Bible translation SQLite database."
    )
    parser.add_argument(
        "-l", "--list", help="List available translations", action="store_true"
    )
    parser.add_argument(
        "-t",
        "--translation",
        default="NRSVUE",
        help="The translation code (e.g., NET, KJV). Default: NRSVUE. Use commas for multiple. Use 'all' for all translations.",
    )
    parser.add_argument(
        "-s",
        "--search",
        help="Search translations for words.",
    )
    parser.add_argument(
        "book", nargs="?", default="Genesis", help="The name of the book"
    )
    parser.add_argument(
        "chapter_verse",
        nargs="?",
        default="1",
        help="The chapter and optionally verse in format 1, 1:1 or 1:1-3",
    )

    args = parser.parse_args()

    db_path = get_db_path()
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    # handle en and em dashes in verse input
    args.chapter_verse = args.chapter_verse.replace("\u2013", "-").replace(
        "\u2014", "-"
    )

    conn = None
    try:
        conn = sqlite3.connect(db_path)

        if args.list:
            print("Available translations:\n")
            print("\n".join(get_translations(conn)))
            sys.exit(0)

        translations = (
            get_translations(conn)
            if args.translation.lower() == "all"
            else args.translation.split(",")
        )

        if args.search:
            for translation in translations:
                query, params = build_search_query(
                    translation, f"%{args.search}%"
                )
                print_search(conn, translation, args.search, query, params)
        else:
            book = find_book(args.book)
            if book is None:
                print(f"Error: Unknown book '{args.book}'", file=sys.stderr)
                close = difflib.get_close_matches(
                    args.book.title(), BOOKS, n=3, cutoff=0.6
                )
                if close:
                    print(
                        f"Did you mean: {', '.join(close)}?",
                        file=sys.stderr,
                    )
                sys.exit(1)
            for translation in translations:
                query, params = build_verse_query(
                    translation, book, args.chapter_verse
                )
                print_verses(
                    conn, translation, book, args.chapter_verse, query, params
                )
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
