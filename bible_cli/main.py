#!/bin/env python3

import argparse
import difflib
import sqlite3
import sys

from . import bible_common as bc


def resolve_translation_list(conn, requested: list[str]):
    """Resolve a list of user-provided translation codes (from -t/--translation)
    against the DB. Returns (tables, errors).
    """
    all_tables = bc.get_translations(conn)
    tables = []
    errors = []
    for name in requested:
        table, err = bc.resolve_translation(all_tables, name)
        if err:
            errors.append(err)
        else:
            tables.append(table)
    return tables, errors


def apply_filter_translations(
    conn, base_tables: list[str], filters: bc.Filters
):
    """Let an embedded t:<name>/t:all filter override the base -t/--translation
    selection. Returns (tables, error).
    """
    if filters.translation_all:
        return bc.get_translations(conn), None
    if filters.translation:
        all_tables = bc.get_translations(conn)
        table, err = bc.resolve_translation(all_tables, filters.translation)
        if err:
            return None, err
        return [table], None
    return base_tables, None


def print_rows(rows, multi):
    last_trans = None
    for i, row in enumerate(rows):
        if last_trans != row.translation:
            last_trans = row.translation
            if i > 0:
                print()
        prefix = f"{row.translation.upper()} " if multi else ""
        print(f"{prefix}{row.book} {row.chapter}:{row.verse} {row.text}")


def suggest_books(book_input):
    close = difflib.get_close_matches(
        book_input.title(), bc.BOOKS, n=3, cutoff=0.6
    )
    if close:
        print(f"Did you mean: {', '.join(close)}?", file=sys.stderr)


def run_lookup(conn, base_tables, raw_ref):
    raw_ref = raw_ref.replace("\u2013", "-").replace("\u2014", "-")
    filters = bc.extract_filters(raw_ref)

    tables, err = apply_filter_translations(conn, base_tables, filters)
    if err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    parsed = bc.parse_reference(filters.remainder)
    if not parsed:
        print(
            f"Error: could not parse reference \u201c{raw_ref}\u201d",
            file=sys.stderr,
        )
        sys.exit(1)

    book_input = filters.book or parsed.book

    rows, errors = bc.lookup_verses(
        conn,
        tables,
        book_input,
        parsed.chapter,
        parsed.start_verse,
        parsed.end_verse,
    )

    for e in errors:
        print(f"Error: {e}", file=sys.stderr)

    if not rows:
        if errors:
            suggest_books(book_input)
            sys.exit(1)
        print("No matching verses found.")
        return

    multi = len(tables) > 1
    if not multi:
        print(f"{tables[0].upper()}\n")
    print_rows(rows, multi=multi)


def run_search(conn, base_tables, raw_search):
    filters = bc.extract_filters(raw_search)
    term = filters.remainder
    if not term:
        print(
            "Error: no search text provided (only filters).", file=sys.stderr
        )
        sys.exit(1)

    tables, err = apply_filter_translations(conn, base_tables, filters)
    if err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    rows, errors = bc.search_verses(conn, tables, term, filters.book)

    for e in errors:
        print(f"Error: {e}", file=sys.stderr)

    multi = len(tables) > 1
    header = f'Search results for "{term}"'
    if filters.book:
        header += f" in {filters.book}"
    if not multi:
        header += f" - {tables[0].upper()}"
    print(f"{header}\n")

    if not rows:
        print("No results found.")
        print()
        return

    print_rows(rows, multi=multi)
    print()


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
        help="The translation code (e.g., NET, KJV). Default: NRSVUE. Use commas "
        "for multiple. Use 'all' for all translations. Can be overridden by an "
        "embedded t:<name> or t:all filter (see below).",
    )
    parser.add_argument(
        "-s",
        "--search",
        help="Search translations for words. Supports 'b:<book>' and "
        "'t:<translation>' (or 't:all') filters anywhere in the text, e.g. "
        '-s "faith b:romans t:kjv".',
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
    parser.add_argument(
        "filters",
        nargs="*",
        help="Optional t:<translation> filter (e.g. t:all, t:kjv) to refine "
        "the lookup, e.g. '1cor 1:1 t:all'.",
    )

    args = parser.parse_args()

    db_path = bc.get_db_path()
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = None
    try:
        conn = sqlite3.connect(db_path)

        if args.list:
            print("Available translations:\n")
            print("\n".join(t.upper() for t in bc.get_translations(conn)))
            sys.exit(0)

        if args.translation.strip().lower() == "all":
            base_tables = bc.get_translations(conn)
        else:
            base_tables, errors = resolve_translation_list(
                conn, args.translation.split(",")
            )
            if errors:
                for e in errors:
                    print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

        if args.search:
            run_search(conn, base_tables, args.search)
        else:
            combined_ref = " ".join(
                [args.book, args.chapter_verse, *args.filters]
            )
            run_lookup(conn, base_tables, combined_ref)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
