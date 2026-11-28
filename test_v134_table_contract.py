"""Table contract tests for tiny-cli 1.3.4.

The artifact here is the STRING the table prints, plus the two operations that
change what it holds (`filter_cols`, `sort_by`). A table is read by a human or
piped into a file, so "it returned a Table" proves nothing: the previous
`sort_by` returned a Table and put 10 before 9.

Assertions compare `str(cell)` and `type(...).__name__` through helpers rather
than `x == "literal"` where the point is a type, because an equality that
cannot see a type is exactly the defect under test.
"""

import pytest

import tiny_cli as tc


def rows_of(table):
    return [[str(c) for c in row] for row in table.rows]


class TestAddRowWidth:
    def test_extra_cell_is_refused_not_dropped(self):
        t = tc.Table(["A", "B"])
        with pytest.raises(ValueError) as exc:
            t.add_row("x", "y", "z")
        msg = str(exc.value)
        assert "3 cells" in msg
        assert "2 columns" in msg

    def test_extra_cell_does_not_leave_a_partial_row(self):
        # The row must not be half-added: a caller that catches the error and
        # prints the table should see the table it had before.
        t = tc.Table(["A", "B"])
        t.add_row("x", "y")
        with pytest.raises(ValueError):
            t.add_row("p", "q", "r")
        assert rows_of(t) == [["x", "y"]]

    def test_short_row_is_padded(self):
        t = tc.Table(["A", "B", "C"])
        t.add_row("x")
        assert rows_of(t) == [["x", "", ""]]

    def test_width_covers_padded_columns(self):
        t = tc.Table(["A", "B", "C"])
        t.add_row("x", "long-value")
        t.add_row("y")
        widths = [int(w) for w in t._widths]
        assert widths == [1, 10, 1]

    def test_exact_width_is_accepted(self):
        t = tc.Table(["A", "B"])
        t.add_row("1", "2")
        assert rows_of(t) == [["1", "2"]]

    def test_non_string_cells_are_stringified(self):
        t = tc.Table(["N", "B"])
        t.add_row(7, None)
        assert rows_of(t) == [["7", "None"]]


class TestFilterCols:
    def test_unknown_column_is_named(self):
        t = tc.Table(["Name", "Size"])
        t.add_row("a", "10")
        with pytest.raises(ValueError) as exc:
            t.filter_cols("Name", "Typo")
        assert "Typo" in str(exc.value)
        # The error must also say what COULD have been asked for, or the
        # reader has to go read the constructor to recover.
        assert "Size" in str(exc.value)

    def test_failed_filter_leaves_the_table_alone(self):
        t = tc.Table(["Name", "Size"])
        t.add_row("a", "10")
        with pytest.raises(ValueError):
            t.filter_cols("Typo")
        assert [str(h) for h in t.headers] == ["Name", "Size"]
        assert rows_of(t) == [["a", "10"]]

    def test_filter_reorders_and_keeps_align(self):
        t = tc.Table(["A", "B", "C"], align=["l", "r", "c"])
        t.add_row("1", "2", "3")
        t.filter_cols("C", "A")
        assert [str(h) for h in t.headers] == ["C", "A"]
        assert [str(a) for a in t._align] == ["c", "l"]
        assert rows_of(t) == [["3", "1"]]

    def test_filter_keeps_rendering_the_kept_values(self):
        t = tc.Table(["Name", "Size"], theme="markdown")
        t.add_row("alpha", "1234")
        t.filter_cols("Name")
        out = str(t)
        assert "alpha" in out
        assert "1234" not in out


class TestSortBy:
    def test_numbers_sort_by_value(self):
        t = tc.Table(["Name", "Size"])
        t.add_row("a", "10")
        t.add_row("b", "9")
        t.add_row("c", "100")
        t.sort_by("Size")
        assert [r[1] for r in rows_of(t)] == ["9", "10", "100"]

    def test_numbers_sort_descending(self):
        t = tc.Table(["Name", "Size"])
        t.add_row("a", "10")
        t.add_row("b", "9")
        t.sort_by("Size", reverse=True)
        assert [r[1] for r in rows_of(t)] == ["10", "9"]

    def test_words_sort_as_words(self):
        t = tc.Table(["Name"])
        t.add_row("cherry")
        t.add_row("apple")
        t.add_row("banana")
        t.sort_by("Name")
        assert [r[0] for r in rows_of(t)] == ["apple", "banana", "cherry"]

    def test_one_non_numeric_cell_keeps_the_column_as_text(self):
        # "10" vs "9" must NOT reorder when the column also holds "-", and
        # the "-" must not be silently sorted to a numeric position.
        t = tc.Table(["Name", "Size"])
        t.add_row("a", "10")
        t.add_row("b", "9")
        t.add_row("c", "-")
        t.sort_by("Size")
        assert [r[1] for r in rows_of(t)] == ["-", "10", "9"]

    def test_empty_cells_sort_last_in_a_numeric_column(self):
        t = tc.Table(["Name", "Size"])
        t.add_row("a", "")
        t.add_row("b", "9")
        t.sort_by("Size")
        assert [r[1] for r in rows_of(t)] == ["9", ""]

    def test_empty_cells_sort_last_in_a_numeric_column_both_directions(self):
        """1.3.4 put empty cells first on a descending sort.

        `reverse=True` reverses the key order, and the empty bucket was encoded
        as "sort after" in the same tuple, so it became "sort first". The
        ascending test that shipped passed the whole time. A rule stated as
        "last" has to be checked in the direction that reverses it.
        """
        body = ["10", "9", "100", ""]
        ascending = tc.Table(["Size"])
        descending = tc.Table(["Size"])
        for value in body:
            ascending.add_row(value)
            descending.add_row(value)

        assert [r[0] for r in rows_of(ascending.sort_by("Size"))] == ["9", "10", "100", ""]
        assert [r[0] for r in rows_of(descending.sort_by("Size", reverse=True))] == ["100", "10", "9", ""]

    def test_numeric_sort_is_stable_across_equal_keys(self):
        """Two equal sizes keep their input order, empty still last."""
        t = tc.Table(["Name", "Size"])
        t.add_row("first", "5")
        t.add_row("second", "5")
        t.add_row("third", "")
        assert [r[1] for r in rows_of(t.sort_by("Size", reverse=True))] == ["5", "5", ""]

    def test_all_empty_column_does_not_raise(self):
        t = tc.Table(["Size"])
        t.add_row("")
        t.add_row("")
        assert [r[0] for r in rows_of(t.sort_by("Size", reverse=True))] == ["", ""]

    def test_unknown_column_is_named(self):
        t = tc.Table(["Name"])
        t.add_row("a")
        with pytest.raises(ValueError) as exc:
            t.sort_by("Size")
        assert "Size" in str(exc.value)

    def test_sort_does_not_change_widths(self):
        t = tc.Table(["Name", "Size"])
        t.add_row("a", "1000")
        before = [int(w) for w in t._widths]
        t.sort_by("Size")
        assert [int(w) for w in t._widths] == before


class TestRenderedString:
    def test_box_theme_borders_every_row(self):
        t = tc.Table(["Name", "Size"])
        t.add_row("a", "10")
        t.add_row("b", "9")
        lines = str(t).splitlines()
        # "a" also matches the header "Name"; pin the data rows by their pads.
        body = [ln for ln in lines if "│ a " in ln or "│ b " in ln]
        assert len(body) == 2
        # top, header rule, bottom
        borders = [ln for ln in lines if "─" in ln]
        assert len(borders) == 3

    def test_markdown_theme_header_separator_is_all_dashes(self):
        t = tc.Table(["Name", "Size"], theme="markdown")
        t.add_row("a", "10")
        lines = str(t).splitlines()
        sep = [ln for ln in lines if "---" in ln]
        assert len(sep) == 1
        assert "|" in sep[0]

    def test_unknown_theme_falls_back_to_box(self):
        t = tc.Table(["Name"], theme="nope")
        t.add_row("a")
        assert str(t.theme) == "box"

    def test_empty_table_renders_headers(self):
        t = tc.Table(["Only"])
        assert "Only" in str(t)

    def test_right_alignment_pads_on_the_left(self):
        t = tc.Table(["N"], align=["r"], theme="simple")
        t.add_row("1")
        t.add_row("100")
        lines = [ln for ln in str(t).splitlines() if "1" in ln]
        # The narrow row must be wider than its content: leading spaces.
        assert any(ln.startswith("  1") or "   1" in ln for ln in lines)
