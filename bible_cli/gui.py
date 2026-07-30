#!/usr/bin/env python3
"""
Simple Bible viewer GUI built with PySide6 (Qt6).

Expects a SQLite database where each table represents one translation,
with at least the columns: book_id, book, chapter, verse, text.

Usage:
    bible-gui [path/to/bible.db]

If no path is given, it looks for "bible.sqlite3" in the current directory.

Dependencies:
    pip install PySide6
"""

import re
import sys
import sqlite3
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QToolBar,
    QComboBox,
    QTextEdit,
    QMessageBox,
    QLabel,
    QLineEdit,
)
from PySide6.QtGui import QAction, QIcon, QFont


def quote_ident(name: str) -> str:
    """Safely quote a SQLite identifier (table/column name)."""
    return '"' + name.replace('"', '""') + '"'


def get_db_path():
    return Path(__file__).parent / "translations" / "bible.db"


class BibleViewer(QMainWindow):
    def __init__(self, db_path: str):
        super().__init__()
        self.setWindowTitle("Bible Viewer")
        self.resize(900, 700)

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        # Tracks whatever book/chapter the dropdowns last pointed at (via
        # manual selection or a resolved lookup), so a translation change
        # can try to restore the same spot instead of resetting to book 1.
        self._last_book: str | None = None
        self._last_chapter: str | None = None

        self._build_menu()
        self._build_toolbar()
        self._build_central()

        self._populate_translations()

    # ---------- UI construction ----------

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _build_toolbar(self):
        toolbar = QToolBar("Selection")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel(" Translation: "))
        self.translation_combo = QComboBox()
        self.translation_combo.currentIndexChanged.connect(
            self._on_translation_changed
        )
        toolbar.addWidget(self.translation_combo)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Book: "))
        self.book_combo = QComboBox()
        self.book_combo.currentIndexChanged.connect(self._on_book_changed)
        toolbar.addWidget(self.book_combo)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Chapter: "))
        self.chapter_combo = QComboBox()
        self.chapter_combo.currentIndexChanged.connect(
            self._on_chapter_changed
        )
        toolbar.addWidget(self.chapter_combo)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Lookup: "))
        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText("e.g. 1cor 13:4-7")
        self.reference_edit.setMinimumWidth(100)
        self.reference_edit.returnPressed.connect(self._on_reference_lookup)
        toolbar.addWidget(self.reference_edit)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Search: "))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search verse text...")
        self.search_edit.setMinimumWidth(100)
        self.search_edit.returnPressed.connect(self._on_search)
        toolbar.addWidget(self.search_edit)

    def _build_central(self):
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.text_view.setFont(QFont("Cascadia", 12))
        self.setCentralWidget(self.text_view)

    # ---------- data population ----------

    def _populate_translations(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        tables = [row["name"] for row in cur.fetchall()]

        # Only keep tables that actually look like translation tables.
        valid_tables = []
        for t in tables:
            cur.execute(f"PRAGMA table_info({quote_ident(t)})")
            cols = {r["name"] for r in cur.fetchall()}
            if {"book", "chapter", "verse", "text"}.issubset(cols):
                valid_tables.append(t)

        if not valid_tables:
            QMessageBox.critical(
                self,
                "No translations found",
                "No tables with book/chapter/verse/text columns were found "
                f"in {self.db_path}.",
            )
            return

        self.translation_combo.blockSignals(True)
        self.translation_combo.clear()
        for i, t in enumerate(valid_tables):
            self.translation_combo.addItem(t.upper(), userData=t)
            if t == "nrsvue":
                self.translation_combo.setCurrentIndex(i)
        self.translation_combo.blockSignals(False)

        self._on_translation_changed()

    def _select_combo_text(self, combo: QComboBox, text: str) -> bool:
        """Silently select the item in combo matching text, if present.

        Does not emit currentIndexChanged, so this can be used to sync
        dropdown state without triggering that combo's own data refresh.
        Returns True if a matching item was found and selected.
        """
        idx = combo.findText(text)
        if idx < 0:
            return False
        combo.blockSignals(True)
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        return True

    def _populate_book_combo(self, table: str) -> list[str]:
        """Fill book_combo with table's books, in canonical order.

        Blocks signals, so this never triggers _on_book_changed on its
        own -- callers decide what should happen after populating.
        """
        cur = self.conn.cursor()
        # Preserve canonical book order via minimum book_id rather than
        # sorting alphabetically.
        cur.execute(
            f"SELECT book, MIN(book_id) AS ord FROM {quote_ident(table)} "
            f"GROUP BY book ORDER BY ord"
        )
        books = [row["book"] for row in cur.fetchall()]

        self.book_combo.blockSignals(True)
        self.book_combo.clear()
        self.book_combo.addItems(books)
        self.book_combo.blockSignals(False)
        return books

    def _populate_chapter_combo(self, table: str, book: str) -> list[str]:
        """Fill chapter_combo with book's chapters in this table.

        Blocks signals, so this never triggers _on_chapter_changed on its
        own -- callers decide what should happen after populating.
        """
        cur = self.conn.cursor()
        cur.execute(
            f"SELECT DISTINCT chapter FROM {quote_ident(table)} "
            f"WHERE book = ? ORDER BY chapter",
            (book,),
        )
        chapters = [str(row["chapter"]) for row in cur.fetchall()]

        self.chapter_combo.blockSignals(True)
        self.chapter_combo.clear()
        self.chapter_combo.addItems(chapters)
        self.chapter_combo.blockSignals(False)
        return chapters

    def _sync_combos_to_reference(self, table: str, book: str, chapter: int):
        """Point the book/chapter dropdowns at a resolved reference.

        Used after a successful lookup so the dropdowns reflect what's on
        screen. Selection changes are made silently (no signals fired), so
        this never re-triggers a display refresh -- the lookup itself is
        already responsible for what's shown in text_view.
        """
        if not self._select_combo_text(self.book_combo, book):
            return
        self._populate_chapter_combo(table, book)
        self._select_combo_text(self.chapter_combo, str(chapter))
        self._last_book = book
        self._last_chapter = str(chapter)

    def _current_table(self):
        return self.translation_combo.currentData()

    def _on_translation_changed(self):
        table = self._current_table()
        if not table:
            return

        self._populate_book_combo(table)

        has_lookup = bool(self.reference_edit.text().strip())
        has_search = bool(self.search_edit.text().strip())

        if not has_lookup and not has_search and self._last_book is not None:
            # Try to stay on the same book (e.g. keep showing Exodus)
            # after switching translations, instead of resetting to the
            # first book.
            self._select_combo_text(self.book_combo, self._last_book)

        # Keep book/chapter mutually consistent up front. A lookup below
        # may resolve to a different book and repopulate this again.
        self._populate_chapter_combo(table, self.book_combo.currentText())

        if (
            not has_lookup
            and not has_search
            and self._last_chapter is not None
        ):
            self._select_combo_text(self.chapter_combo, self._last_chapter)

        if has_lookup:
            self._on_reference_lookup()
        elif has_search:
            self._on_search()
        else:
            self._on_chapter_changed()

    def _on_book_changed(self):
        table = self._current_table()
        book = self.book_combo.currentText()
        if not table or not book:
            return

        self._populate_chapter_combo(table, book)
        self._on_chapter_changed()

    def _on_chapter_changed(self):
        table = self._current_table()
        book = self.book_combo.currentText()
        chapter_text = self.chapter_combo.currentText()
        if not table or not book or not chapter_text:
            self.text_view.clear()
            return

        self._last_book = book
        self._last_chapter = chapter_text

        cur = self.conn.cursor()
        cur.execute(
            f"SELECT verse, text FROM {quote_ident(table)} "
            f"WHERE book = ? AND chapter = ? ORDER BY verse",
            (book, int(chapter_text)),
        )
        rows = cur.fetchall()

        lines = [
            f"<b>{book} {chapter_text}:{row['verse']}</b> {row['text']}<br>"
            for row in rows
        ]
        self.text_view.setHtml("\n".join(lines))

    def _on_search(self):
        table = self._current_table()
        term = self.search_edit.text().strip()
        if not table or not term:
            return

        cur = self.conn.cursor()
        cur.execute(
            f"SELECT book, chapter, verse, text FROM {quote_ident(table)} "
            f"WHERE text LIKE ? ORDER BY book_id, chapter, verse",
            (f"%{term}%",),
        )
        rows = cur.fetchall()

        if not rows:
            self.text_view.setPlainText(f"No results for \u201c{term}\u201d.")
            return

        bold_term = re.sub(
            re.escape(term),
            lambda m: f"<b>{m.group(0)}</b>",
            row["text"],
            flags=re.IGNORECASE,
        )

        lines = [
            f"<b>{row['book']} {row['chapter']}:{row['verse']}</b> {bold_term}<br>"
            for row in rows
        ]
        self.text_view.setHtml("\n".join(lines))

    # Matches: book [chapter[:start_verse[-end_verse]]]
    # "book" is a lazy free-form match so it can contain spaces or digits
    # (e.g. "1cor", "song of solomon"); the trailing chapter/verse portion
    # is only consumed if it looks like whitespace followed by digits.
    _REFERENCE_RE = re.compile(
        r"^\s*(?P<book>.+?)"
        r"(?:\s+(?P<chapter>\d+)(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?)?"
        r"\s*$"
    )

    def _parse_reference(self, ref: str):
        """Parse 'book [chapter[:start_verse[-end_verse]]]' into a tuple.

        Missing chapter defaults to 1. Missing start_verse means "no verse
        filter" (i.e. show the whole chapter) rather than defaulting to
        verse 1. An explicit start_verse with no end_verse means just that
        one verse. Returns None if ref does not match the expected shape.

        Returns (book, chapter, start_verse, end_verse) where start_verse
        and end_verse may be None to indicate "whole chapter".
        """
        match = self._REFERENCE_RE.match(ref)
        if not match or not match.group("book"):
            return None

        book = match.group("book").strip()
        chapter = int(match.group("chapter")) if match.group("chapter") else 1
        start_verse = (
            int(match.group("start")) if match.group("start") else None
        )
        if start_verse is None:
            end_verse = None
        else:
            end_verse = (
                int(match.group("end")) if match.group("end") else start_verse
            )
        return book, chapter, start_verse, end_verse

    def _on_reference_lookup(self):
        table = self._current_table()
        raw_ref = self.reference_edit.text().strip()
        if not table or not raw_ref:
            return

        parsed = self._parse_reference(raw_ref)
        if not parsed:
            self.text_view.setPlainText(
                f"Could not parse reference \u201c{raw_ref}\u201d."
            )
            return

        book_input, chapter, start_verse, end_verse = parsed
        normalized_input = book_input.lower().replace(" ", "")

        cur = self.conn.cursor()

        # Book is matched by comparing the input (lowercased, spaces
        # stripped) as a prefix against the DB's book field, similarly
        # normalized, e.g. "1cor" matches "1 Corinthians".
        cur.execute(
            f"SELECT DISTINCT book, book_id FROM {quote_ident(table)} "
            f"WHERE LOWER(REPLACE(book, ' ', '')) LIKE ? "
            f"ORDER BY book_id",
            (f"{normalized_input}%",),
        )
        matches = cur.fetchall()
        distinct_books = list(dict.fromkeys(row["book"] for row in matches))

        if not distinct_books:
            self.text_view.setPlainText(
                f"No book matches \u201c{book_input}\u201d."
            )
            return
        if len(distinct_books) > 1:
            self.text_view.setPlainText(
                f"\u201c{book_input}\u201d is ambiguous, matches: "
                + ", ".join(distinct_books)
            )
            return

        book = distinct_books[0]

        # Point the dropdowns at this book/chapter now that it's resolved.
        # Runs whether this was triggered by a translation change or the
        # user pressing Enter directly in the Lookup box, so the dropdowns
        # always reflect what's actually on screen.
        self._sync_combos_to_reference(table, book, chapter)

        if start_verse is None:
            # No verse given at all: whole chapter.
            cur.execute(
                f"SELECT book, chapter, verse, text FROM {quote_ident(table)} "
                f"WHERE book = ? AND chapter = ? "
                f"ORDER BY verse",
                (book, chapter),
            )
        else:
            # Single verse (end_verse == start_verse) or an explicit range.
            cur.execute(
                f"SELECT book, chapter, verse, text FROM {quote_ident(table)} "
                f"WHERE book = ? AND chapter = ? AND verse BETWEEN ? AND ? "
                f"ORDER BY verse",
                (book, chapter, start_verse, end_verse),
            )
        rows = cur.fetchall()

        if not rows:
            if start_verse is None:
                ref_desc = f"{book} {chapter}"
            elif end_verse != start_verse:
                ref_desc = f"{book} {chapter}:{start_verse}-{end_verse}"
            else:
                ref_desc = f"{book} {chapter}:{start_verse}"
            self.text_view.setPlainText(f"No verses found for {ref_desc}")
            return

        lines = [
            f"<b>{row['book']} {row['chapter']}:{row['verse']}</b> {row['text']}<br>"
            for row in rows
        ]
        self.text_view.setHtml("\n".join(lines))

    def closeEvent(self, event):
        self.conn.close()
        super().closeEvent(event)


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else get_db_path()

    if not Path(db_path).is_file():
        app = QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "Database not found",
            f"Could not find database file: {db_path}\n\n"
            "Usage: python bible_viewer.py [path/to/bible.sqlite3]",
        )
        sys.exit(1)

    app = QApplication(sys.argv)
    window = BibleViewer(db_path)
    icon = QIcon()
    icon.addFile(str(Path(__file__).parent / "resources" / "bible.png"))
    window.setWindowIcon(icon)
    window.show()
    window.reference_edit.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
