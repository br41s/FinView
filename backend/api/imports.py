"""API endpoints for file import."""

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, File

from backend.api.schemas import ImportRecordOut, ImportResult
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
from backend.models import ImportRecord
from backend.services.import_service import (
    import_bbva_report,
    import_dg_report,
    import_etoro_report,
    import_ibkr_report,
    import_ing_report,
    import_tr_report,
    _delete_import_data,
)

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/tr", response_model=ImportResult, responses={400: {"description": "Solo se aceptan archivos PDF"}, 422: {"description": "Error al procesar el PDF"}})
def upload_tr_report(file: UploadFile, db: DbSession):
    """Upload a Trade Republic Tax Report PDF."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    # Save to temp file for processing
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        file_hash = compute_file_hash(tmp_path)
        report = parse_tr_tax_report(tmp_path)
        result = import_tr_report(db, report, file_hash, file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/degiro", response_model=ImportResult, responses={400: {"description": "Solo se aceptan archivos PDF"}, 422: {"description": "Error al procesar el PDF"}})
def upload_dg_report(file: UploadFile, db: DbSession):
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
        result = import_dg_report(db, report, file_hash, file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/ibkr", response_model=ImportResult, responses={400: {"description": "Solo se aceptan archivos CSV"}, 422: {"description": "Error al procesar el CSV"}})
def upload_ibkr_report(file: UploadFile, db: DbSession):
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
        result = import_ibkr_report(db, report, file_hash, file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el CSV: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/ing", response_model=ImportResult, responses={400: {"description": "Solo se aceptan archivos PDF"}, 422: {"description": "Error al procesar el PDF"}})
def upload_ing_report(file: UploadFile, db: DbSession):
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
        result = import_ing_report(db, report, file_hash, file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/bbva", response_model=ImportResult, responses={400: {"description": "Solo se aceptan archivos PDF"}, 422: {"description": "Error al procesar los PDFs"}})
def upload_bbva_reports(files: Annotated[list[UploadFile], File(description="1-3 BBVA PDFs")], db: DbSession):
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
        result = import_bbva_report(db, report, file_hash, filenames)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar los PDFs de BBVA: {e}")
    finally:
        for p in tmp_paths:
            p.unlink(missing_ok=True)


@router.post("/etoro", response_model=ImportResult, responses={400: {"description": "Solo se aceptan archivos XLSX"}, 422: {"description": "Error al procesar el XLSX"}})
def upload_etoro_report(file: UploadFile, db: DbSession):
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
        result = import_etoro_report(db, report, file_hash, file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar el XLSX de eToro: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/", response_model=list[ImportRecordOut])
def list_imports(db: DbSession):
    """List all import records."""
    return db.query(ImportRecord).order_by(ImportRecord.imported_at.desc()).all()


@router.delete("/{import_id}", responses={404: {"description": "Importación no encontrada"}})
def delete_import(import_id: int, db: DbSession):
    """Delete an import and all its associated data."""
    record = db.query(ImportRecord).filter(ImportRecord.id == import_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Importación no encontrada")
    _delete_import_data(db, import_id)
    db.commit()
    return {"status": "deleted", "message": f"Importación {import_id} eliminada"}
