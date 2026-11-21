"""Testes automatizados do pipeline B2B: scraping, validação Pydantic e exportação Excel."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from src.exporter import export_to_excel_file
from src.normalizer import normalize_products, parse_brl_price
from src.scraper import (
    scrape_local_html,
    scrape_uploaded_bytes,
    validate_html_filename,
    validate_url,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_HTML = PROJECT_ROOT / "data" / "catalogo_demo.html"


def test_scrape_local_html_extracts_demo_catalog() -> None:
    raw_items = scrape_local_html(DEMO_HTML)
    assert len(raw_items) == 13
    assert raw_items[0]["sku"].strip() == "nb-dell-5440"
    assert "Latitude 5440" in raw_items[0]["titulo"]
    assert raw_items[-1]["preco_bruto"] == "Sob consulta"


def test_security_sanitization_filename_and_url() -> None:
    assert validate_html_filename("../../pasta/catalogo.HTML") == "catalogo.HTML"

    with pytest.raises(ValueError):
        validate_html_filename("malware.exe")

    with pytest.raises(ValueError):
        validate_url("file:///etc/passwd")

    with pytest.raises(ValueError):
        validate_url("javascript:alert(1)")

    assert validate_url("https://fornecedor.example.com/lista") == (
        "https://fornecedor.example.com/lista"
    )


def test_parse_brl_price_formats() -> None:
    assert parse_brl_price("R$ 5.790,90") == 5790.90
    assert parse_brl_price("R$ 74,90 / un") == 74.90
    assert parse_brl_price("Sob consulta") is None
    assert parse_brl_price("R$ 0,00") is None


def test_normalize_products_pydantic_and_categorization() -> None:
    raw_items = scrape_local_html(DEMO_HTML)
    resultado = normalize_products(raw_items, use_llm=False)

    assert resultado.provedor_ia == "offline"
    assert len(resultado.produtos_validos) == 12
    assert len(resultado.registros_rejeitados) == 1
    assert resultado.registros_rejeitados[0].sku == "SRV-HPE-DL380"

    by_sku = {p.sku: p for p in resultado.produtos_validos}

    dell = by_sku["NB-DELL-5440"]
    assert dell.categoria == "Hardware & TI"
    assert dell.preco_unitario == 5790.90
    assert dell.pedido_minimo == 2
    assert dell.ticket_minimo_lote == 11581.80
    assert dell.desconto_pct == 16.0
    assert dell.alerta_monitoramento == "Oportunidade (Desconto >= 15%)"

    cisco = by_sku["SW-CISCO-24P"]
    assert cisco.categoria == "Redes & Conectividade"
    assert cisco.alerta_monitoramento == "Risco de Ruptura"

    luva = by_sku["EPI-3M-LUVA"]
    assert luva.categoria == "EPI & Segurança"
    assert luva.alerta_monitoramento == "Sem Estoque"


def test_scrape_uploaded_bytes_and_export_excel(tmp_path: Path) -> None:
    html_bytes = DEMO_HTML.read_bytes()
    raw_items = scrape_uploaded_bytes("fornecedor/catalogo_demo.html", html_bytes)
    resultado = normalize_products(raw_items, use_llm=False)

    output_xlsx = tmp_path / "saida_b2b.xlsx"
    saved_path = export_to_excel_file(
        resultado.produtos_validos,
        output_xlsx,
        rejeitados=resultado.registros_rejeitados,
    )

    assert saved_path.is_file()
    wb = load_workbook(saved_path)
    assert wb.sheetnames == [
        "Produtos B2B",
        "Resumo por Categoria",
        "Quarentena (Rejeitados)",
    ]

    ws_data = wb["Produtos B2B"]
    assert ws_data.max_row == 13  # 1 cabeçalho + 12 produtos válidos
    assert ws_data["A2"].value == "NB-DELL-5440"
    assert ws_data["E2"].value == 5790.90

    ws_rej = wb["Quarentena (Rejeitados)"]
    assert ws_rej.max_row == 2  # 1 cabeçalho + 1 item "Sob consulta"
    assert ws_rej["A2"].value == "SRV-HPE-DL380"
