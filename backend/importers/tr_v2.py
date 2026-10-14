"""Trade Republic Tax Report parser — 2025+ Spanish-branch (Sucursal España) format.

The Spanish-branch report replaced the former multi-section tax report
(Roman-numeral sections I-XI) with a flat structure organised by the
Spanish tax returns themselves (Modelo 100, Modelo 714). Key differences
vs. the legacy parser in ``tr.py``:

- Dates are ``DD/MM/YYYY`` (not ``DD.MM.YYYY``).
- Rows carry two retention columns: ``Retenciones en origen`` (foreign
  WHT) and ``Retenciones en destino`` (Spanish 19% retention applied by
  TR as Spanish branch).
- Capital gains are one row per sell (no buy/sell grouping + "menos/más
  1 año" summary line).
- There is no "all transactions" (old Section VI) list.
- ``Liquidación al contado`` / ``Transferencia saliente`` appear as
  corporate-action transaction types on ANR (derechos) positions.

Extraction uses pdfplumber's ``extract_words`` so table cells that wrap
across lines (long names, two-word countries) are regrouped by y
coordinate. Numeric columns on each row are then parsed from their
ISIN-anchored line.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from backend.importers.base import (
    ParsedCapitalGain,
    ParsedCasilla,
    ParsedPortfolioHolding,
    ParsedTransaction,
    ParsedWithholding,
    TRTaxReport,
    TxType,
    ISIN_RE,
    parse_dmy,
    parse_eur_decimal,
)

# ---------------------------------------------------------------------------
# Low-level parsers
# ---------------------------------------------------------------------------

_EUR_NUM = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d+")
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _try_num(token: str) -> Decimal | None:
    if not token or token == "n/a":
        return None
    try:
        return parse_eur_decimal(token)
    except (InvalidOperation, ValueError):
        return None


# Countries, ordered longest-first so "Estados Unidos" beats "España".
_COUNTRIES = [
    "Estados Unidos de América",
    "Estados Unidos",
    "Países Bajos",
    "Reino Unido",
    "Hong Kong",
    "Alemania",
    "Australia",
    "Austria",
    "Bélgica",
    "Brasil",
    "Canadá",
    "China",
    "Dinamarca",
    "España",
    "Finlandia",
    "Francia",
    "Irlanda",
    "Italia",
    "Japón",
    "Luxemburgo",
    "Noruega",
    "Portugal",
    "Singapur",
    "Suecia",
    "Suiza",
]

_TX_TYPE_LABELS = [
    "Liquidación al contado",
    "Transferencia saliente",
    "Cupón del bono",
    "Dividendo",
    "Intereses",
    "Venta",
    "Compra",
]


# ---------------------------------------------------------------------------
# Row grouping by y-position
# ---------------------------------------------------------------------------


def _page_lines(page: pdfplumber.page.Page, tol: float = 3.0) -> list[str]:
    """Return the page text grouped by y-position (tolerant of wrapped cells)."""
    words = page.extract_words()
    by_y: dict[int, list[tuple[float, str]]] = defaultdict(list)
    for w in words:
        y = int(round(w["top"] / tol) * tol)
        by_y[y].append((w["x0"], w["text"]))
    return [
        " ".join(t for _, t in sorted(by_y[y]))
        for y in sorted(by_y.keys())
    ]


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def is_spanish_branch_format(pdf_path: str | Path) -> bool:
    """Return True if the PDF is a 2025+ Spanish-branch Tax Report."""
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return False
        first = pdf.pages[0].extract_text() or ""
    return "SUCURSAL EN ESPAÑA" in first.upper()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

_CLIENT_RE = re.compile(r"Clientela:\s*(\d+)")
_PERIOD_RE = re.compile(
    r"Período\s*reportado:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})"
)


def _extract_header(pages_text: list[str]) -> tuple[str, date, date]:
    joined = "\n".join(pages_text[:4])
    client = _CLIENT_RE.search(joined)
    period = _PERIOD_RE.search(joined)
    if not period:
        raise ValueError("No se encontró el período en el PDF (formato ES-IBAN).")
    start = parse_dmy(period.group(1))
    end = parse_dmy(period.group(2))
    return (client.group(1) if client else "", start, end)


# ---------------------------------------------------------------------------
# Row splitter: extract ISIN, name, country, type, date, numbers from a row
# ---------------------------------------------------------------------------


def _strip_known_prefix(line: str, options: list[str]) -> tuple[str | None, str]:
    for opt in options:
        if line.startswith(opt + " ") or line == opt:
            return opt, line[len(opt):].lstrip()
    return None, line


def _split_row_prefix(line: str) -> dict | None:
    """Split a data row into structured fields.

    Handles the variable parts before the numeric columns:

        ``<ISIN|N/A> <nombre...> <fecha DD/MM/YYYY> <país...> <tipo...> <nums...>``

    Both name and country may contain multiple words. Anchored on
    the DD/MM/YYYY date and a known country/type list.
    """
    tokens = line.split()
    if not tokens:
        return None

    date_idx = None
    for i, t in enumerate(tokens):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None or date_idx == 0:
        return None

    pre = tokens[:date_idx]
    date_token = tokens[date_idx]
    post = tokens[date_idx + 1:]

    isin = None
    if ISIN_RE.fullmatch(pre[0]):
        isin = pre[0]
        name_tokens = pre[1:]
    elif pre[0].upper() == "N/A":
        isin = None
        name_tokens = pre[1:]
    else:
        name_tokens = pre
    name = " ".join(name_tokens).strip()

    post_line = " ".join(post)
    country, rest = _strip_known_prefix(post_line, _COUNTRIES)
    if country is None:
        return None
    tx_type, rest = _strip_known_prefix(rest, _TX_TYPE_LABELS)

    nums_raw = rest.split()
    return {
        "isin": isin,
        "name": name,
        "date": parse_dmy(date_token),
        "country": country,
        "type": tx_type,
        "nums": nums_raw,
    }


# ---------------------------------------------------------------------------
# Modelo 100 – 0027 Intereses + 0029 Dividendos
# ---------------------------------------------------------------------------


def _parse_rendimientos_row(line: str) -> ParsedTransaction | None:
    """Rows of casillas 0027 (intereses) and 0029 (dividendos).

    Column layout (in the PDF): ``ISIN | Bien | Fecha | País | Tipo |
    Ingresos | Origen | [Acreditables] | Destino``.

    When ``Origen`` or ``Acreditables`` are zero, the PDF collapses
    them, so we parse by number count: last is destino, first is
    gross, and 0/1/2 middle values are origen/acreditable.
    """
    row = _split_row_prefix(line)
    if row is None:
        return None

    nums = [_try_num(n) for n in row["nums"] if n.lower() not in {"n/a", "(*)"}]
    nums = [n for n in nums if n is not None]
    if not nums:
        return None

    gross = nums[0]
    destino = nums[-1]
    middle = nums[1:-1]
    # 0 middle → origen=0, acreditable=0
    # 1 middle → origen=middle
    # 2 middle → origen, acreditable
    origen = middle[0] if len(middle) >= 1 else Decimal("0")
    acreditable = middle[1] if len(middle) >= 2 else Decimal("0")

    tx_type = TxType.INTEREST if row["type"] == "Intereses" else TxType.DIVIDEND

    return ParsedTransaction(
        tx_type=tx_type,
        trade_date=row["date"],
        isin=row["isin"] or "",
        name=row["name"],
        country=row["country"],
        quantity=Decimal("1"),
        price=gross,
        currency="EUR",
        exchange_rate=Decimal("1"),
        gross_amount=gross,
        fees=Decimal("0"),
        withholding_tax=origen + destino,
        domestic_withholding_tax=destino,
        foreign_withholding_tax=origen,
        net_amount_eur=gross - origen - destino,
        double_taxation_amount=acreditable if acreditable > 0 else None,
        casilla=27 if tx_type == TxType.INTEREST else 29,
    )


# ---------------------------------------------------------------------------
# Capital gains rows (acciones + otros elementos)
# ---------------------------------------------------------------------------


def _parse_capital_gain_row(line: str) -> ParsedCapitalGain | None:
    """Parse a single capital-gain row.

    Layout: ``ISIN <name> <país> EUR <fecha trans> <tipo> <qty>
    <fecha adq> <val trans> <val adq> <comisión> <origen|n/a>
    <destino|n/a> <ganancia>``.
    """
    tokens = line.split()
    if "EUR" not in tokens:
        return None
    try:
        eur_idx = tokens.index("EUR")
    except ValueError:
        return None

    pre = tokens[:eur_idx]
    post = tokens[eur_idx + 1:]

    if not pre or not ISIN_RE.fullmatch(pre[0]):
        return None

    isin = pre[0]
    # country is the last known country word(s) in pre
    country = ""
    name_tokens = pre[1:]
    pre_line = " ".join(name_tokens)
    for c in _COUNTRIES:
        if pre_line.endswith(" " + c) or pre_line == c:
            country = c
            pre_line = pre_line[: -len(c)].rstrip()
            break
    name = pre_line.strip()

    if len(post) < 6 or not _DATE_RE.match(post[0]):
        return None
    sell_date = parse_dmy(post[0])

    # Optional tipo tokens (may be wrapped to adjacent lines, so it's OK
    # to have none here). Walk until we hit qty (a comma-number).
    type_tokens: list[str] = []
    i = 1
    while i < len(post):
        t = post[i]
        if re.match(r"^-?\d", t) and "," in t:
            break
        type_tokens.append(t)
        i += 1

    if i >= len(post):
        return None
    qty = _try_num(post[i])
    i += 1
    if qty is None or i >= len(post) or not _DATE_RE.match(post[i]):
        return None
    buy_date = parse_dmy(post[i])
    i += 1

    rest = post[i:]
    numeric = [(t, _try_num(t)) for t in rest]
    # last column is always ganancia
    pl = None
    for _, n in reversed(numeric):
        if n is not None:
            pl = n
            break
    if pl is None:
        return None

    # Strip trailing ganancia; remaining numbers from the right are
    # optional destino, optional origen; skipping n/a values.
    # We also extract val-trans, val-adq, comisión in order from the left.
    nums_from_left: list[Decimal] = []
    for t, n in numeric:
        if n is not None and (t, n) != (None, None):
            nums_from_left.append(n)
    if not nums_from_left:
        return None
    # Remove the last (pl)
    nums_from_left = nums_from_left[:-1]
    # Expected in order: val_trans, val_adq, comisión, [origen], [destino]
    val_trans = nums_from_left[0] if len(nums_from_left) >= 1 else Decimal("0")
    val_adq = nums_from_left[1] if len(nums_from_left) >= 2 else Decimal("0")
    fee = nums_from_left[2] if len(nums_from_left) >= 3 else Decimal("0")

    holding_days = (sell_date - buy_date).days
    holding = ">1y" if holding_days >= 365 else "<1y"
    casilla = 332 if pl >= 0 else 337

    sell_price = (val_trans / qty) if qty and qty != 0 else Decimal("0")
    buy_price = (val_adq / qty) if qty and qty != 0 else Decimal("0")

    return ParsedCapitalGain(
        isin=isin,
        name=name,
        country=country,
        buy_date=buy_date,
        buy_quantity=qty,
        buy_price=buy_price,
        buy_fees=Decimal("0"),
        buy_total_eur=val_adq,
        sell_date=sell_date,
        sell_quantity=qty,
        sell_price=sell_price,
        sell_fees=fee,
        sell_total_eur=val_trans,
        realized_pl_eur=pl,
        holding_period=holding,
        casilla=casilla,
    )


# ---------------------------------------------------------------------------
# Modelo 714 – E (deposits) / F (bonds) / G (shares)
# ---------------------------------------------------------------------------


def _parse_m714_row(line: str, casilla: int) -> ParsedPortfolioHolding | None:
    """Parse a Modelo 714 holdings row.

    Layout: ``<ISIN?> <país?> <descripción...> <qty> <avg> <val_31dic>
    <val_fiscal> <moneda/tipo>``. CurrentAccount (E) has no ISIN/país.
    """
    tokens = line.split()
    if len(tokens) < 5:
        return None

    # Extract trailing "EUR / X,XXXXX" or "USD / 0,85056"
    fx_tokens = []
    if len(tokens) >= 3 and tokens[-2] == "/" and tokens[-3] in {
        "EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "HKD", "BRL", "CNY",
    }:
        fx_tokens = tokens[-3:]
        tokens = tokens[:-3]
    currency = fx_tokens[0] if fx_tokens else "EUR"

    # Pull trailing numbers off the right
    trailing: list[Decimal] = []
    while tokens:
        n = _try_num(tokens[-1])
        if n is None:
            break
        trailing.insert(0, n)
        tokens.pop()
    if len(trailing) < 3:
        return None

    # Last 4 numbers (if present): qty, avg, val31, val_fiscal — but E
    # has only 3 (no ISIN/qty). Interpret by length.
    if casilla == 5:
        # E: avg, val31, val_fiscal
        qty = Decimal("0")
        avg = trailing[-3]
        val31 = trailing[-2]
        val_fiscal = trailing[-1]
    else:
        # F1/G1/G2: qty, avg, val31, val_fiscal
        if len(trailing) < 4:
            return None
        qty = trailing[-4]
        avg = trailing[-3]
        val31 = trailing[-2]
        val_fiscal = trailing[-1]

    # Remaining tokens on the left: [ISIN?] [País?] <descripción...>
    isin = None
    country = ""
    if tokens and ISIN_RE.fullmatch(tokens[0]):
        isin = tokens[0]
        tokens = tokens[1:]
    if tokens:
        for c in _COUNTRIES:
            if tokens[0:].__len__() and " ".join(tokens).startswith(c):
                country = c
                tokens = " ".join(tokens)[len(c):].strip().split()
                break
    name = " ".join(tokens).strip()
    if not name:
        name = "CurrentAccount" if casilla == 5 else ""

    asset_type = {5: "Cuenta de efectivo", 6: "Renta fija", 8: "ETF", 9: "Acciones"}.get(
        casilla, "Acciones"
    )

    return ParsedPortfolioHolding(
        isin=isin or "",
        name=name,
        currency=currency,
        asset_type=asset_type,
        country=country,
        casilla_714=casilla,
        quantity=qty,
        avg_q4_balance=avg,
        value_dec31_eur=val31,
        fiscal_valuation=val_fiscal,
    )


# ---------------------------------------------------------------------------
# Page classification and section walkers
# ---------------------------------------------------------------------------


def _page_kind(text: str) -> str:
    """Classify a page by its leading title."""
    t = text.strip()
    if t.startswith("Informe resumido") or "Informe resumido" in t[:60]:
        return "summary"
    if t.startswith("Base imponible general") or "Base imponible general" in t[:60]:
        return "base_general"
    # Modelo 100 detail pages start with casilla code + descripción.
    if t.startswith("0027 ") or t.startswith("Modelo 100"):
        return "m100_0027"
    if t.startswith("0029 "):
        return "m100_0029"
    if "Retenciones en Retenciones Retenciones en" in t and "ISIN Bien o derecho" in t:
        return "m100_0029"
    if "Ganancias y pérdidas patrimoniales derivadas de transmisiones de acciones" in t:
        return "m100_gy_acciones"
    if "Ganancias y pérdidas patrimoniales derivadas de transmisiones de otros elementos" in t:
        return "m100_gy_otros"
    if "E. Depósitos en cuenta corriente" in t:
        return "m714_E"
    if "F. Valores representativos de la cesión" in t:
        return "m714_F"
    if "G. Valores no exentos representativos" in t:
        return "m714_G"
    if t.startswith("Valoración") and "Cuenta de depósito" in t:
        # Continuation of F/G holdings pages
        return "m714_G_cont"
    if "Resumen de retenciones en origen" in t:
        return "retenciones_origen"
    if "Informe resumido" in t[:60]:
        return "summary"
    if "Base imponible general" in t[:60]:
        return "base_general"
    if t.startswith("Nombre del valor"):
        return "per_security"
    return "unknown"


def _page_continues_table(text: str) -> bool:
    """Hint that a page is a continuation of the previous table (no title)."""
    # Pages 5/6 (dividends page 4+5 continuation), 9 (gains page 8 cont),
    # and 14/15 (G shares continuation). All start with header row.
    t = text.strip()
    return t.startswith(("Retenciones en", "Valor de", "Valoración", "N° Valores", "ISIN"))


# ---------------------------------------------------------------------------
# Aggregated totals – Informe resumido + Retenciones en origen
# ---------------------------------------------------------------------------


def _parse_summary(text: str) -> list[ParsedCasilla]:
    """Extract casillas 0027, 0029, 0030, 0031, 0033, 0034 totals from the
    ``Informe resumido`` page."""
    wanted = ["0027", "0029", "0030", "0031", "0033", "0034"]
    out: list[ParsedCasilla] = []
    # Each casilla code is followed by a free-form description that
    # wraps across many lines and then three amounts (Rendimiento,
    # Ret.origen, Ret.destino). We want the first (Rendimiento).
    for code in wanted:
        pat = re.compile(
            rf"(?<!\d){code}(?!\d)"
            rf"[\s\S]*?(-?\d{{1,3}}(?:\.\d{{3}})*,\d+)"
        )
        m = pat.search(text)
        if m:
            out.append(
                ParsedCasilla(
                    modelo=100,
                    casilla=int(code),
                    description=f"Casilla {code}",
                    amount_eur=parse_eur_decimal(m.group(1)),
                )
            )
    return out


def _parse_base_general(text: str) -> list[ParsedCasilla]:
    """Extract the two casillas needed for Modelo 100 D2 / D3 from the
    ``Base imponible general`` page (ganancias 0328/0329 equivalents)."""
    out: list[ParsedCasilla] = []
    patterns = [
        ("acciones_gain", r"transmisión de Acciones\.\s+(-?\d{1,3}(?:\.\d{3})*,\d+)", 328),
        ("otros_gain", r"otros elementos patrimoniales\s+(-?\d{1,3}(?:\.\d{3})*,\d+)", 380),
    ]
    for _, pat, casilla in patterns:
        m = re.search(pat, text)
        if m:
            out.append(
                ParsedCasilla(
                    modelo=100,
                    casilla=casilla,
                    description="Ganancia/pérdida transmisión",
                    amount_eur=parse_eur_decimal(m.group(1)),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


def parse_tr_tax_report_v2(pdf_path: str | Path) -> TRTaxReport:
    """Parse a Spanish-branch (2025+) Trade Republic Tax Report PDF."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    dividends: list[ParsedTransaction] = []
    capital_gains: list[ParsedCapitalGain] = []
    withholdings: list[ParsedWithholding] = []
    holdings: list[ParsedPortfolioHolding] = []
    casillas_m100: list[ParsedCasilla] = []
    casillas_m714: list[ParsedCasilla] = []

    pages_text: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        pages_text.extend(page.extract_text() or "" for page in pdf.pages)

        last_kind = "unknown"
        # Track Modelo 714 subsection (E / F1 / G1 / G2)
        m714_sub = None

        for idx, page in enumerate(pdf.pages):
            text = pages_text[idx]
            kind = _page_kind(text)
            if kind == "unknown" and _page_continues_table(text):
                kind = last_kind if last_kind.startswith(
                    ("m100_", "m714_")
                ) else "unknown"
            if kind == "summary":
                casillas_m100.extend(_parse_summary(text))
            elif kind == "base_general":
                casillas_m100.extend(_parse_base_general(text))
            elif kind == "retenciones_origen":
                # Already captured inline on each dividend row; nothing extra.
                pass
            elif kind in {"m100_0027", "m100_0029"}:
                lines = _page_lines(page)
                for line in lines:
                    if line.startswith(("Retenciones", "ISIN", "Total", "*", "Página")):
                        continue
                    tx = _parse_rendimientos_row(line)
                    if tx:
                        dividends.append(tx)
                        if tx.withholding_tax > 0:
                            withholdings.append(
                                ParsedWithholding(
                                    country=tx.country,
                                    isin=tx.isin,
                                    name=tx.name,
                                    tx_type=(
                                        "Dividendo"
                                        if tx.tx_type == TxType.DIVIDEND
                                        else "Intereses"
                                    ),
                                    payment_date=tx.trade_date,
                                    currency="EUR",
                                    income_eur=tx.gross_amount,
                                    withholding_eur=tx.withholding_tax,
                                    withholding_rate=Decimal("0"),
                                    double_taxation_eur=tx.double_taxation_amount
                                    or Decimal("0"),
                                )
                            )
            elif kind in {"m100_gy_acciones", "m100_gy_otros"}:
                lines = _page_lines(page)
                for line in lines:
                    if line.startswith(("Valor", "Nombre", "ISIN", "activo", "pérdida", "(*)", "Total", "*", "Página")):
                        continue
                    cg = _parse_capital_gain_row(line)
                    if cg:
                        capital_gains.append(cg)
            elif kind == "m714_E":
                m714_sub = 5
                lines = _page_lines(page)
                for line in lines:
                    if line.startswith(("E.", "Valoración", "Cuenta", "Total", "*", "Página")):
                        continue
                    h = _parse_m714_row(line, 5)
                    if h:
                        holdings.append(h)
                total_e = _extract_total(text)
                if total_e is not None:
                    casillas_m714.append(
                        ParsedCasilla(
                            modelo=714,
                            casilla=5,
                            description="Depósitos en cuenta corriente o de ahorro",
                            amount_eur=total_e,
                        )
                    )
            elif kind == "m714_F":
                m714_sub = 6
                lines = _page_lines(page)
                for line in lines:
                    if line.startswith(("F.", "F1:", "Valoración", "Cuenta", "Total", "*", "Página")):
                        continue
                    h = _parse_m714_row(line, 6)
                    if h:
                        holdings.append(h)
                total_f = _extract_total(text)
                if total_f is not None:
                    casillas_m714.append(
                        ParsedCasilla(
                            modelo=714,
                            casilla=6,
                            description="Deuda pública, obligaciones, bonos",
                            amount_eur=total_f,
                        )
                    )
            elif kind in {"m714_G", "m714_G_cont"}:
                lines = _page_lines(page)
                for line in lines:
                    if "G1:" in line:
                        m714_sub = 8
                        continue
                    if "G2:" in line:
                        m714_sub = 9
                        continue
                    if line.startswith(("G.", "Valoración", "Cuenta", "Total", "*", "Página", "N°", "ISIN")):
                        continue
                    if m714_sub in (8, 9):
                        h = _parse_m714_row(line, m714_sub)
                        if h:
                            holdings.append(h)

            if kind != "unknown":
                last_kind = kind

    # Derive G1/G2 casillas by summing parsed holdings (the PDF only
    # prints the combined Total on the last G page).
    g1_total = sum(
        (h.fiscal_valuation for h in holdings if h.casilla_714 == 8),
        Decimal("0"),
    )
    g2_total = sum(
        (h.fiscal_valuation for h in holdings if h.casilla_714 == 9),
        Decimal("0"),
    )
    if g1_total > 0:
        casillas_m714.append(
            ParsedCasilla(
                modelo=714,
                casilla=8,
                description="Acciones IIC y SOCIMI negociadas en mercados organizados",
                amount_eur=g1_total,
            )
        )
    if g2_total > 0:
        casillas_m714.append(
            ParsedCasilla(
                modelo=714,
                casilla=9,
                description="Acciones y participaciones negociadas en mercados organizados",
                amount_eur=g2_total,
            )
        )

    client_id, period_start, period_end = _extract_header(pages_text)

    return TRTaxReport(
        client_id=client_id,
        period_start=period_start,
        period_end=period_end,
        currency="EUR",
        fiscal_year=period_end.year,
        dividends=dividends,
        capital_gains=capital_gains,
        transactions=[],  # Section VI no longer exists in the new format
        withholdings=withholdings,
        holdings=holdings,
        casillas_modelo_100=casillas_m100,
        casillas_modelo_714=casillas_m714,
        source_variant="es_branch",
    )


def _extract_total(text: str) -> Decimal | None:
    """Return the LAST EUR number on the ``Total`` line (value fiscal)."""
    for line in reversed(text.splitlines()):
        if line.strip().startswith("Total"):
            nums = _EUR_NUM.findall(line)
            if nums:
                return parse_eur_decimal(nums[-1])
    return None
