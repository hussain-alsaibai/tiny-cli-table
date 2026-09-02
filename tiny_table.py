"""
tiny_table — a beautiful, zero-dependency Python CLI table renderer.

Supports multiple border styles (classic, compact, fancy, markdown, grid, simple,
rounded, double), column alignment, color highlighting, alternating row colors,
conditional row coloring via callbacks, column spanning / cell merging, nested
tables, sortable columns, auto and fixed widths, overflow truncation with
ellipsis, and iterable row types (list, dict, namedtuple, dataclass).

Stdlib only. No third-party dependencies.
"""

from __future__ import annotations

import dataclasses
import io
import re
from typing import Any, Callable, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = ["Table", "TinyTableError", "enable_color", "bold", "color", "SPAN"]
__version__ = "1.0.0"


# ---------------------------------------------------------------------------
# ANSI helpers — always safe to call; gracefully degrade when color disabled.
# ---------------------------------------------------------------------------

_IS_TTY = False  # caller may override with ``enable_color(True)``


def enable_color(enabled: bool) -> None:
    """Globally toggle ANSI color output."""
    global _IS_TTY
    _IS_TTY = bool(enabled)


def _supports_color() -> bool:
    return bool(_IS_TTY)


_RESET = "\x1b[0m"


def _ansi(code: str, text: str) -> str:
    if not _supports_color():
        return text
    return f"\x1b[{code}m{text}{_RESET}"


def bold(text: Any) -> str:
    """Wrap ``text`` in bold ANSI."""
    return _ansi("1", str(text))


def color(text: Any, code: str = "36") -> str:
    """Wrap ``text`` in an ANSI color code (default: cyan ``36``)."""
    return _ansi(code, str(text))


# ---------------------------------------------------------------------------
# Border styles.  Each style defines the box-drawing characters used at each
# junction in a single-line ASCII / Unicode table.
# ---------------------------------------------------------------------------

_STYLES: dict[str, dict[str, str]] = {
    "classic": {
        "tl": "+", "tr": "+", "bl": "+", "br": "+",
        "ml": "+", "mr": "+",
        "tm": "-", "bm": "-", "lm": "|", "rm": "|",
        "h": "-", "v": "|",
    },
    "compact": {
        "tl": " ", "tr": " ", "bl": " ", "br": " ",
        "ml": " ", "mr": " ",
        "tm": "-", "bm": "-", "lm": "  ", "rm": "  ",
        "h": "-", "v": " ",
    },
    "fancy": {
        "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
        "ml": "├", "mr": "┤",
        "tm": "─", "bm": "─", "lm": "│", "rm": "│",
        "h": "─", "v": "│",
    },
    "rounded": {
        "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
        "ml": "├", "mr": "┤",
        "tm": "─", "bm": "─", "lm": "│", "rm": "│",
        "h": "─", "v": "│",
    },
    "double": {
        "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝",
        "ml": "╠", "mr": "╣",
        "tm": "═", "bm": "═", "lm": "║", "rm": "║",
        "h": "═", "v": "║",
    },
    "grid": {
        "tl": "+", "tr": "+", "bl": "+", "br": "+",
        "ml": "+", "mr": "+",
        "tm": "-", "bm": "-", "lm": "|", "rm": "|",
        "h": "-", "v": "|",
    },
    "simple": {
        "tl": " ", "tr": " ", "bl": " ", "br": " ",
        "ml": "-", "mr": "-",
        "tm": "-", "bm": "-", "lm": " ", "rm": " ",
        "h": "-", "v": " ",
    },
}


_VALID_STYLES = set(_STYLES) | {"markdown"}


# ---------------------------------------------------------------------------
# TinyTableError — single exception type for the module.
# ---------------------------------------------------------------------------


class TinyTableError(Exception):
    """Raised when a table cannot be rendered due to invalid input."""


# ---------------------------------------------------------------------------
# Column spanning sentinel.
# ---------------------------------------------------------------------------


class _Span:
    """Sentinel marker: when present in a row, the cell spans the previous column(s)."""

    _instance: "Optional[_Span]" = None

    def __new__(cls) -> "_Span":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "SPAN"


SPAN = _Span()


# ---------------------------------------------------------------------------
# Width helpers — ANSI escape codes are zero-width for layout purposes.
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _display_width(text: str) -> int:
    """Return the visible width of ``text``, ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub("", text))


def _truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Truncate ``text`` to ``width`` visible characters, adding ``ellipsis`` if cut."""
    visible = _ANSI_RE.sub("", text)
    if len(visible) <= width:
        return text
    if width <= len(ellipsis):
        return ellipsis[:width]
    keep = width - len(ellipsis)
    out_chars: list[str] = []
    used = 0
    i = 0
    while i < len(text) and used < keep:
        m = _ANSI_RE.match(text, i)
        if m:
            out_chars.append(m.group(0))
            i = m.end()
            continue
        out_chars.append(text[i])
        used += 1
        i += 1
    return "".join(out_chars) + ellipsis


def _pad(text: str, width: int, align: str) -> str:
    """Pad / align ``text`` within ``width`` visible characters."""
    visible_len = _display_width(text)
    if visible_len >= width:
        return text
    gap = width - visible_len
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        right = gap - left
        return " " * left + text + " " * right
    return text + " " * gap  # left (default)


# ---------------------------------------------------------------------------
# Row normalization — accept lists, dicts, namedtuples, dataclasses.
# ---------------------------------------------------------------------------


def _normalize_row(row: Any, columns: Optional[Sequence[str]]) -> Tuple[List[Any], Optional[Sequence[str]]]:
    """Convert ``row`` to a list of cell values.  Returns (values, columns_or_None)."""
    if row is None:
        raise TinyTableError("row cannot be None")
    if isinstance(row, Mapping):
        if columns is None:
            columns = list(row.keys())
        return [row.get(c, "") for c in columns], columns
    if dataclasses.is_dataclass(row) and not isinstance(row, type):
        if columns is None:
            columns = [f.name for f in dataclasses.fields(row)]
        values = []
        for c in columns:
            if not hasattr(row, c):
                raise TinyTableError(f"dataclass row missing field {c!r}")
            values.append(getattr(row, c))
        return values, columns
    if isinstance(row, tuple) and hasattr(row, "_fields"):  # namedtuple
        if columns is None:
            columns = list(row._fields)  # type: ignore[attr-defined]
        values = []
        for c in columns:
            if not hasattr(row, c):
                raise TinyTableError(f"namedtuple row missing field {c!r}")
            values.append(getattr(row, c))
        return values, columns
    if isinstance(row, (list, tuple)):
        return list(row), columns
    raise TinyTableError(f"unsupported row type: {type(row).__name__}")


# ---------------------------------------------------------------------------
# The Table class.
# ---------------------------------------------------------------------------

ColorFunc = Callable[[int, Sequence[Any]], Optional[str]]
"""Callable used by ``row_color`` to color a single row.

Receives ``(row_index, row_values)`` and returns an ANSI color code (e.g. ``"31"``
for red) or ``None`` to leave the row uncolored.
"""


@dataclasses.dataclass
class _Column:
    name: str
    align: str = "left"
    width: Optional[int] = None  # None = auto
    color: Optional[str] = None  # ANSI code applied to every cell in column
    sort_key: Optional[Callable[[Any], Any]] = None  # for sortable columns


class Table:
    """A flexible, beautiful CLI table renderer.

    Parameters
    ----------
    headers:
        Column names.  If ``None``, columns are inferred from the first row.
    rows:
        Initial rows.  Each row may be a list/tuple, dict, namedtuple, or
        dataclass instance.
    style:
        One of ``"classic"``, ``"compact"``, ``"fancy"``, ``"rounded"``,
        ``"double"``, ``"grid"``, ``"simple"``, or ``"markdown"``.
    align:
        Default column alignment (``"left"``, ``"right"``, or ``"center"``).
    width:
        If an int, the table will try to fit within this many columns (cells
        may be truncated).  ``None`` lets columns size to their content.
    max_width:
        Hard upper bound on column widths.  Overflowing cells are truncated
        with an ellipsis.
    header_style:
        ANSI style code applied to headers (default ``"1;36"`` = bold cyan).
        ``None`` disables header coloring.
    row_colors:
        Pair of ANSI codes for alternating row striping.  Set to ``None`` to
        disable.  Default is a subtle gray stripe on every other row.
    row_color:
        Callable for per-row conditional coloring.  Receives ``(row_index,
        row_values)`` and returns an ANSI code or ``None``.  Wins over
        ``row_colors``.
    sort_by:
        Column name to sort rows by at render time.
    sort_desc:
        If True, sort in descending order.

    Examples
    --------
    >>> t = Table(headers=["name", "age"], rows=[["Alice", 30], ["Bob", 25]], style="fancy")
    >>> print(t)
    ╭──────────────╮
    │ name   │ age │
    ├──────────────┤
    │ Alice  │ 30  │
    │ Bob    │ 25  │
    ╰──────────────╯
    """

    SPAN = SPAN  # exposed as Table.SPAN for convenience

    def __init__(
        self,
        headers: Optional[Sequence[str]] = None,
        rows: Optional[Iterable[Any]] = None,
        style: str = "fancy",
        align: str = "left",
        width: Optional[int] = None,
        max_width: Optional[int] = None,
        header_style: Optional[str] = "1;36",
        row_colors: Optional[Tuple[Optional[str], Optional[str]]] = ("", "90"),
        row_color: Optional[ColorFunc] = None,
        sort_by: Optional[str] = None,
        sort_desc: bool = False,
    ) -> None:
        if style not in _VALID_STYLES:
            raise TinyTableError(f"unknown style {style!r}; choose from {sorted(_VALID_STYLES)}")
        if align not in ("left", "right", "center"):
            raise TinyTableError(f"unknown alignment {align!r}")
        self.style = style
        self.align = align
        self.width = width
        self.max_width = max_width
        self.header_style = header_style
        self.row_colors = row_colors
        self.row_color = row_color
        self.sort_by = sort_by
        self.sort_desc = sort_desc
        self._columns: List[_Column] = []
        self._rows: List[List[Any]] = []
        if headers is not None:
            for h in headers:
                self._columns.append(_Column(name=str(h), align=align))
        if rows is not None:
            for r in rows:
                self.add_row(r)

    # ----- column helpers ----------------------------------------------------

    @property
    def headers(self) -> List[str]:
        return [c.name for c in self._columns]

    def add_column(
        self,
        name: str,
        align: Optional[str] = None,
        width: Optional[int] = None,
        color: Optional[str] = None,
        sort_key: Optional[Callable[[Any], Any]] = None,
    ) -> _Column:
        """Append a new column definition."""
        if align is not None and align not in ("left", "right", "center"):
            raise TinyTableError(f"unknown alignment {align!r}")
        self._columns.append(
            _Column(name=str(name), align=align or self.align, width=width, color=color, sort_key=sort_key)
        )
        return self._columns[-1]

    def set_column_style(
        self,
        name: str,
        align: Optional[str] = None,
        width: Optional[int] = None,
        color: Optional[str] = None,
        sort_key: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        """Update an existing column's style in-place."""
        if align is not None and align not in ("left", "right", "center"):
            raise TinyTableError(f"unknown alignment {align!r}")
        for c in self._columns:
            if c.name == name:
                if align is not None:
                    c.align = align
                if width is not None:
                    c.width = width
                if color is not None:
                    c.color = color
                if sort_key is not None:
                    c.sort_key = sort_key
                return
        raise TinyTableError(f"column {name!r} not found")

    # ----- row helpers -------------------------------------------------------

    def add_row(self, row: Any) -> None:
        """Append a row, inferring columns from dicts/dataclasses if needed.

        Use :data:`SPAN` (or ``Table.SPAN``) to make a cell span the previous
        column(s):

        >>> t = Table(headers=["A", "B", "C"])
        >>> t.add_row(["merged", Table.SPAN, "tail"])
        """
        values, inferred_cols = _normalize_row(row, [c.name for c in self._columns] or None)
        if not self._columns:
            if inferred_cols is None:
                inferred_cols = [str(i) for i in range(len(values))]
            for c in inferred_cols:
                self._columns.append(_Column(name=str(c), align=self.align))
        if len(values) < len(self._columns):
            values = list(values) + [""] * (len(self._columns) - len(values))
        elif len(values) > len(self._columns):
            values = list(values[: len(self._columns)])
        self._rows.append([_stringify(v) for v in values])

    def sort(self, column: str, descending: bool = False) -> None:
        """Sort rows by ``column``."""
        idx = self._column_index(column)
        col = self._columns[idx]
        key_fn = col.sort_key or _natural_key
        self._rows.sort(key=lambda r: key_fn(r[idx] if idx < len(r) else ""), reverse=descending)

    # ----- rendering ---------------------------------------------------------

    def _column_index(self, name: str) -> int:
        for i, c in enumerate(self._columns):
            if c.name == name:
                return i
        raise TinyTableError(f"column {name!r} not found")

    def _compute_widths(self) -> List[int]:
        n = len(self._columns)
        widths = [0] * n
        for i, c in enumerate(self._columns):
            widths[i] = max(widths[i], _display_width(c.name))
        for row in self._rows:
            for i in range(n):
                text = row[i] if i < len(row) else ""
                for line in str(text).split("\n") or [""]:
                    widths[i] = max(widths[i], _display_width(line))
        for i, c in enumerate(self._columns):
            if c.width is not None:
                widths[i] = c.width
        if self.max_width is not None:
            widths = [min(w, self.max_width) for w in widths]
        if isinstance(self.width, int):
            total = sum(widths) + 3 * (n + 1)
            if total > self.width:
                available = max(self.width - 3 * (n + 1), n)
                if sum(widths) == 0:
                    return [max(1, available // n)] * n
                scale = available / sum(widths)
                widths = [max(1, int(w * scale)) for w in widths]
                leftover = available - sum(widths)
                if leftover:
                    widths[0] += leftover
        return widths

    def _render_markdown(self) -> str:
        widths = self._compute_widths()
        aligns = [c.align for c in self._columns]
        out = io.StringIO()
        # Header cells — Markdown convention is no extra space around content.
        header_cells = [c.name.ljust(widths[i]) for i, c in enumerate(self._columns)]
        out.write("|" + "|".join(header_cells) + "|\n")
        # Separator — one cell-width per column, matching header widths.
        sep_cells = []
        for i in range(len(self._columns)):
            w = widths[i]
            a = aligns[i]
            dash = "-" * max(w, 3)
            if a == "right":
                sep_cells.append(dash[:-1] + ":")
            elif a == "center":
                sep_cells.append(":" + dash[1:-1] + ":")
            else:
                sep_cells.append(dash)
        out.write("|" + "|".join(sep_cells) + "|\n")
        # Data rows — right/center align cells inside their column.
        for row in self._render_rows():
            data_cells = []
            for i, _c in enumerate(self._columns):
                text = row[i] if i < len(row) else ""
                if self.max_width:
                    text = _truncate(str(text), widths[i])
                else:
                    text = str(text)
                a = aligns[i]
                if a == "right":
                    text = text.rjust(widths[i])
                elif a == "center":
                    inner = widths[i]
                    pad_total = max(inner - _display_width(text), 0)
                    text = (" " * (pad_total // 2)) + text + (" " * (pad_total - pad_total // 2))
                else:
                    text = text.ljust(widths[i])
                data_cells.append(text)
            out.write("|" + "|".join(data_cells) + "|\n")
        return out.getvalue().rstrip("\n")

    def _render_box(self) -> str:
        if self.style == "markdown":
            return self._render_markdown()
        b = _STYLES[self.style]
        widths = self._compute_widths()
        aligns = [c.align for c in self._columns]

        def rule(left: str, mid: str, right: str, fill: str) -> str:
            return left + mid.join(fill * (w + 2) for w in widths) + right

        top = rule(b["tl"], b["tm"], b["tr"], b["h"])
        mid = rule(b["ml"], b["tm"], b["mr"], b["h"])
        bot = rule(b["bl"], b["bm"], b["br"], b["h"])

        out_lines: List[str] = [top]
        header_cells = []
        for i, c in enumerate(self._columns):
            text = _pad(c.name, widths[i], aligns[i])
            if self.header_style:
                text = _ansi(self.header_style, text)
            header_cells.append(" " + text + " ")
        out_lines.append(b["lm"] + b["v"].join(header_cells) + b["rm"])
        rows = self._render_rows()
        if rows:
            out_lines.append(mid)
            for ri, row in enumerate(rows):
                out_lines.append(self._format_row(row, widths, aligns, ri))
        out_lines.append(bot)
        return "\n".join(out_lines)

    def _sorted_indices(self) -> List[int]:
        rows = self._rows
        if self.sort_by is None:
            return list(range(len(rows)))
        idx = self._column_index(self.sort_by)
        col = self._columns[idx]
        key_fn = col.sort_key or _natural_key
        return sorted(
            range(len(rows)),
            key=lambda i: key_fn(rows[i][idx] if idx < len(rows[i]) else ""),
            reverse=self.sort_desc,
        )

    def _render_rows(self) -> List[List[Any]]:
        return [self._rows[i] for i in self._sorted_indices()]

    def _format_row(self, row: List[Any], widths: List[int], aligns: List[str], row_index: int) -> str:
        b = _STYLES[self.style]
        per_row_color: Optional[str] = None
        if self.row_color is not None:
            try:
                per_row_color = self.row_color(row_index, row)
            except Exception:
                per_row_color = None
        if per_row_color is None and self.row_colors is not None:
            a, bcode = self.row_colors
            per_row_color = a if (row_index % 2 == 0) else bcode

        cells: List[str] = []
        i = 0
        while i < len(self._columns):
            value = row[i] if i < len(row) else ""
            span = 1
            j = i + 1
            while j < len(self._columns) and (j >= len(row) or row[j] is SPAN):
                span += 1
                j += 1
            total_width = sum(widths[i : i + span]) + 2 * (span - 1)
            text = str(value)
            if self.max_width:
                text = _truncate(text, total_width)
            text = _pad(text, total_width, aligns[i])
            col_color = self._columns[i].color
            if col_color:
                text = _ansi(col_color, text)
            if per_row_color:
                text = _ansi(per_row_color, text)
            cells.append(" " + text + " ")
            i = j
        return b["lm"] + b["v"].join(cells) + b["rm"]

    # ----- public output -----------------------------------------------------

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        return f"<Table style={self.style!r} cols={len(self._columns)} rows={len(self._rows)}>"

    def render(self) -> str:
        """Return the table as a string."""
        return self._render_box()

    def print(self) -> None:
        """Print the table to stdout."""
        print(self.render())

    def to_string(self) -> str:
        """Alias for :meth:`render`."""
        return self.render()


# ---------------------------------------------------------------------------
# Sorting helpers.
# ---------------------------------------------------------------------------

def _stringify(value: Any) -> Any:
    """Convert ``value`` to its render-friendly form."""
    if value is None or value is SPAN:
        return value  # preserve sentinel; None will be rendered as empty string
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, Table):
        return value.render()
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify(v) for v in value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    return str(value)


def _natural_key(value: Any) -> Tuple[int, Any]:
    """Sort key that places numbers before strings and respects numeric value."""
    if value is None:
        return (2, "")
    s = str(value)
    try:
        return (0, float(s))
    except (TypeError, ValueError):
        return (1, s.lower())
