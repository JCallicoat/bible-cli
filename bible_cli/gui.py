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

from .bible_common import (
    DEFAULT_TRANSLATION,
    bold_term,
    extract_filters,
    get_translations,
    list_books,
    list_chapters,
    lookup_verses,
    parse_reference,
    resolve_book,
    resolve_translation,
    search_verses,
    build_verse_query,
)


def get_icon_path():
    return str(Path(__file__).parent / "resources" / "bible.png")


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
        self.reference_edit.setPlaceholderText(
            "e.g. 1cor 13:4-7, or 1cor 1:1 t:all"
        )
        self.reference_edit.setMinimumWidth(100)
        self.reference_edit.returnPressed.connect(self._on_reference_lookup)
        toolbar.addWidget(self.reference_edit)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Search: "))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Search verse text... e.g. love b:john t:all"
        )
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
        valid_tables = get_translations(self.conn)

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
            if t == DEFAULT_TRANSLATION:
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
        books = list_books(self.conn, table)

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
        chapters = list_chapters(self.conn, table, book)

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

        query, params = build_verse_query(
            table, book, int(chapter_text), None, None
        )
        cur = self.conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()

        lines = [
            f"<b>{book} {chapter_text}:{row[0]}</b> {row[1]}<br>"
            for row in rows
        ]
        self.text_view.setHtml("\n".join(lines))

    def _on_search(self):
        table = self._current_table()
        raw_input = self.search_edit.text().strip()
        if not table or not raw_input:
            return

        filters = extract_filters(raw_input)
        term = filters.remainder
        if not term:
            self.text_view.setPlainText(
                "Enter search text in addition to the filter(s)."
            )
            return

        if filters.translation_all:
            tables = get_translations(self.conn)
        elif filters.translation:
            resolved, error = resolve_translation(
                get_translations(self.conn), filters.translation
            )
            if error:
                self.text_view.setPlainText(error)
                return
            tables = [resolved]
        else:
            tables = [table]

        rows, errors = search_verses(self.conn, tables, term, filters.book)

        if not rows:
            desc = f"\u201c{term}\u201d" + (
                f" in {filters.book}" if filters.book else ""
            )
            self.text_view.setPlainText(
                errors[0] if errors else f"No results for {desc}."
            )
            return

        multi = filters.translation_all
        lines = []
        last_trans = None
        for i, row in enumerate(rows):
            if last_trans != row.translation:
                last_trans = row.translation
                if i > 0:
                    lines.append("<br>")
            prefix = f"{row.translation.upper()} " if multi else ""
            lines.append(
                f"<b>{prefix}{row.book} {row.chapter}:{row.verse}</b> "
                f"{bold_term(term, row.text)}<br>"
            )
        self.text_view.setHtml("\n".join(lines))

    def _on_reference_lookup(self):
        table = self._current_table()
        raw_ref = self.reference_edit.text().strip()
        if not table or not raw_ref:
            return

        raw_ref = raw_ref.replace("\u2013", "-").replace("\u2014", "-")
        filters = extract_filters(raw_ref)

        parsed = parse_reference(filters.remainder)
        if not parsed:
            self.text_view.setPlainText(
                f"Could not parse reference \u201c{raw_ref}\u201d."
            )
            return

        book_input = filters.book or parsed.book
        explicit_translation = None

        if filters.translation_all:
            tables = get_translations(self.conn)
        elif filters.translation:
            resolved, error = resolve_translation(
                get_translations(self.conn), filters.translation
            )
            if error:
                self.text_view.setPlainText(error)
                return
            explicit_translation = resolved
            tables = [resolved]
        else:
            tables = [table]

        # For a single translation, resolve the book and sync the dropdowns
        # up front (as before) so they reflect what's on screen even if the
        # specific verse range below has no matches. "t:all" intentionally
        # skips this -- per spec, none of the dropdowns update for that mode.
        if not filters.translation_all:
            resolved_book, error = resolve_book(
                self.conn, tables[0], book_input
            )
            if error:
                self.text_view.setPlainText(error)
                return
            if explicit_translation:
                self._select_combo_text(
                    self.translation_combo, explicit_translation.upper()
                )
            self._sync_combos_to_reference(
                tables[0], resolved_book, parsed.chapter
            )
            book_input = resolved_book

        rows, errors = lookup_verses(
            self.conn,
            tables,
            book_input,
            parsed.chapter,
            parsed.start_verse,
            parsed.end_verse,
        )

        if not rows:
            if parsed.start_verse is None:
                ref_desc = f"{book_input} {parsed.chapter}"
            elif parsed.end_verse != parsed.start_verse:
                ref_desc = f"{book_input} {parsed.chapter}:{parsed.start_verse}-{parsed.end_verse}"
            else:
                ref_desc = (
                    f"{book_input} {parsed.chapter}:{parsed.start_verse}"
                )
            self.text_view.setPlainText(
                errors[0] if errors else f"No verses found for {ref_desc}"
            )
            return

        multi = filters.translation_all
        lines = []
        last_trans = None
        for i, row in enumerate(rows):
            if last_trans != row.translation:
                last_trans = row.translation
                if i > 0:
                    lines.append("<br>")
            prefix = f"{row.translation.upper()} " if multi else ""
            lines.append(
                f"<b>{prefix}{row.book} {row.chapter}:{row.verse}</b> {row.text}<br>"
            )
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
    icon.addFile(get_icon_path())
    window.setWindowIcon(icon)
    window.show()
    window.reference_edit.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
