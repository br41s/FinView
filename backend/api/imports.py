"""API endpoints for file import."""

import tempfile
from pathlib import Path
from typing import Annotated

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


@router.post("/tr", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos PDF o CSV"}, 422: {"description": "Error al procesar el archivo"}})
def upload_tr_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload a Trade Republic Tax Report PDF or Transaction export CSV.

    PDF → full year-end tax report (capital gains, holdings, casillas).
    CSV → running transaction ledger across all years (idempotent, dedups
    against already-imported TR transactions).
    """
    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        is_csv = False
        suffix = ".pdf"
    elif name.endswith(".csv"):
        is_csv = True
        suffix = ".csv"
    else:
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF o CSV")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        if is_csv:
            file_hash = tr_csv_compute_hash(tmp_path)
            report = parse_tr_csv(tmp_path)
            result = import_tr_csv_report(db, report, file_hash, file.filename, user_id=user.id)
        else:
            file_hash = compute_file_hash(tmp_path)
            report = parse_tr_tax_report(tmp_path)
            result = import_tr_report(db, report, file_hash, file.filename, user_id=user.id)
        return result
    except Exception as e:
        kind = "CSV" if is_csv else "PDF"
        raise HTTPException(status_code=422, detail=f"Error al procesar el {kind}: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/degiro", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos PDF"}, 422: {"description": "Error al procesar el PDF"}})
def upload_dg_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload a DEGIRO Annual Report PDF."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        file_hash = dg_compute_hash(tmp_path)
        report = parse_dg_annual_report(tmp_path)
        result = import_dg_report(db, report, file_hash, file.filename, user_id=user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/ibkr", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos CSV"}, 422: {"description": "Error al procesar el CSV"}})
def upload_ibkr_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload an IBKR Activity Statement CSV."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos CSV")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        file_hash = ibkr_compute_hash(tmp_path)
        report = parse_ibkr_activity_statement(tmp_path)
        result = import_ibkr_report(db, report, file_hash, file.filename, user_id=user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el CSV: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/ing", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos PDF"}, 422: {"description": "Error al procesar el PDF"}})
def upload_ing_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload an ING Información Fiscal PDF."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        file_hash = ing_compute_hash(tmp_path)
        report = parse_ing_report(tmp_path)
        result = import_ing_report(db, report, file_hash, file.filename, user_id=user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/bbva", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos PDF"}, 422: {"description": "Error al procesar los PDFs"}})
def upload_bbva_reports(files: Annotated[list[UploadFile], File(description="1-3 BBVA PDFs")], db: DbSession, user: CurrentUser):
    """Upload 1-3 BBVA PDFs (operaciones, dividendos, patrimonio)."""
    if not files or len(files) > 3:
        raise HTTPException(status_code=400, detail="Se aceptan entre 1 y 3 archivos PDF de BBVA")
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Solo se aceptan archivos PDF: {f.filename}")

    tmp_paths: list[Path] = []
    try:
        for f in files:
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            content = f.file.read()
            tmp.write(content)
            tmp.close()
            tmp_paths.append(Path(tmp.name))

        file_hash = bbva_compute_hash(tmp_paths)
        report = parse_bbva_pdfs(tmp_paths)
        filenames = ", ".join(f.filename or "unknown" for f in files)
        result = import_bbva_report(db, report, file_hash, filenames, user_id=user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar los PDFs de BBVA: {e}")
    finally:
        for p in tmp_paths:
            p.unlink(missing_ok=True)


@router.post("/etoro", dependencies=[ImportQuota], response_model=ImportResult, responses={403: {"description": "Límite de importaciones del plan alcanzado"}, 400: {"description": "Solo se aceptan archivos XLSX"}, 422: {"description": "Error al procesar el XLSX"}})
def upload_etoro_report(file: UploadFile, db: DbSession, user: CurrentUser):
    """Upload an eToro annual account statement XLSX."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos XLSX")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        file_hash = etoro_compute_hash(tmp_path)
        report = parse_etoro_statement(tmp_path)
        result = import_etoro_report(db, report, file_hash, file.filename, user_id=user.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el XLSX de eToro: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


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
