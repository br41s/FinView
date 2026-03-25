"""API endpoints for file import."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.api.schemas import ImportRecordOut, ImportResult
from backend.database import get_db
from backend.importers.tr import compute_file_hash, parse_tr_tax_report
from backend.models import ImportRecord
from backend.services.import_service import import_tr_report

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/tr", response_model=ImportResult)
def upload_tr_report(file: UploadFile, db: Session = Depends(get_db)):
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


@router.get("/", response_model=list[ImportRecordOut])
def list_imports(db: Session = Depends(get_db)):
    """List all import records."""
    return db.query(ImportRecord).order_by(ImportRecord.imported_at.desc()).all()
