#!/usr/bin/env python3
"""Shared database access and text-parsing helpers for the Bible CLI and GUI.

Both main.py (CLI) and gui.py (Qt GUI) build on top of these functions so
that book/translation resolution, filter parsing, and query construction
behave identically in both places. The CLI and GUI still own their own
presentation (plain text vs. HTML), but never talk to sqlite or parse
reference/search text on their own.
"""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Canonical book order/names. This is used only as a fallback for "did you
# mean" suggestions when a book can't be resolved against a translation's
# actual table contents -- book *resolution* itself is always done against
# the database (see resolve_book), since different translations can cover
# different books (e.g. a Greek New Testament table has no Old Testament
# books at all).
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

DEFAULT_TRANSLATION = "nrsvue"

REQUIRED_COLUMNS = {"book", "chapter", "verse", "text"}


def get_db_path() -> Path:
    return Path(__file__).parent / "translations" / "bible.db"


def quote_ident(name: str) -> str:
    """Safely quote a SQLite identifier (table/column name)."""
    return '"' + name.replace('"', '""') + '"'


def get_translations(conn: sqlite3.Connection) -> list[str]:
    """Return the names of tables that look like translations (i.e. have
    book/chapter/verse/text columns), in alphabetical order, as they are
    stored in the database (typically lowercase).
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    )
    tables = [row[0] for row in cur.fetchall()]

    valid = []
    for t in tables:
        cur.execute(f"PRAGMA table_info({quote_ident(t)})")
        cols = {row[1] for row in cur.fetchall()}
        if REQUIRED_COLUMNS.issubset(cols):
            valid.append(t)
    return valid


def resolve_translation(translations: list[str], name_input: str):
    """Resolve name_input against translations using lowercase matching.

    Returns (table, None) on an exact case-insensitive match, or
    (None, error_message) if there's no match.
    """
    normalized = name_input.strip().lower()
    for t in translations:
        if t.lower() == normalized:
            return t, None
    return None, f"No translation matches \u201c{name_input}\u201d."


def resolve_book(conn: sqlite3.Connection, table: str, book_input: str):
    """Resolve a possibly-abbreviated book name against table's books.

    Matching compares book_input (lowercased, spaces stripped) as a prefix
    against the DB's book field, normalized the same way, e.g. "1cor"
    matches "1 Corinthians". Resolution is scoped to a single translation
    table, since not every translation necessarily contains every book.

    Returns (book, None) on a single unambiguous match, or
    (None, error_message) if there's no match or more than one.
    """
    normalized_input = book_input.lower().replace(" ", "")
    cur = conn.cursor()
    cur.execute(
        f"SELECT DISTINCT book, book_id FROM {quote_ident(table)} "
        f"WHERE LOWER(REPLACE(book, ' ', '')) LIKE ? "
        f"ORDER BY book_id",
        (f"{normalized_input}%",),
    )
    matches = cur.fetchall()
    distinct_books = list(dict.fromkeys(row[0] for row in matches))

    if not distinct_books:
        return None, f"No book matches \u201c{book_input}\u201d."
    if len(distinct_books) > 1:
        return None, (
            f"\u201c{book_input}\u201d is ambiguous, matches: "
            + ", ".join(distinct_books)
        )
    return distinct_books[0], None


def list_books(conn: sqlite3.Connection, table: str) -> list[str]:
    """Books in table, in canonical order (by minimum book_id)."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT book, MIN(book_id) AS ord FROM {quote_ident(table)} "
        f"GROUP BY book ORDER BY ord"
    )
    return [row[0] for row in cur.fetchall()]


def list_chapters(
    conn: sqlite3.Connection, table: str, book: str
) -> list[str]:
    """Chapter numbers (as strings) for book in table, in order."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT DISTINCT chapter FROM {quote_ident(table)} "
        f"WHERE book = ? ORDER BY chapter",
        (book,),
    )
    return [str(row[0]) for row in cur.fetchall()]


def bold_term(term: str, text: str) -> str:
    """Wrap case-insensitive occurrences of term in text with <b> tags."""
    return re.sub(
        re.escape(term),
        lambda m: f"<b>{m.group(0)}</b>",
        text,
        flags=re.IGNORECASE,
    )


# ---------- filter parsing ----------

# Matches a "b:xxx" or "t:xxx" token, where xxx is a single non-whitespace
# chunk. The key must be preceded by the start of the string or whitespace,
# so this won't misfire inside an ordinary word that happens to contain a
# colon.
_FILTER_RE = re.compile(
    r"(?:^|(?<=\s))(?P<key>[bt]):(?P<value>\S+)", re.IGNORECASE
)


@dataclass
class Filters:
    book: str | None = None
    translation: str | None = None
    translation_all: bool = False
    remainder: str = ""


def extract_filters(raw_input: str) -> Filters:
    """Pull "b:<book>" and "t:<translation>" tokens out of raw_input.

    "t:all" (case-insensitive) sets translation_all rather than
    translation. remainder is raw_input with every recognized filter token
    removed and whitespace collapsed -- i.e. whatever lookup/search text is
    left over once the filters are stripped out.
    """
    filters = Filters()

    def _consume(m: "re.Match[str]") -> str:
        key = m.group("key").lower()
        value = m.group("value")
        if key == "b":
            filters.book = value
        elif key == "t":
            if value.lower() == "all":
                filters.translation_all = True
            else:
                filters.translation = value
        return ""

    remainder = _FILTER_RE.sub(_consume, raw_input)
    filters.remainder = re.sub(r"\s+", " ", remainder).strip()
    return filters


# ---------- reference parsing ----------


@dataclass
class Reference:
    book: str
    chapter: int
    start_verse: int | None
    end_verse: int | None


# Matches: book [chapter[:start_verse[-end_verse]]]
# "book" is a lazy free-form match so it can contain spaces or digits (e.g.
# "1cor", "song of solomon"); the trailing chapter/verse portion is only
# consumed if it looks like whitespace followed by digits.
_REFERENCE_RE = re.compile(
    r"^\s*(?P<book>.+?)"
    r"(?:\s+(?P<chapter>\d+)(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?)?"
    r"\s*$"
)


def parse_reference(ref: str) -> Reference | None:
    """Parse 'book [chapter[:start_verse[-end_verse]]]' into a Reference.

    Missing chapter defaults to 1. Missing start_verse means "no verse
    filter" (i.e. show the whole chapter) rather than defaulting to verse
    1. An explicit start_verse with no end_verse means just that one
    verse. Returns None if ref does not match the expected shape.
    """
    match = _REFERENCE_RE.match(ref)
    if not match or not match.group("book"):
        return None

    book = match.group("book").strip()
    chapter = int(match.group("chapter")) if match.group("chapter") else 1
    start_verse = int(match.group("start")) if match.group("start") else None
    if start_verse is None:
        end_verse = None
    else:
        end_verse = (
            int(match.group("end")) if match.group("end") else start_verse
        )
    return Reference(
        book=book,
        chapter=chapter,
        start_verse=start_verse,
        end_verse=end_verse,
    )


# ---------- query construction & execution ----------


@dataclass
class VerseRow:
    translation: str
    book: str
    chapter: int
    verse: int
    text: str


def build_verse_query(
    table: str, book: str, chapter: int, start_verse, end_verse
):
    query = (
        f"SELECT verse, text FROM {quote_ident(table)} "
        f"WHERE book = ? AND chapter = ?"
    )
    params = [book, chapter]
    if start_verse is not None:
        query += " AND verse >= ? AND verse <= ?"
        params.extend([start_verse, end_verse])
    query += " ORDER BY verse;"
    return query, params


def build_search_query(table: str, term: str, book: str | None = None):
    query = (
        f"SELECT book, chapter, verse, text FROM {quote_ident(table)} "
        f"WHERE text LIKE ?"
    )
    params = [f"%{term}%"]
    if book:
        query += " AND book = ?"
        params.append(book)
    query += " ORDER BY book_id, chapter, verse;"
    return query, params


def lookup_verses(
    conn: sqlite3.Connection,
    tables: list[str],
    book_input: str,
    chapter: int,
    start_verse,
    end_verse,
):
    """Look up a reference across one or more translation tables.

    Book resolution happens independently per table, so e.g. a
    Greek-New-Testament-only translation simply contributes nothing for an
    Old Testament reference instead of failing the whole lookup. Returns
    (rows, errors). When only one table is given, a resolution failure for
    it is reported as an error; across several tables, resolution failures
    are only reported in aggregate if *none* of them resolve the book.
    """
    rows: list[VerseRow] = []
    errors: list[str] = []
    resolved_any = False

    for table in tables:
        book, err = resolve_book(conn, table, book_input)
        if err:
            if len(tables) == 1:
                errors.append(err)
            continue
        resolved_any = True

        query, params = build_verse_query(
            table, book, chapter, start_verse, end_verse
        )
        cur = conn.cursor()
        cur.execute(query, params)
        for verse, text in cur.fetchall():
            rows.append(VerseRow(table, book, chapter, verse, text))

    if len(tables) > 1 and not resolved_any:
        errors.append(
            f"No book matches \u201c{book_input}\u201d in any translation."
        )

    return rows, errors


def search_verses(
    conn: sqlite3.Connection,
    tables: list[str],
    term: str,
    book_input: str | None = None,
):
    """Search for term across one or more translation tables, optionally
    scoped to a resolved book (resolved independently per table, same as
    lookup_verses). Returns (rows, errors).
    """
    rows: list[VerseRow] = []
    errors: list[str] = []
    resolved_any = False

    for table in tables:
        book = None
        if book_input:
            book, err = resolve_book(conn, table, book_input)
            if err:
                if len(tables) == 1:
                    errors.append(err)
                continue
        resolved_any = True

        query, params = build_search_query(table, term, book)
        cur = conn.cursor()
        cur.execute(query, params)
        for b, chapter, verse, text in cur.fetchall():
            rows.append(VerseRow(table, b, chapter, verse, text))

    if book_input and len(tables) > 1 and not resolved_any:
        errors.append(
            f"No book matches \u201c{book_input}\u201d in any translation."
        )

    return rows, errors
