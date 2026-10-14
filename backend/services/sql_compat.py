"""Dialect-portable SQL functions for date formatting.

SQLite's ``strftime`` does not exist in PostgreSQL. These helpers compile
to ``STRFTIME(...)`` on SQLite and ``TO_CHAR(...)`` on PostgreSQL, both
returning the same string format — so existing comparisons against
``str(year)`` or ``"%Y-%m"`` labels keep working unchanged.
"""

from datetime import date

from sqlalchemy import and_
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression
from sqlalchemy.types import String


def year_range(column, fiscal_year: int):
    """Index-friendly "column falls within *fiscal_year*" predicate.

    Use in ``.filter(...)`` instead of ``year_str(column) == str(year)``.
    Wrapping the column in ``year_str`` (STRFTIME/TO_CHAR) forces a full scan
    because the planner can't use the date index. A half-open range keeps the
    column bare so the index on it applies. Both ``trade_date`` and
    ``close_date`` are DATE columns, so the date-object bounds compare directly.
    """
    return and_(
        column >= date(fiscal_year, 1, 1),
        column < date(fiscal_year + 1, 1, 1),
    )


class year_str(expression.FunctionElement):
    type = String()
    name = "year_str"
    inherit_cache = True


@compiles(year_str, "sqlite")
def _year_str_sqlite(element, compiler, **kw):
    col = next(iter(element.clauses))
    return f"STRFTIME('%Y', {compiler.process(col, **kw)})"


@compiles(year_str)
def _year_str_default(element, compiler, **kw):
    col = next(iter(element.clauses))
    return f"TO_CHAR({compiler.process(col, **kw)}, 'YYYY')"


class year_month_str(expression.FunctionElement):
    type = String()
    name = "year_month_str"
    inherit_cache = True


@compiles(year_month_str, "sqlite")
def _year_month_str_sqlite(element, compiler, **kw):
    col = next(iter(element.clauses))
    return f"STRFTIME('%Y-%m', {compiler.process(col, **kw)})"


@compiles(year_month_str)
def _year_month_str_default(element, compiler, **kw):
    col = next(iter(element.clauses))
    return f"TO_CHAR({compiler.process(col, **kw)}, 'YYYY-MM')"
