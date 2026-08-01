"""Ensure only documents that actually contain holdings close a snapshot year."""

from pathlib import Path

from backend.importers import bbva, ing


def test_ing_operations_certificate_is_not_a_complete_snapshot(monkeypatch):
    monkeypatch.setattr(
        ing,
        "_extract_all_text",
        lambda _path: "Certificado de Operaciones Fecha inicio: 01/01/2024",
    )

    report = ing.parse_ing_report(Path("operations.pdf"))

    assert report.portfolio_snapshot_complete is False


def test_ing_fiscal_report_is_a_complete_snapshot(monkeypatch):
    monkeypatch.setattr(
        ing,
        "_extract_all_text",
        lambda _path: "Información Fiscal 2024 Cuenta de valores",
    )

    report = ing.parse_ing_report(Path("fiscal.pdf"))

    assert report.portfolio_snapshot_complete is True


def test_bbva_requires_patrimonio_document_for_complete_snapshot(monkeypatch):
    documents = {
        "operations.pdf": "Ejercicio: 2024 OPERACIONES DE VALORES",
        "holdings.pdf": "Ejercicio: 2024 PATRIMONIO EN VALORES",
    }
    monkeypatch.setattr(
        bbva,
        "_extract_all_text",
        lambda path: documents[path.name],
    )

    operations_only = bbva.parse_bbva_pdfs([Path("operations.pdf")])
    with_holdings = bbva.parse_bbva_pdfs([
        Path("operations.pdf"),
        Path("holdings.pdf"),
    ])

    assert operations_only.portfolio_snapshot_complete is False
    assert with_holdings.portfolio_snapshot_complete is True
