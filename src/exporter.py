"""Geração de planilhas Excel (.xlsx) formatadas para uso comercial com openpyxl."""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.normalizer import ProdutoB2B, RegistroRejeitado

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
BODY_FONT = Font(name="Calibri", size=10, color="1E293B")
THIN_BORDER = Border(
    left=Side(style="thin", color="D9E1F2"),
    right=Side(style="thin", color="D9E1F2"),
    top=Side(style="thin", color="D9E1F2"),
    bottom=Side(style="thin", color="D9E1F2"),
)

ALERT_FILLS = {
    "Oportunidade (Desconto >= 15%)": PatternFill(
        start_color="DCFCE7", end_color="DCFCE7", fill_type="solid"
    ),
    "Risco de Ruptura": PatternFill(
        start_color="FEF3C7", end_color="FEF3C7", fill_type="solid"
    ),
    "Sem Estoque": PatternFill(
        start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"
    ),
}

CURRENCY_FORMAT = 'R$ #,##0.00'
PERCENT_FORMAT = '0.0%'


def _style_header(ws, headers: list[str]) -> None:
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER
    ws.row_dimensions[1].height = 24
    ws.freeze_panes = "A2"


def _autofit_columns(ws, max_width: int = 44) -> None:
    for col_cells in ws.columns:
        col_letter = get_column_letter(col_cells[0].column)
        longest = max(len(str(cell.value or "")) for cell in col_cells)
        ws.column_dimensions[col_letter].width = min(max(longest + 4, 12), max_width)


def export_to_excel_bytes(
    produtos: list[ProdutoB2B],
    rejeitados: list[RegistroRejeitado] | None = None,
) -> bytes:
    """Gera o arquivo Excel (.xlsx) formatado em memória e retorna os bytes."""
    wb = Workbook()

    # Aba 1: Dados Higienizados
    ws_data = wb.active
    ws_data.title = "Produtos B2B"
    headers = [
        "SKU",
        "Produto",
        "Fornecedor",
        "Categoria",
        "Preço Unitário",
        "Preço Anterior",
        "Desconto",
        "Status Estoque",
        "Qtd. Estoque",
        "Pedido Mínimo",
        "Ticket Mín. Lote",
        "Alerta Monitoramento",
        "Origem",
    ]
    _style_header(ws_data, headers)

    for row_idx, item in enumerate(produtos, start=2):
        ws_data.append(
            [
                item.sku,
                item.titulo,
                item.fornecedor,
                item.categoria,
                item.preco_unitario,
                item.preco_anterior,
                item.desconto_pct / 100.0,
                item.status_estoque,
                item.quantidade_estoque,
                item.pedido_minimo,
                item.ticket_minimo_lote,
                item.alerta_monitoramento,
                item.origem,
            ]
        )
        for col_idx in range(1, len(headers) + 1):
            cell = ws_data.cell(row=row_idx, column=col_idx)
            cell.font = BODY_FONT
            cell.border = THIN_BORDER
            if col_idx in {5, 6, 11} and cell.value is not None:
                cell.number_format = CURRENCY_FORMAT
                cell.alignment = Alignment(horizontal="right")
            elif col_idx == 7:
                cell.number_format = PERCENT_FORMAT
                cell.alignment = Alignment(horizontal="right")
            elif col_idx in {9, 10}:
                cell.alignment = Alignment(horizontal="center")

        alert_fill = ALERT_FILLS.get(item.alerta_monitoramento)
        if alert_fill:
            ws_data.cell(row=row_idx, column=12).fill = alert_fill

    if produtos:
        ws_data.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(produtos) + 1}"
    _autofit_columns(ws_data)

    # Aba 2: Resumo por Categoria
    ws_summary = wb.create_sheet(title="Resumo por Categoria")
    summary_headers = [
        "Categoria",
        "Qtd. SKUs",
        "Preço Médio",
        "Menor Preço",
        "Maior Preço",
        "Desconto Médio",
        "Soma Ticket Mín. Lote",
    ]
    _style_header(ws_summary, summary_headers)

    grouped: dict[str, list[ProdutoB2B]] = defaultdict(list)
    for item in produtos:
        grouped[item.categoria].append(item)

    for row_idx, (cat, items) in enumerate(sorted(grouped.items()), start=2):
        prices = [p.preco_unitario for p in items]
        avg_discount = sum(p.desconto_pct for p in items) / len(items) / 100.0
        total_min_ticket = sum(p.ticket_minimo_lote for p in items)
        ws_summary.append(
            [
                cat,
                len(items),
                round(sum(prices) / len(prices), 2),
                min(prices),
                max(prices),
                avg_discount,
                round(total_min_ticket, 2),
            ]
        )
        for col_idx in range(1, len(summary_headers) + 1):
            cell = ws_summary.cell(row=row_idx, column=col_idx)
            cell.font = BODY_FONT
            cell.border = THIN_BORDER
            if col_idx in {3, 4, 5, 7}:
                cell.number_format = CURRENCY_FORMAT
                cell.alignment = Alignment(horizontal="right")
            elif col_idx == 6:
                cell.number_format = PERCENT_FORMAT
                cell.alignment = Alignment(horizontal="right")
            elif col_idx == 2:
                cell.alignment = Alignment(horizontal="center")

    _autofit_columns(ws_summary)

    # Aba 3: Quarentena (Rejeitados)
    if rejeitados:
        ws_rej = wb.create_sheet(title="Quarentena (Rejeitados)")
        rej_headers = ["SKU", "Produto", "Preço Bruto", "Motivo da Rejeição"]
        _style_header(ws_rej, rej_headers)
        for row_idx, rej in enumerate(rejeitados, start=2):
            ws_rej.append([rej.sku, rej.titulo, rej.preco_bruto, rej.motivo])
            for col_idx in range(1, len(rej_headers) + 1):
                cell = ws_rej.cell(row=row_idx, column=col_idx)
                cell.font = BODY_FONT
                cell.border = THIN_BORDER
        _autofit_columns(ws_rej)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def export_to_excel_file(
    produtos: list[ProdutoB2B],
    output_path: str | Path,
    rejeitados: list[RegistroRejeitado] | None = None,
) -> Path:
    """Salva o relatório Excel (.xlsx) no caminho informado."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(export_to_excel_bytes(produtos, rejeitados=rejeitados))
    return target
