"""Dialect-portable SQL functions for date formatting.

SQLite's ``strftime`` does not exist in PostgreSQL. These helpers compile
to ``STRFTIME(...)`` on SQLite and ``TO_CHAR(...)`` on PostgreSQL, both
returning the same string format — so existing comparisons against
``str(year)`` or ``"%Y-%m"`` labels keep working unchanged.
"""

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression
from sqlalchemy.types import String


class year_str(expression.FunctionElement):
    type = String()
    name = "year_str"
    inherit_cache = True


@compiles(year_str, "sqlite")
def _year_str_sqlite(element, compiler, **kw):
    col = list(element.clauses)[0]
    return f"STRFTIME('%Y', {compiler.process(col, **kw)})"


@compiles(year_str)
def _year_str_default(element, compiler, **kw):
    col = list(element.clauses)[0]
    return f"TO_CHAR({compiler.process(col, **kw)}, 'YYYY')"


class year_month_str(expression.FunctionElement):
    type = String()
    name = "year_month_str"
    inherit_cache = True


@compiles(year_month_str, "sqlite")
def _year_month_str_sqlite(element, compiler, **kw):
    col = list(element.clauses)[0]
    return f"STRFTIME('%Y-%m', {compiler.process(col, **kw)})"


@compiles(year_month_str)
def _year_month_str_default(element, compiler, **kw):
    col = list(element.clauses)[0]
    return f"TO_CHAR({compiler.process(col, **kw)}, 'YYYY-MM')"
