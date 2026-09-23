"""API endpoints for file import."""

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import and_, or_

from backend.api.auth import CurrentUser
from backend.api.schemas import DataIssueOut, ImportRecordOut, ImportResult, ResolveIssueRequest
from backend.database import DbSession
from backend.importers.bbva import (
    compute_file_hash as bbva_compute_hash,
    parse_bbva_pdfs,
)
from backend.importers.dg import (
    compute_file_hash as dg_compute_hash,
    parse_dg_annual_report,
)
from backend.importers.etoro import (
    compute_file_hash as etoro_compute_hash,
    parse_etoro_statement,
)
from backend.importers.ibkr import (
    compute_file_hash as ibkr_compute_hash,
    parse_ibkr_activity_statement,
)
from backend.importers.ing import (
    compute_file_hash as ing_compute_hash,
    parse_ing_report,
)
from backend.importers.tr import compute_file_hash, parse_tr_tax_report
from backend.importers.tr_csv import (
    compute_file_hash as tr_csv_compute_hash,
    parse_tr_csv,
)
from backend.models import Account, DataIssue, ImportRecord
from backend.services.billing_service import count_imports_this_month, import_allowance
from backend.services.import_service import (
    import_bbva_report,
    import_dg_report,
    import_etoro_report,
    import_ibkr_report,
    import_ing_report,
    import_tr_csv_report,
    import_tr_report,
    _delete_import_data,
    delete_all_imports,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/imports", tags=["imports"])


def enforce_import_quota(db: DbSession, user: CurrentUser) -> None:
    """Reject an upload once the plan's monthly import allowance is spent.

    `max_imports_per_month` was advertised on the billing page and returned by
    /billing/subscription, but nothing consulted it — every import endpoint
    accepted uploads regardless of plan. Applied via the route decorator rather
    than a parameter so it is visible on each route and cannot be forgotten in
    the body of a new one.
    """
    used = count_imports_this_month(db, user)
    allowed = import_allowance(user)
    if used < allowed:
        return
    raise HTTPException(
        status_code=403,
        detail=(
            f"Has alcanzado el límite de {allowed} importaciones al mes de tu plan "
            f"({used} este mes). Mejora tu plan para importar más."
        ),
    )


ImportQuota = Depends(enforce_import_quota)


# Broker exports are a few hundred KB; the largest real one (a multi-year IBKR
# CSV) is under 5 MB. Past this it is not a broker report, and it used to be
# read whole into memory before anyone looked at it.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

T = TypeVar("T")


def _require_suffix(upload: UploadFile, suffix: str, detail: str) -> None:
    if not upload.filename or not upload.filename.lower().endswith(suffix):
        raise HTTPException(status_code=400, detail=detail)


def _spool(upload: UploadFile, suffix: str) -> Path:
    """Copy the upload to a temp file in chunks, refusing anything over MAX_UPLOAD_BYTES."""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    path = Path(tmp.name)
    copied = 0
    try:
        while chunk := upload.file.read(1 << 20):
            copied += len(chunk)
            if copied > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"El archivo supera el tamaño máximo de {MAX_UPLOAD_BYTES >> 20} MB",
                )
            tmp.write(chunk)
    except BaseException:
        tmp.close()
        path.unlink(missing_ok=True)
        raise
    tmp.close()
    return path


def _run_import(kind: str, parse: Callable[[], T], store: Callable[[T], dict]) -> dict:
    """Parse, then store — and tell the two failures apart.

    A parse failure is the user's file: 422 with the parser's message, as before.
    A failure after parsing is ours (DB, locks, FIFO): every route used to fold it
    into the same 422 with ``str(e)`` and no server log, so a FIFO bug looked like
    a bad PDF to the user and left nothing to debug. Now it is a logged 500.
    """
    try:
        report = parse()
    except Exception as e:
        logger.warning("Upload rejected: %s could not be parsed: %s", kind, e)
        raise HTTPException(status_code=422, detail=f"Error al procesar {kind}: {e}")
    try:
        return store(report)
    except Exception:
        logger.exception("Import of %s failed after parsing", kind)
        raise HTTPException(
            status_code=500,
            detail="Error interno al guardar la importación. Inténtalo de nuevo más tarde.",
        )


@router.post("/tr", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos PDF o CSV"}, 413: {"description": "Archivo demasiado grande"}, 422: {"description": "Error al procesar el archivo"}})
def upload_tr_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload a Trade Republic Tax Report PDF or Transaction export CSV.

    PDF → full year-end tax report (capital gains, holdings, casillas).
    CSV → running transaction ledger across all years (idempotent, dedups
    against already-imported TR transactions).
    """
    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        is_csv = False
    elif name.endswith(".csv"):
        is_csv = True
    else:
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF o CSV")

    path = _spool(file, ".csv" if is_csv else ".pdf")
    try:
        if is_csv:
            return _run_import(
                "el CSV",
                lambda: parse_tr_csv(path),
                lambda r: import_tr_csv_report(db, r, tr_csv_compute_hash(path), file.filename, user_id=user.id),
            )
        return _run_import(
            "el PDF",
            lambda: parse_tr_tax_report(path),
            lambda r: import_tr_report(db, r, compute_file_hash(path), file.filename, user_id=user.id),
        )
    finally:
        path.unlink(missing_ok=True)


@router.post("/degiro", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos PDF"}, 413: {"description": "Archivo demasiado grande"}, 422: {"description": "Error al procesar el PDF"}})
def upload_dg_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload a DEGIRO Annual Report PDF."""
    _require_suffix(file, ".pdf", "Solo se aceptan archivos PDF")
    path = _spool(file, ".pdf")
    try:
        return _run_import(
            "el PDF",
            lambda: parse_dg_annual_report(path),
            lambda r: import_dg_report(db, r, dg_compute_hash(path), file.filename, user_id=user.id),
        )
    finally:
        path.unlink(missing_ok=True)


@router.post("/ibkr", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos CSV"}, 413: {"description": "Archivo demasiado grande"}, 422: {"description": "Error al procesar el CSV"}})
def upload_ibkr_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload an IBKR Activity Statement CSV."""
    _require_suffix(file, ".csv", "Solo se aceptan archivos CSV")
    path = _spool(file, ".csv")
    try:
        return _run_import(
            "el CSV",
            lambda: parse_ibkr_activity_statement(path),
            lambda r: import_ibkr_report(db, r, ibkr_compute_hash(path), file.filename, user_id=user.id),
        )
    finally:
        path.unlink(missing_ok=True)


@router.post("/ing", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos PDF"}, 413: {"description": "Archivo demasiado grande"}, 422: {"description": "Error al procesar el PDF"}})
def upload_ing_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload an ING Información Fiscal PDF."""
    _require_suffix(file, ".pdf", "Solo se aceptan archivos PDF")
    path = _spool(file, ".pdf")
    try:
        return _run_import(
            "el PDF",
            lambda: parse_ing_report(path),
            lambda r: import_ing_report(db, r, ing_compute_hash(path), file.filename, user_id=user.id),
        )
    finally:
        path.unlink(missing_ok=True)


@router.post("/bbva", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos PDF"}, 413: {"description": "Archivo demasiado grande"}, 422: {"description": "Error al procesar los PDFs"}})
def upload_bbva_reports(files: Annotated[list[UploadFile], File(description="1-3 BBVA PDFs")], db: DbSession, user: CurrentUser):
    """Upload 1-3 BBVA PDFs (operaciones, dividendos, patrimonio)."""
    if not files or len(files) > 3:
        raise HTTPException(status_code=400, detail="Se aceptan entre 1 y 3 archivos PDF de BBVA")
    for f in files:
        _require_suffix(f, ".pdf", f"Solo se aceptan archivos PDF: {f.filename}")

    paths: list[Path] = []
    try:
        for f in files:
            paths.append(_spool(f, ".pdf"))
        filenames = ", ".join(f.filename or "unknown" for f in files)
        return _run_import(
            "los PDFs de BBVA",
            lambda: parse_bbva_pdfs(paths),
            lambda r: import_bbva_report(db, r, bbva_compute_hash(paths), filenames, user_id=user.id),
        )
    finally:
        for p in paths:
            p.unlink(missing_ok=True)


@router.post("/etoro", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos XLSX"}, 413: {"description": "Archivo demasiado grande"}, 422: {"description": "Error al procesar el XLSX"}})
def upload_etoro_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload an eToro annual account statement XLSX."""
    _require_suffix(file, ".xlsx", "Solo se aceptan archivos XLSX")
    path = _spool(file, ".xlsx")
    try:
        return _run_import(
            "el XLSX de eToro",
            lambda: parse_etoro_statement(path),
            lambda r: import_etoro_report(db, r, etoro_compute_hash(path), file.filename, user_id=user.id),
        )
    finally:
        path.unlink(missing_ok=True)


@router.get("", response_model=list[ImportRecordOut], include_in_schema=False)
@router.get("/", response_model=list[ImportRecordOut])
def list_imports(db: DbSession, user: CurrentUser):
    """List all import records."""
    return (
        db.query(ImportRecord)
        .join(Account)
        .filter(Account.user_id == user.id)
        .order_by(ImportRecord.imported_at.desc())
        .all()
    )


@router.delete("/all")
def delete_all_imports_endpoint(db: DbSession, user: CurrentUser):
    """Delete all imports and associated data for the current user."""
    result = delete_all_imports(db, user.id)
    db.commit()
    return {"status": "deleted", "deleted_imports": result["deleted_imports"]}


@router.delete("/{import_id}", responses={404: {"description": "Importación no encontrada"}})
def delete_import(import_id: int, db: DbSession, user: CurrentUser):
    """Delete an import and all its associated data."""
    record = (
        db.query(ImportRecord)
        .join(Account)
        .filter(ImportRecord.id == import_id, Account.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Importación no encontrada")
    _delete_import_data(db, import_id)
    db.commit()
    return {"status": "deleted", "message": f"Importación {import_id} eliminada"}


# ---------------------------------------------------------------------------
# Data issues endpoints
# ---------------------------------------------------------------------------


@router.get("/issues", response_model=list[DataIssueOut])
def list_issues(db: DbSession, user: CurrentUser, status: str | None = None, import_id: int | None = None):
    """List data quality issues, optionally filtered by status or import."""
    q = (
        db.query(DataIssue)
        .outerjoin(ImportRecord, DataIssue.import_id == ImportRecord.id)
        .outerjoin(Account, ImportRecord.account_id == Account.id)
        .filter(
            and_(
                DataIssue.user_id == user.id,
                or_(DataIssue.import_id.is_(None), Account.user_id == user.id),
            )
        )
        .order_by(DataIssue.created_at.desc())
    )
    if status:
        q = q.filter(DataIssue.status == status)
    if import_id:
        q = q.filter(DataIssue.import_id == import_id)
    return q.all()


@router.post("/issues/{issue_id}/resolve", response_model=DataIssueOut)
def resolve_issue(issue_id: int, body: ResolveIssueRequest, db: DbSession, user: CurrentUser):
    """Resolve a pending data issue, applying the appropriate data correction."""
    from datetime import date as date_type
    from decimal import Decimal
    from backend.services.issue_resolver import (
        resolve_add_buy,
        resolve_apply_split,
        resolve_set_ticker,
        resolve_zero_price,
    )

    issue = (
        db.query(DataIssue)
        .outerjoin(ImportRecord, DataIssue.import_id == ImportRecord.id)
        .outerjoin(Account, ImportRecord.account_id == Account.id)
        .filter(
            DataIssue.id == issue_id,
            and_(
                DataIssue.user_id == user.id,
                or_(DataIssue.import_id.is_(None), Account.user_id == user.id),
            ),
        )
        .first()
    )
    if not issue:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    if issue.status not in ("pending", "needs_input"):
        raise HTTPException(status_code=400, detail=f"La incidencia ya está en estado '{issue.status}'")

    try:
        if body.action == "dismiss":
            issue.status = "dismissed"
        elif body.action == "set_price":
            if not body.data or "price" not in body.data:
                raise HTTPException(400, "Se requiere 'price' en data")
            resolve_zero_price(db, issue, Decimal(str(body.data["price"])))
        elif body.action == "add_buy":
            if not body.data or not all(k in body.data for k in ("qty", "price", "acquisition_date")):
                raise HTTPException(400, "Se requieren 'qty', 'price' y 'acquisition_date' en data")
            resolve_add_buy(
                db, issue,
                qty=Decimal(str(body.data["qty"])),
                price=Decimal(str(body.data["price"])),
                acquisition_date=date_type.fromisoformat(str(body.data["acquisition_date"])),
            )
        elif body.action == "set_ticker":
            if not body.data or "ticker" not in body.data:
                raise HTTPException(400, "Se requiere 'ticker' en data")
            resolve_set_ticker(db, issue, str(body.data["ticker"]))
        elif body.action == "apply_split":
            resolve_apply_split(db, issue)
        else:
            raise HTTPException(status_code=400, detail=f"Acción no válida: {body.action}")
    except HTTPException:
        raise
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    return issue


@router.post("/audit", response_model=list[DataIssueOut])
def run_full_audit(db: DbSession, user: CurrentUser):
    """Run the data supervisor on all existing data (full audit)."""
    from backend.services.data_supervisor import run_checks

    issues = run_checks(db, import_id=None, user_id=user.id)
    db.commit()
    return issues
