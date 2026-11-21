"""Extração de catálogos B2B a partir de HTML local, upload sanitizado ou URL externa."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag

ALLOWED_HTML_EXTENSIONS = {".html", ".htm"}
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def validate_html_filename(filename: str) -> str:
    """Sanitiza o nome do arquivo com os.path.basename e valida extensão HTML."""
    safe_name = os.path.basename(filename or "").strip()
    if not safe_name:
        raise ValueError("Nome de arquivo vazio ou inválido.")
    _, ext = os.path.splitext(safe_name)
    if ext.lower() not in ALLOWED_HTML_EXTENSIONS:
        raise ValueError(
            f"Extensão não permitida: '{ext or '(sem extensão)'}'. "
            "Envie apenas arquivos .html ou .htm."
        )
    return safe_name


def validate_url(url: str) -> str:
    """Valida se a URL usa protocolo HTTP/HTTPS e possui host válido."""
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL inválida. Utilize um endereço completo com http:// ou https://.")
    return cleaned


def _extract_text(node: Tag, selectors: list[str]) -> str:
    for selector in selectors:
        found = node.select_one(selector)
        if found:
            text = found.get_text(" ", strip=True)
            if text:
                return text
    return ""


def _extract_href(node: Tag, selectors: list[str]) -> str:
    for selector in selectors:
        found = node.select_one(selector)
        if found and found.has_attr("href"):
            return str(found["href"]).strip()
    return ""


def parse_catalog_html(html_content: str, source_label: str = "local") -> list[dict[str, str]]:
    """Extrai registros brutos de produtos B2B de um documento HTML."""
    soup = BeautifulSoup(html_content, "html.parser")
    cards = soup.select(".product-card")

    if not cards:
        cards = soup.select(
            "article, [itemtype*='Product'], .product, .product-item, .catalog-item"
        )

    raw_items: list[dict[str, str]] = []
    for idx, card in enumerate(cards, start=1):
        titulo = _extract_text(
            card,
            [".product-title", "h2", "h3", "[itemprop='name']", ".title", ".name"],
        )
        preco_bruto = _extract_text(
            card,
            [".price", "[itemprop='price']", ".current-price", ".preco"],
        )
        if not titulo and not preco_bruto:
            continue

        sku_attr = str(card.get("data-sku", "")).strip()
        sku = sku_attr or _extract_text(card, [".sku", "[itemprop='sku']"]) or f"ITEM-{idx:03d}"

        raw_items.append(
            {
                "sku": sku,
                "titulo": titulo,
                "fornecedor": _extract_text(
                    card, [".supplier", ".brand", "[itemprop='brand']", ".fornecedor"]
                ),
                "descricao": _extract_text(
                    card, [".description", "[itemprop='description']", "p"]
                ),
                "preco_bruto": preco_bruto,
                "preco_anterior_bruto": _extract_text(
                    card, [".old-price", ".list-price", ".preco-anterior", "del"]
                ),
                "estoque_bruto": _extract_text(
                    card, [".stock", ".availability", ".estoque"]
                ),
                "moq_bruto": _extract_text(card, [".moq", ".min-order", ".pedido-minimo"]),
                "url": _extract_href(card, [".product-url", "a[href]"]),
                "origem": source_label,
            }
        )

    return raw_items


def scrape_local_html(file_path: str | Path) -> list[dict[str, str]]:
    """Lê e extrai produtos de um arquivo HTML local."""
    path = Path(file_path)
    safe_name = validate_html_filename(path.name)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo HTML não encontrado: {path}")
    html_content = path.read_text(encoding="utf-8", errors="replace")
    return parse_catalog_html(html_content, source_label=safe_name)


def scrape_uploaded_bytes(filename: str, content: bytes) -> list[dict[str, str]]:
    """Extrai produtos de um upload HTML validando nome e extensão."""
    safe_name = validate_html_filename(filename)
    html_content = content.decode("utf-8", errors="replace")
    return parse_catalog_html(html_content, source_label=safe_name)


def scrape_url(url: str, timeout: float = 15.0) -> list[dict[str, str]]:
    """Faz requisição HTTP segura via httpx e extrai produtos do HTML retornado."""
    safe_url = validate_url(url)
    response = httpx.get(
        safe_url,
        timeout=timeout,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    )
    response.raise_for_status()
    return parse_catalog_html(response.text, source_label=safe_url)
