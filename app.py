"""Interface Streamlit para Extração B2B, Monitoramento de Preços e Exportação Excel."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.exporter import export_to_excel_bytes
from src.normalizer import (
    ProdutoB2B,
    ResultadoNormalizacao,
    get_ai_provider,
    normalize_products,
)
from src.scraper import scrape_local_html, scrape_uploaded_bytes, scrape_url

DEMO_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalogo_demo.html"

st.set_page_config(
    page_title="Extrator B2B & Monitoramento de Preços",
    page_icon="📊",
    layout="wide",
)


def _format_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _run_pipeline(
    source_mode: str,
    uploaded_file,
    target_url: str,
    use_llm: bool,
) -> ResultadoNormalizacao:
    if source_mode == "Catálogo Demo Local (Offline)":
        raw_items = scrape_local_html(DEMO_CATALOG_PATH)
    elif source_mode == "Upload de HTML (.html/.htm)":
        if uploaded_file is None:
            raise ValueError("Envie um arquivo .html ou .htm antes de executar a extração.")
        raw_items = scrape_uploaded_bytes(uploaded_file.name, uploaded_file.getvalue())
    else:
        raw_items = scrape_url(target_url)

    return normalize_products(raw_items, use_llm=use_llm)


def _filter_products(
    produtos: list[ProdutoB2B],
    categorias: list[str],
    fornecedores: list[str],
    status_list: list[str],
    faixa_preco: tuple[float, float],
    termo_busca: str,
) -> list[ProdutoB2B]:
    query = termo_busca.strip().lower()
    filtered: list[ProdutoB2B] = []
    for item in produtos:
        if categorias and item.categoria not in categorias:
            continue
        if fornecedores and item.fornecedor not in fornecedores:
            continue
        if status_list and item.status_estoque not in status_list:
            continue
        if not (faixa_preco[0] <= item.preco_unitario <= faixa_preco[1]):
            continue
        if query and query not in f"{item.sku} {item.titulo} {item.fornecedor}".lower():
            continue
        filtered.append(item)
    return filtered


def main() -> None:
    st.title("📊 Extrator B2B & Monitoramento de Preços")
    st.caption(
        "Coleta automatizada, higienização estruturada (Pydantic), alertas de estoque/desconto "
        "e exportação executiva em Excel (.xlsx)."
    )

    provider = get_ai_provider()
    provider_label = {
        "openai": "IA Ativa (OpenAI)",
        "gemini": "IA Ativa (Gemini)",
        "offline": "Modo Demo Offline (Motor Heurístico Local)",
    }[provider]

    with st.sidebar:
        st.header("⚙️ Fonte de Dados")
        st.info(f"**Motor:** {provider_label}")

        source_mode = st.radio(
            "Selecione a origem do catálogo:",
            options=[
                "Catálogo Demo Local (Offline)",
                "Upload de HTML (.html/.htm)",
                "URL Externa (HTTP/HTTPS)",
            ],
            index=0,
        )

        uploaded_file = None
        target_url = ""
        if source_mode == "Upload de HTML (.html/.htm)":
            uploaded_file = st.file_uploader(
                "Arquivo HTML do fornecedor",
                type=["html", "htm"],
            )
        elif source_mode == "URL Externa (HTTP/HTTPS)":
            target_url = st.text_input(
                "URL do catálogo",
                placeholder="https://fornecedor.com.br/catalogo",
            )

        use_llm = st.checkbox(
            "Usar IA para categorização (se API key configurada)",
            value=provider != "offline",
            disabled=provider == "offline",
        )

        executar = st.button("🚀 Executar Extração", type="primary", use_container_width=True)

    if "resultado_b2b" not in st.session_state or executar:
        try:
            st.session_state["resultado_b2b"] = _run_pipeline(
                source_mode=source_mode,
                uploaded_file=uploaded_file,
                target_url=target_url,
                use_llm=use_llm,
            )
            st.session_state.pop("erro_pipeline", None)
        except Exception as exc:
            st.session_state["erro_pipeline"] = str(exc)

    if "erro_pipeline" in st.session_state:
        st.error(f"Erro na extração: {st.session_state['erro_pipeline']}")
        return

    resultado: ResultadoNormalizacao = st.session_state["resultado_b2b"]
    produtos = resultado.produtos_validos
    rejeitados = resultado.registros_rejeitados

    if not produtos:
        st.warning("Nenhum produto válido foi encontrado na fonte selecionada.")
        return

    # Filtros interativos
    st.subheader("🔍 Filtros de Análise")
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)

    all_categories = sorted({p.categoria for p in produtos})
    all_suppliers = sorted({p.fornecedor for p in produtos})
    all_status = sorted({p.status_estoque for p in produtos})
    min_price = min(p.preco_unitario for p in produtos)
    max_price = max(p.preco_unitario for p in produtos)

    with col_f1:
        sel_categories = st.multiselect("Categoria", all_categories, default=all_categories)
    with col_f2:
        sel_suppliers = st.multiselect("Fornecedor", all_suppliers, default=all_suppliers)
    with col_f3:
        sel_status = st.multiselect("Estoque", all_status, default=all_status)
    with col_f4:
        termo_busca = st.text_input("Buscar SKU / Produto", placeholder="Ex.: Dell, Cisco, EPI...")

    if min_price < max_price:
        faixa_preco = st.slider(
            "Faixa de Preço Unitário (R$)",
            min_value=float(min_price),
            max_value=float(max_price),
            value=(float(min_price), float(max_price)),
            step=10.0,
        )
    else:
        faixa_preco = (float(min_price), float(max_price))

    filtrados = _filter_products(
        produtos,
        categorias=sel_categories,
        fornecedores=sel_suppliers,
        status_list=sel_status,
        faixa_preco=faixa_preco,
        termo_busca=termo_busca,
    )

    # KPIs executivos
    st.divider()
    avg_price = sum(p.preco_unitario for p in filtrados) / len(filtrados) if filtrados else 0.0
    avg_discount = sum(p.desconto_pct for p in filtrados) / len(filtrados) if filtrados else 0.0
    oportunidades = sum(1 for p in filtrados if p.desconto_pct >= 15.0)
    alertas_estoque = sum(
        1 for p in filtrados if p.status_estoque in {"Estoque baixo", "Indisponível"}
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("SKUs Validados", len(filtrados), f"{len(rejeitados)} em quarentena")
    m2.metric("Preço Médio", _format_brl(avg_price))
    m3.metric("Desconto Médio", f"{avg_discount:.1f}%")
    m4.metric("Oportunidades (>=15%)", oportunidades)
    m5.metric("Alertas de Estoque", alertas_estoque)

    # Tabela principal
    st.subheader("📋 Catálogo Higienizado")
    rows = [
        {
            "SKU": p.sku,
            "Produto": p.titulo,
            "Fornecedor": p.fornecedor,
            "Categoria": p.categoria,
            "Preço Unit. (R$)": p.preco_unitario,
            "Preço Ant. (R$)": p.preco_anterior,
            "Desconto (%)": p.desconto_pct,
            "Estoque": p.status_estoque,
            "Qtd.": p.quantidade_estoque,
            "MOQ": p.pedido_minimo,
            "Ticket Mín. (R$)": p.ticket_minimo_lote,
            "Alerta": p.alerta_monitoramento,
        }
        for p in filtrados
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Exportação Excel formatado
    excel_bytes = export_to_excel_bytes(filtrados, rejeitados=rejeitados)
    st.download_button(
        label="⬇️ Baixar Relatório Excel (.xlsx)",
        data=excel_bytes,
        file_name="relatorio_b2b_precos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    if rejeitados:
        with st.expander(f"⚠️ Registros em Quarentena ({len(rejeitados)})"):
            st.dataframe(
                [r.model_dump() for r in rejeitados],
                use_container_width=True,
                hide_index=True,
            )


if __name__ == "__main__":
    main()
