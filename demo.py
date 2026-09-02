"""Interactive demo for tiny_table.

Run::

    python3 demo.py            # ANSI colors disabled
    FORCE_COLOR=1 python3 demo.py   # ANSI colors enabled

Walks through every feature of the library.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from collections import namedtuple
from typing import Iterable

from tiny_table import Table, SPAN, enable_color


def _section(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n  {title}\n{bar}")


def demo_styles() -> None:
    _section("1. Style gallery")
    rows = [["Alice", "30", "NYC"], ["Bob", "25", "LA"], ["Carol", "41", "Berlin"]]
    for style in ("classic", "fancy", "rounded", "double", "grid", "compact", "simple", "markdown"):
        t = Table(headers=["Name", "Age", "City"], rows=rows, style=style)
        print(f"\n  style = {style!r}")
        print(t.render())


def demo_alignment() -> None:
    _section("2. Alignment")
    t = Table(headers=["left", "center", "right"], rows=[
        ["apple", "banana", "cherry"],
        ["1", "2", "3"],
        ["longer text", "mid", "x"],
    ], style="fancy")
    t.set_column_style("left", align="left")
    t.set_column_style("center", align="center")
    t.set_column_style("right", align="right")
    print(t.render())


def demo_color() -> None:
    _section("3. Colors (bold headers, alternating rows, conditional rows)")
    enable_color(True)
    try:
        # Alternating row stripes
        rows = [
            ["Alice", "alice@example.com", "active"],
            ["Bob", "bob@example.com", "active"],
            ["Carol", "carol@example.com", "inactive"],
            ["Dan", "dan@example.com", "active"],
        ]
        t = Table(headers=["name", "email", "status"], rows=rows, style="fancy")
        t.set_column_style("name", color="36")  # cyan
        t.set_column_style("status", color="32")
        print(t.render())

        # Conditional row coloring: red for inactive users
        t = Table(
            headers=["name", "email", "status"],
            rows=rows,
            style="fancy",
            row_color=lambda i, r: "31" if r[2] == "inactive" else None,
        )
        print(t.render())
    finally:
        enable_color(False)


def demo_width() -> None:
    _section("4. Auto vs fixed widths, and truncation")
    # Auto
    t = Table(headers=["a", "b"], rows=[["short", "v"], ["a much longer value", "tiny"]], style="rounded")
    print("Auto width:\n" + t.render())

    # Fixed per-column
    t = Table(headers=["a", "b"], rows=[["short", "v"], ["a much longer value", "tiny"]], style="rounded")
    t.set_column_style("a", width=10)
    print("\nFixed width=10 for column 'a':\n" + t.render())

    # Truncation with max_width
    t = Table(headers=["a"], rows=[["this string is way too long"]], style="classic", max_width=10)
    print("\nTruncation with max_width=10:\n" + t.render())


def demo_sort() -> None:
    _section("5. Sortable columns")
    rows = [
        ["Charlie", 28],
        ["Alice", 30],
        ["Bob", 25],
        ["Diana", 41],
    ]
    t = Table(headers=["name", "age"], rows=rows, style="fancy", sort_by="age")
    print("Sorted by age (asc):\n" + t.render())

    t = Table(headers=["name", "age"], rows=rows, style="fancy", sort_by="age", sort_desc=True)
    print("\nSorted by age (desc):\n" + t.render())


def demo_dicts() -> None:
    _section("6. Dict rows (columns inferred from first row)")
    rows = [
        {"product": "Widget", "price": 9.99, "stock": 42},
        {"product": "Gadget", "price": 19.95, "stock": 7},
        {"product": "Gizmo", "price": 4.50, "stock": 0},
    ]
    t = Table(rows=rows, style="fancy")
    print(t.render())


def demo_dataclass() -> None:
    _section("7. Dataclass rows")

    @dataclasses.dataclass
    class Repo:
        name: str
        stars: int
        language: str

    repos = [
        Repo("tiny-cli-table", 1, "Python"),
        Repo("requests", 52000, "Python"),
        Repo("deno", 92000, "Rust"),
        Repo("flask", 65000, "Python"),
    ]
    t = Table(rows=repos, style="rounded", sort_by="stars", sort_desc=True)
    print(t.render())


def demo_namedtuple() -> None:
    _section("8. Namedtuple rows")
    Point = namedtuple("Point", ["x", "y", "label"])
    rows = [Point(1, 2, "origin"), Point(3, 4, "first"), Point(5, 6, "second")]
    t = Table(rows=rows, style="grid")
    print(t.render())


def demo_span() -> None:
    _section("9. Column spanning / cell merging")
    rows = [
        ["report-2024-q1", SPAN, SPAN, "ok"],
        ["notes", SPAN, SPAN, SPAN],
        ["a", "b", "c", "d"],
    ]
    t = Table(headers=["section", "owner", "due", "status"], rows=rows, style="fancy")
    print(t.render())


def demo_nested() -> None:
    _section("10. Nested tables")
    inner = Table(headers=["k", "v"], rows=[["x", "1"], ["y", "2"], ["z", "3"]], style="compact")
    outer = Table(
        headers=["Section", "Detail"],
        rows=[
            ["Header", "the top of the page"],
            ["Body", "where content lives"],
            ["Keys", inner],
        ],
        style="fancy",
    )
    print(outer.render())


def demo_markdown() -> None:
    _section("11. Markdown output (great for GitHub READMEs)")
    t = Table(
        headers=["tool", "deps", "lines", "notes"],
        rows=[
            ["tiny-cli-table", "0", "1 file", "this repo"],
            ["tabulate", "1 (wcwidth)", "many", "wide"],
            ["prettytable", "1 (wcwidth)", "many", "wide"],
        ],
        style="markdown",
    )
    print(t.render())


def demo_full_showcase() -> None:
    _section("12. Full kitchen-sink showcase")
    enable_color(True)
    try:
        @dataclasses.dataclass
        class Server:
            host: str
            cpu: float
            mem: float
            status: str

        servers = [
            Server("web-01", 12.5, 38.2, "healthy"),
            Server("web-02", 88.1, 91.0, "warning"),
            Server("db-01", 45.0, 60.5, "healthy"),
            Server("cache-01", 95.0, 12.0, "critical"),
        ]
        t = Table(
            rows=servers,
            style="fancy",
            sort_by="cpu",
            sort_desc=True,
            row_color=lambda i, r: {
                "healthy": None,
                "warning": "33",
                "critical": "31",
            }.get(r[3]),
        )
        t.set_column_style("host", align="left", color="36")
        t.set_column_style("cpu", align="right")
        t.set_column_style("mem", align="right")
        t.set_column_style("status", align="center")
        print(t.render())
    finally:
        enable_color(False)


def main() -> int:
    if os.environ.get("FORCE_COLOR"):
        enable_color(True)

    print("tiny_table — interactive demo\n")
    print("A zero-dependency CLI table renderer. Here is what 5 lines of code")
    print("can produce:")
    print()
    print(
        Table(
            headers=["Name", "Role", "Stars"],
            rows=[
                ["Hussain", "maintainer", "∞"],
                ["You", "user", "1"],
            ],
            style="fancy",
        ).render()
    )

    demo_styles()
    demo_alignment()
    demo_color()
    demo_width()
    demo_sort()
    demo_dicts()
    demo_dataclass()
    demo_namedtuple()
    demo_span()
    demo_nested()
    demo_markdown()
    demo_full_showcase()
    print("\nDone.  pip install tiny-cli-table  (or just copy tiny_table.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
