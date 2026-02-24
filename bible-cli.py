#!/bin/env python

import argparse
import sqlite3
import glob
import os
import sys

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


def find_book(book):
    book = book.title().replace(" ", "")
    for b in BOOKS:
        if book in b.replace(" ", ""):
            return b
    return None


def build_verse_query(translation, book, chapter_verse):
    # Build the query dynamically based on provided arguments
    # We assume the table name is 'net' as per your schema description
    query = f"SELECT verse, text FROM {translation.lower()} WHERE 1=1"
    params = []

    query += " AND book = ?"
    params.append(book)

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
                params.append(start)
                params.append(end)
            else:
                query += " AND verse = ?"
                params.append(verses)

    # Sort results to ensure they are printed in biblical order
    query += " ORDER BY book_id, chapter, verse;"

    # print(query)
    # print(params)
    return (query, params)


def print_verses(translation, book, chapter_verse, query, params):

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
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()


def build_search_query(translation, search):
    # Build the query dynamically based on provided arguments
    # We assume the table name is 'net' as per your schema description
    query = f"SELECT book, chapter, verse, text FROM {translation.lower()} WHERE 1=1"
    params = []

    query += " AND text like ?"
    params.append(search)

    # Sort results to ensure they are printed in biblical order
    query += " ORDER BY book_id, chapter, verse;"

    # print(query)
    # print(params)
    return (query, params)


def print_search(translation, search, query, params):

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
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()


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
        help="The translation code (e.g., NET, KJV). Default: NRSVUE. Use commas for multiple.",
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

    if args.list:
        print("Available translations:\n")
        for db in sorted(glob.glob("translations/*.db")):
            print(os.path.basename(db).replace("_bible.db", ""))
        sys.exit(0)

    for translation in args.translation.split(","):
        if args.search:
            query, params = build_search_query(translation, f"%{args.search}%")
            print_search(translation, args.search, query, params)
        else:
            book = find_book(args.book)
            query, params = build_verse_query(
                translation, book, args.chapter_verse
            )
            print_verses(translation, book, args.chapter_verse, query, params)


if __name__ == "__main__":
    main()
