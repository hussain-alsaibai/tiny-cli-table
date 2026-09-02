"""Comprehensive test suite for tiny_table.

Run with::

    python -m unittest test_tiny_table.py
    # or
    pytest test_tiny_table.py
"""

import dataclasses
import io
import unittest
from collections import namedtuple

import tiny_table as ttab
from tiny_table import Table, TinyTableError, SPAN, enable_color, bold, color


# Helper: always turn off color during tests so output is deterministic.
def setUpModule() -> None:  # pragma: no cover - trivial
    enable_color(False)


class TestColorHelpers(unittest.TestCase):
    def test_bold_off(self) -> None:
        enable_color(False)
        self.assertEqual(bold("hi"), "hi")

    def test_bold_on(self) -> None:
        enable_color(True)
        try:
            self.assertIn("\x1b[", bold("hi"))
            self.assertIn("hi", bold("hi"))
        finally:
            enable_color(False)

    def test_color_default_code(self) -> None:
        enable_color(True)
        try:
            out = color("x")
            self.assertIn("36", out)
        finally:
            enable_color(False)

    def test_color_custom_code(self) -> None:
        enable_color(True)
        try:
            out = color("x", code="31")
            self.assertIn("31", out)
        finally:
            enable_color(False)


class TestSpan(unittest.TestCase):
    def test_singleton(self) -> None:
        self.assertIs(SPAN, SPAN)
        self.assertIs(SPAN, ttab.SPAN)
        self.assertIs(Table.SPAN, SPAN)
        self.assertEqual(repr(SPAN), "SPAN")


class TestRowNormalization(unittest.TestCase):
    def test_list(self) -> None:
        values, cols = ttab._normalize_row([1, 2, 3], None)
        self.assertEqual(values, [1, 2, 3])
        self.assertIsNone(cols)

    def test_dict(self) -> None:
        values, cols = ttab._normalize_row({"a": 1, "b": 2}, None)
        self.assertEqual(cols, ["a", "b"])
        self.assertEqual(values, [1, 2])

    def test_dict_with_columns(self) -> None:
        values, cols = ttab._normalize_row({"a": 1, "b": 2}, ["b", "a"])
        self.assertEqual(cols, ["b", "a"])
        self.assertEqual(values, [2, 1])

    def test_dataclass(self) -> None:
        @dataclasses.dataclass
        class P:
            name: str
            age: int

        values, cols = ttab._normalize_row(P("Alice", 30), None)
        self.assertEqual(cols, ["name", "age"])
        self.assertEqual(values, ["Alice", 30])

    def test_namedtuple(self) -> None:
        P = namedtuple("P", ["name", "age"])
        values, cols = ttab._normalize_row(P("Alice", 30), None)
        self.assertEqual(cols, ["name", "age"])
        self.assertEqual(values, ["Alice", 30])

    def test_none_raises(self) -> None:
        with self.assertRaises(TinyTableError):
            ttab._normalize_row(None, None)

    def test_unsupported_raises(self) -> None:
        with self.assertRaises(TinyTableError):
            ttab._normalize_row(42, None)


class TestDisplayWidthAndTruncate(unittest.TestCase):
    def test_display_width_plain(self) -> None:
        self.assertEqual(ttab._display_width("hello"), 5)

    def test_display_width_ansi(self) -> None:
        enable_color(False)
        self.assertEqual(ttab._display_width("\x1b[31mhi\x1b[0m"), 2)

    def test_truncate_short(self) -> None:
        self.assertEqual(ttab._truncate("hi", 10), "hi")

    def test_truncate_long(self) -> None:
        out = ttab._truncate("hello world", 5)
        self.assertEqual(ttab._display_width(out), 5)
        self.assertTrue(out.endswith("…"))

    def test_pad_left(self) -> None:
        self.assertEqual(ttab._pad("x", 4, "left"), "x   ")

    def test_pad_right(self) -> None:
        self.assertEqual(ttab._pad("x", 4, "right"), "   x")

    def test_pad_center(self) -> None:
        self.assertEqual(ttab._pad("x", 5, "center"), "  x  ")


class TestTableInit(unittest.TestCase):
    def test_basic(self) -> None:
        t = Table(headers=["a", "b"], rows=[[1, 2]])
        self.assertEqual(t.headers, ["a", "b"])
        self.assertEqual(len(t._rows), 1)

    def test_invalid_style(self) -> None:
        with self.assertRaises(TinyTableError):
            Table(style="bogus")

    def test_invalid_align(self) -> None:
        with self.assertRaises(TinyTableError):
            Table(align="middle")

    def test_inferred_columns_from_first_row(self) -> None:
        t = Table(rows=[{"x": 1, "y": 2}])
        self.assertEqual(t.headers, ["x", "y"])

    def test_repr(self) -> None:
        t = Table(headers=["a"], rows=[["x"]])
        self.assertIn("Table", repr(t))


class TestColumns(unittest.TestCase):
    def test_add_column(self) -> None:
        t = Table()
        t.add_column("a")
        t.add_column("b", align="right", width=5, color="31")
        self.assertEqual(len(t.headers), 2)
        self.assertEqual(t._columns[1].align, "right")
        self.assertEqual(t._columns[1].width, 5)
        self.assertEqual(t._columns[1].color, "31")

    def test_add_column_invalid_align(self) -> None:
        t = Table()
        with self.assertRaises(TinyTableError):
            t.add_column("a", align="bogus")

    def test_set_column_style(self) -> None:
        t = Table(headers=["a"])
        t.set_column_style("a", align="center", width=10)
        self.assertEqual(t._columns[0].align, "center")
        self.assertEqual(t._columns[0].width, 10)

    def test_set_column_style_missing(self) -> None:
        t = Table(headers=["a"])
        with self.assertRaises(TinyTableError):
            t.set_column_style("missing")

    def test_set_column_style_invalid_align(self) -> None:
        t = Table(headers=["a"])
        with self.assertRaises(TinyTableError):
            t.set_column_style("a", align="bogus")


class TestAddRow(unittest.TestCase):
    def test_add_row_pads_short(self) -> None:
        t = Table(headers=["a", "b", "c"])
        t.add_row([1])
        self.assertEqual(t._rows[0][1], "")
        self.assertEqual(t._rows[0][2], "")

    def test_add_row_truncates_long(self) -> None:
        t = Table(headers=["a", "b"])
        t.add_row([1, 2, 3])
        self.assertEqual(len(t._rows[0]), 2)

    def test_add_row_dict(self) -> None:
        t = Table()
        t.add_row({"a": 1, "b": 2})
        self.assertEqual(t.headers, ["a", "b"])

    def test_add_row_dataclass(self) -> None:
        @dataclasses.dataclass
        class P:
            name: str
            age: int

        t = Table()
        t.add_row(P("alice", 30))
        self.assertEqual(t.headers, ["name", "age"])

    def test_add_row_dataclass_missing_field(self) -> None:
        @dataclasses.dataclass
        class P:
            name: str

        t = Table(headers=["name", "age"])
        with self.assertRaises(TinyTableError):
            t.add_row(P("alice"))


class TestSorting(unittest.TestCase):
    def test_sort_method(self) -> None:
        t = Table(headers=["n"], rows=[["10"], ["2"], ["1"]])
        t.sort("n")
        self.assertEqual([r[0] for r in t._rows], ["1", "2", "10"])

    def test_sort_descending(self) -> None:
        t = Table(headers=["n"], rows=[["10"], ["2"], ["1"]])
        t.sort("n", descending=True)
        self.assertEqual([r[0] for r in t._rows], ["10", "2", "1"])

    def test_sort_by_constructor(self) -> None:
        t = Table(headers=["n"], rows=[["10"], ["2"], ["1"]], sort_by="n")
        rendered = t.render()
        # After sort: 1, 2, 10
        self.assertLess(rendered.find("1"), rendered.find("2"))
        self.assertLess(rendered.find("2"), rendered.find("10"))

    def test_sort_missing_column(self) -> None:
        t = Table(headers=["a"])
        with self.assertRaises(TinyTableError):
            t.sort("missing")


class TestAllStyles(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Table(headers=["A", "B"], rows=[["1", "2"], ["3", "4"]])

    def test_fancy(self) -> None:
        self.t.style = "fancy"
        out = self.t.render()
        self.assertIn("╭", out)
        self.assertIn("╰", out)
        self.assertIn("│", out)

    def test_classic(self) -> None:
        self.t.style = "classic"
        out = self.t.render()
        self.assertIn("+", out)
        self.assertIn("|", out)
        self.assertIn("-", out)

    def test_double(self) -> None:
        self.t.style = "double"
        out = self.t.render()
        self.assertIn("╔", out)
        self.assertIn("║", out)

    def test_rounded(self) -> None:
        self.t.style = "rounded"
        out = self.t.render()
        self.assertIn("╭", out)

    def test_compact(self) -> None:
        self.t.style = "compact"
        out = self.t.render()
        self.assertNotIn("╭", out)

    def test_grid(self) -> None:
        self.t.style = "grid"
        out = self.t.render()
        self.assertIn("+", out)

    def test_simple(self) -> None:
        self.t.style = "simple"
        out = self.t.render()
        # simple has no corner chars
        self.assertNotIn("╭", out)
        self.assertNotIn("+", out)

    def test_markdown(self) -> None:
        self.t.style = "markdown"
        out = self.t.render()
        self.assertIn("|", out)
        self.assertIn("-", out)
        # No fancy chars in markdown
        self.assertNotIn("╭", out)


class TestAlignment(unittest.TestCase):
    def test_right_align(self) -> None:
        t = Table(headers=["x"], rows=[["1"]], align="right")
        self.assertIn(" 1", t.render())

    def test_center_align(self) -> None:
        t = Table(headers=["x"], rows=[["1"]], align="center")
        out = t.render()
        # '   1   ' with padding
        self.assertIn("1", out)

    def test_per_column_align(self) -> None:
        t = Table(headers=["a", "b"], rows=[["1", "2"]])
        t.set_column_style("a", align="right")
        t.set_column_style("b", align="center")
        self.assertEqual(t._columns[0].align, "right")
        self.assertEqual(t._columns[1].align, "center")
        t.render()  # should not raise


class TestWidths(unittest.TestCase):
    def test_auto_width(self) -> None:
        t = Table(headers=["a"], rows=[["really long value"]])
        widths = t._compute_widths()
        self.assertGreaterEqual(widths[0], len("really long value"))

    def test_fixed_column_width(self) -> None:
        t = Table(headers=["a"], rows=[["hi"]])
        t.set_column_style("a", width=20)
        widths = t._compute_widths()
        self.assertEqual(widths[0], 20)

    def test_max_width_truncates(self) -> None:
        t = Table(headers=["a"], rows=[["a really long string"]], max_width=5)
        widths = t._compute_widths()
        self.assertEqual(widths[0], 5)

    def test_total_width_fits(self) -> None:
        t = Table(headers=["a", "b"], rows=[["hi", "world"]], width=20)
        out = t.render()
        for line in out.splitlines():
            self.assertLessEqual(len(line), 25)  # generous bound

    def test_zero_width(self) -> None:
        t = Table(headers=["a", "b"], rows=[["hi", "world"]])
        widths = t._compute_widths()
        self.assertEqual(len(widths), 2)


class TestColors(unittest.TestCase):
    def test_header_color(self) -> None:
        enable_color(True)
        try:
            t = Table(headers=["a"], rows=[["b"]], header_style="1;31")
            out = t.render()
            self.assertIn("\x1b[", out)
        finally:
            enable_color(False)

    def test_disable_header_color(self) -> None:
        enable_color(True)
        try:
            t = Table(headers=["a"], rows=[["b"]], header_style=None)
            # Header cell should have no ANSI codes
            self.assertNotIn("\x1b[", t._render_box().splitlines()[1])
        finally:
            enable_color(False)

    def test_row_color_callback(self) -> None:
        enable_color(True)
        try:
            t = Table(
                headers=["x"],
                rows=[["a"], ["b"], ["c"]],
                row_colors=None,
                row_color=lambda i, r: "31" if i == 1 else None,
            )
            out = t.render()
            # The middle row should have an ANSI code
            self.assertIn("31", out)
        finally:
            enable_color(False)

    def test_row_color_callback_exception(self) -> None:
        def bad_cb(i, r):
            raise RuntimeError("oops")

        t = Table(headers=["x"], rows=[["a"]], row_colors=None, row_color=bad_cb)
        # Should not raise
        t.render()

    def test_column_color(self) -> None:
        enable_color(True)
        try:
            t = Table(headers=["a", "b"], rows=[["x", "y"]])
            t.set_column_style("a", color="32")
            out = t.render()
            self.assertIn("32", out)
        finally:
            enable_color(False)

    def test_alternating_row_colors(self) -> None:
        enable_color(True)
        try:
            t = Table(
                headers=["a"],
                rows=[["x"], ["y"]],
                row_colors=("", "90"),
            )
            out = t.render()
            # The stripe color is 90
            self.assertIn("90", out)
        finally:
            enable_color(False)


class TestColumnSpanning(unittest.TestCase):
    def test_basic_span(self) -> None:
        t = Table(headers=["A", "B", "C"], rows=[["1", "2", "3"], ["merged", SPAN, "tail"]])
        out = t.render()
        self.assertIn("merged", out)
        self.assertIn("tail", out)

    def test_full_row_span(self) -> None:
        t = Table(headers=["A", "B", "C"], rows=[["1", "2", "3"], ["all", SPAN, SPAN]])
        out = t.render()
        self.assertIn("all", out)
        # Top border still drawn even when row is fully spanned
        self.assertTrue(out.startswith("╭") or out.startswith("+") or out.startswith(" "))

    def test_table_class_span(self) -> None:
        t = Table(headers=["A", "B", "C"], rows=[["1", "2", "3"], ["x", Table.SPAN, "y"]])
        self.assertIn("y", t.render())


class TestNestedTables(unittest.TestCase):
    def test_nested_table_renders(self) -> None:
        inner = Table(headers=["k", "v"], rows=[["a", "1"], ["b", "2"]], style="compact")
        outer = Table(headers=["Section", "Detail"], rows=[["A", "simple"], ["Nested", inner]])
        out = outer.render()
        self.assertIn("Section", out)
        self.assertIn("Detail", out)
        # Inner table should appear inside
        self.assertIn("a", out)
        self.assertIn("1", out)


class TestStringify(unittest.TestCase):
    def test_none(self) -> None:
        self.assertEqual(ttab._stringify(None), None)

    def test_bool_true(self) -> None:
        self.assertEqual(ttab._stringify(True), "✓")

    def test_bool_false(self) -> None:
        self.assertEqual(ttab._stringify(False), "✗")

    def test_int(self) -> None:
        self.assertEqual(ttab._stringify(42), "42")

    def test_float_intlike(self) -> None:
        self.assertEqual(ttab._stringify(3.0), "3")

    def test_float(self) -> None:
        self.assertEqual(ttab._stringify(3.14), "3.14")

    def test_list(self) -> None:
        self.assertEqual(ttab._stringify([1, 2, 3]), "1, 2, 3")

    def test_table(self) -> None:
        t = Table(headers=["a"], rows=[["b"]])
        out = ttab._stringify(t)
        self.assertIn("a", out)
        self.assertIn("b", out)


class TestNaturalKey(unittest.TestCase):
    def test_numbers_before_strings(self) -> None:
        self.assertLess(ttab._natural_key("10"), ttab._natural_key("a"))

    def test_numeric_sort(self) -> None:
        keys = [ttab._natural_key(x) for x in ["1", "10", "2"]]
        self.assertEqual(sorted(keys), [ttab._natural_key("1"), ttab._natural_key("2"), ttab._natural_key("10")])

    def test_none(self) -> None:
        self.assertEqual(ttab._natural_key(None), (2, ""))


class TestStringOutput(unittest.TestCase):
    def test_str_returns_render(self) -> None:
        t = Table(headers=["a"], rows=[["b"]])
        self.assertEqual(str(t), t.render())

    def test_to_string(self) -> None:
        t = Table(headers=["a"], rows=[["b"]])
        self.assertEqual(t.to_string(), t.render())

    def test_print(self) -> None:
        import sys
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            Table(headers=["a"], rows=[["b"]]).print()
        finally:
            sys.stdout = old
        self.assertIn("a", buf.getvalue())
        self.assertIn("b", buf.getvalue())


class TestIterables(unittest.TestCase):
    def test_dict_rows(self) -> None:
        rows = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        t = Table(rows=rows, style="classic")
        out = t.render()
        self.assertIn("Alice", out)
        self.assertIn("Bob", out)

    def test_dataclass_rows(self) -> None:
        @dataclasses.dataclass
        class P:
            name: str
            age: int

        rows = [P("Alice", 30), P("Bob", 25)]
        t = Table(rows=rows, style="classic")
        out = t.render()
        self.assertIn("Alice", out)
        self.assertIn("Bob", out)

    def test_namedtuple_rows(self) -> None:
        P = namedtuple("P", ["name", "age"])
        rows = [P("Alice", 30), P("Bob", 25)]
        t = Table(rows=rows, style="classic")
        out = t.render()
        self.assertIn("Alice", out)
        self.assertIn("Bob", out)

    def test_mixed_rows(self) -> None:
        t = Table(headers=["a", "b"])
        t.add_row([1, 2])
        t.add_row({"a": 3, "b": 4})
        self.assertEqual(len(t._rows), 2)

    def test_bool_rendering(self) -> None:
        t = Table(headers=["name", "ok"], rows=[["x", True], ["y", False]])
        out = t.render()
        self.assertIn("✓", out)
        self.assertIn("✗", out)


class TestEdgeCases(unittest.TestCase):
    def test_empty_table(self) -> None:
        t = Table(headers=["a", "b"])
        out = t.render()
        # Should still produce a valid header-only table
        self.assertIn("a", out)
        self.assertIn("b", out)

    def test_single_row(self) -> None:
        t = Table(headers=["a", "b"], rows=[["1", "2"]])
        self.assertIn("1", t.render())
        self.assertIn("2", t.render())

    def test_single_column(self) -> None:
        t = Table(headers=["only"], rows=[["x"], ["y"], ["z"]])
        out = t.render()
        self.assertIn("x", out)
        self.assertIn("y", out)
        self.assertIn("z", out)

    def test_unicode_values(self) -> None:
        t = Table(headers=["emoji"], rows=[["🎉"], ["🚀"]])
        out = t.render()
        self.assertIn("🎉", out)
        self.assertIn("🚀", out)

    def test_multiline_cells(self) -> None:
        # Multiline cells: should not crash; uses widest line for width
        t = Table(headers=["x"], rows=[["line1\nline two"]])
        widths = t._compute_widths()
        self.assertGreaterEqual(widths[0], len("line two"))


class TestInteractiveMode(unittest.TestCase):
    """Verify the ``sort_by`` constructor flag gives render-time sorting."""

    def test_sort_by_renders_sorted(self) -> None:
        t = Table(headers=["name", "score"], rows=[
            ["Bob", "10"],
            ["Alice", "30"],
            ["Carol", "20"],
        ], sort_by="score")
        out = t.render()
        # Numeric ascending: 10, 20, 30 → Bob, Carol, Alice
        bob_pos = out.find("Bob")
        carol_pos = out.find("Carol")
        alice_pos = out.find("Alice")
        self.assertLess(bob_pos, carol_pos)
        self.assertLess(carol_pos, alice_pos)

    def test_sort_desc(self) -> None:
        t = Table(headers=["name", "score"], rows=[
            ["Bob", "10"],
            ["Alice", "30"],
            ["Carol", "20"],
        ], sort_by="score", sort_desc=True)
        out = t.render()
        # Numeric descending: 30, 20, 10 → Alice, Carol, Bob
        alice_pos = out.find("Alice")
        carol_pos = out.find("Carol")
        bob_pos = out.find("Bob")
        self.assertLess(alice_pos, carol_pos)
        self.assertLess(carol_pos, bob_pos)


if __name__ == "__main__":
    unittest.main(verbosity=2)
