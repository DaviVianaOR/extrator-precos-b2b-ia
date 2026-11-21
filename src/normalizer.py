"""Higienização estruturada, validação estrita com Pydantic e categorização híbrida."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

load_dotenv()

CANONICAL_CATEGORIES = [
    "Hardware & TI",
    "Redes & Conectividade",
    "Energia & Nobreaks",
    "Ferramentas Industriais",
    "EPI & Segurança",
    "Periféricos & Escritório",
    "Outros B2B",
]

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Hardware & TI": (
        "notebook",
        "servidor",
        "server",
        "xeon",
        "ssd",
        "thinkpad",
        "latitude",
        "desktop",
        "workstation",
        "cpu",
    ),
    "Redes & Conectividade": (
        "switch",
        "roteador",
        "router",
        "access point",
        "wifi",
        "wi-fi",
        "unifi",
        "cisco",
        "gigabit",
        "poe",
        "firewall",
    ),
    "Energia & Nobreaks": (
        "nobreak",
        "ups",
        "estabilizador",
        "bateria",
        "senoidal",
        "bivolt",
        "va",
        "energia",
    ),
    "Ferramentas Industriais": (
        "parafusadeira",
        "furadeira",
        "esmerilhadeira",
        "makita",
        "bosch",
        "serra",
        "ferramenta",
        "brushless",
        "industrial",
    ),
    "EPI & Segurança": (
        "capacete",
        "luva",
        "epi",
        "anticorte",
        "segurança",
        "óculos",
        "botina",
        "protetor",
        "ca ",
    ),
    "Periféricos & Escritório": (
        "monitor",
        "teclado",
        "mouse",
        "headset",
        "webcam",
        "logitech",
        "periférico",
        "impressora",
    ),
}


def get_ai_provider() -> str:
    """Detecta automaticamente se há chave OpenAI ou Gemini configurada no ambiente."""
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "gemini"
    return "offline"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def parse_brl_price(raw: str | float | int | None) -> float | None:
    """Converte strings de preço (ex: 'R$ 5.790,90 / un') para float positivo."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return round(float(raw), 2) if raw > 0 else None

    text = raw.strip()
    if not text:
        return None

    match = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+(?:\.\d{2})?)", text)
    if not match:
        return None

    number_str = match.group(1)
    if "," in number_str:
        number_str = number_str.replace(".", "").replace(",", ".")

    try:
        value = round(float(number_str), 2)
    except ValueError:
        return None
    return value if value > 0 else None


def parse_stock(raw: str) -> tuple[str, int]:
    """Normaliza status de estoque e quantidade disponível."""
    text = _clean_text(raw)
    lower = text.lower()
    qty_match = re.search(r"(\d+)", lower)
    qty = int(qty_match.group(1)) if qty_match else 0

    if "indispon" in lower or "esgotado" in lower or "sem estoque" in lower:
        return "Indisponível", 0
    if "encomenda" in lower:
        return "Sob encomenda", 0
    if "baixo" in lower or (0 < qty <= 5):
        return "Estoque baixo", qty
    if "estoque" in lower or qty > 0:
        return "Em estoque", qty
    return "Não informado", 0


def parse_moq(raw: str) -> int:
    """Extrai o pedido mínimo (MOQ) garantindo valor inteiro >= 1."""
    match = re.search(r"(\d+)", raw or "")
    if not match:
        return 1
    value = int(match.group(1))
    return value if value >= 1 else 1


def categorize_heuristic(titulo: str, descricao: str = "", sku: str = "") -> str:
    """Classifica o item B2B de forma 100% offline via pontuação de palavras-chave."""
    haystack = f"{titulo} {descricao} {sku}".lower()
    best_category = "Outros B2B"
    best_score = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in haystack)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category


def _categorize_with_llm(titulo: str, descricao: str, provider: str) -> str | None:
    """Tenta categorizar via OpenAI ou Gemini quando a API key estiver configurada."""
    prompt = (
        "Classifique o produto B2B abaixo em EXATAMENTE uma das categorias: "
        f"{', '.join(CANONICAL_CATEGORIES)}. "
        "Responda apenas com o nome exato da categoria.\n"
        f"Produto: {titulo}\nDescrição: {descricao}"
    )
    try:
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 25,
                },
                timeout=8.0,
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"].strip()
        elif provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
            resp = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=8.0,
            )
            resp.raise_for_status()
            answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            return None
    except Exception:
        return None

    for canonical in CANONICAL_CATEGORIES:
        if canonical.lower() in answer.lower():
            return canonical
    return None


class ProdutoB2B(BaseModel):
    """Schema validado de produto B2B pronto para precificação e BI."""

    sku: str = Field(..., min_length=2)
    titulo: str = Field(..., min_length=3)
    fornecedor: str = Field(default="Não informado")
    categoria: str = Field(default="Outros B2B")
    preco_unitario: float = Field(..., gt=0)
    preco_anterior: float | None = Field(default=None, gt=0)
    desconto_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    status_estoque: str = Field(default="Não informado")
    quantidade_estoque: int = Field(default=0, ge=0)
    pedido_minimo: int = Field(default=1, ge=1)
    ticket_minimo_lote: float = Field(default=0.0, ge=0.0)
    alerta_monitoramento: str = Field(default="Normal")
    url: str = Field(default="")
    origem: str = Field(default="local")
    modo_classificacao: str = Field(default="heuristico")

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", "-", value.strip()).upper()
        if len(cleaned) < 2:
            raise ValueError("SKU deve ter ao menos 2 caracteres.")
        return cleaned

    @field_validator("titulo", "fornecedor", "origem")
    @classmethod
    def clean_strings(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("categoria")
    @classmethod
    def validate_category(cls, value: str) -> str:
        cleaned = _clean_text(value)
        return cleaned if cleaned in CANONICAL_CATEGORIES else "Outros B2B"


class RegistroRejeitado(BaseModel):
    """Registro descartado durante a validação estrita (ex.: preço 'Sob consulta')."""

    sku: str
    titulo: str
    preco_bruto: str
    motivo: str


class ResultadoNormalizacao(BaseModel):
    """Resultado consolidado da etapa de higienização."""

    produtos_validos: list[ProdutoB2B]
    registros_rejeitados: list[RegistroRejeitado]
    provedor_ia: str


def _compute_alert(desconto_pct: float, status_estoque: str) -> str:
    if status_estoque == "Indisponível":
        return "Sem Estoque"
    if status_estoque == "Estoque baixo":
        return "Risco de Ruptura"
    if desconto_pct >= 15.0:
        return "Oportunidade (Desconto >= 15%)"
    return "Normal"


def normalize_products(
    raw_items: list[dict[str, Any]], use_llm: bool = True
) -> ResultadoNormalizacao:
    """Valida, higieniza e categoriza itens brutos retornando válidos e rejeitados."""
    provider = get_ai_provider() if use_llm else "offline"
    valid_items: list[ProdutoB2B] = []
    rejected_items: list[RegistroRejeitado] = []

    for item in raw_items:
        sku = _clean_text(str(item.get("sku", "")))
        titulo = _clean_text(str(item.get("titulo", "")))
        descricao = _clean_text(str(item.get("descricao", "")))
        fornecedor = _clean_text(str(item.get("fornecedor", ""))) or "Não informado"
        preco_bruto = str(item.get("preco_bruto", "")).strip()
        preco_anterior_bruto = str(item.get("preco_anterior_bruto", "")).strip()

        preco_unitario = parse_brl_price(preco_bruto)
        preco_anterior = parse_brl_price(preco_anterior_bruto)

        if preco_unitario is None:
            rejected_items.append(
                RegistroRejeitado(
                    sku=sku.upper() or "SEM-SKU",
                    titulo=titulo or "Produto sem título",
                    preco_bruto=preco_bruto or "(vazio)",
                    motivo="Preço unitário inválido ou 'Sob consulta'",
                )
            )
            continue

        desconto_pct = 0.0
        if preco_anterior and preco_anterior > preco_unitario:
            desconto_pct = round(((preco_anterior - preco_unitario) / preco_anterior) * 100, 1)

        status_estoque, quantidade_estoque = parse_stock(str(item.get("estoque_bruto", "")))
        pedido_minimo = parse_moq(str(item.get("moq_bruto", "")))
        ticket_minimo_lote = round(preco_unitario * pedido_minimo, 2)

        categoria_llm = (
            _categorize_with_llm(titulo, descricao, provider) if provider != "offline" else None
        )
        if categoria_llm:
            categoria = categoria_llm
            modo = f"ia:{provider}"
        else:
            categoria = categorize_heuristic(titulo, descricao, sku)
            modo = "heuristico"

        alerta = _compute_alert(desconto_pct, status_estoque)

        try:
            produto = ProdutoB2B(
                sku=sku,
                titulo=titulo,
                fornecedor=fornecedor,
                categoria=categoria,
                preco_unitario=preco_unitario,
                preco_anterior=preco_anterior,
                desconto_pct=desconto_pct,
                status_estoque=status_estoque,
                quantidade_estoque=quantidade_estoque,
                pedido_minimo=pedido_minimo,
                ticket_minimo_lote=ticket_minimo_lote,
                alerta_monitoramento=alerta,
                url=str(item.get("url", "")).strip(),
                origem=str(item.get("origem", "local")).strip() or "local",
                modo_classificacao=modo,
            )
            valid_items.append(produto)
        except ValidationError as exc:
            rejected_items.append(
                RegistroRejeitado(
                    sku=sku.upper() or "SEM-SKU",
                    titulo=titulo or "Produto sem título",
                    preco_bruto=preco_bruto,
                    motivo=exc.errors()[0]["msg"],
                )
            )

    return ResultadoNormalizacao(
        produtos_validos=valid_items,
        registros_rejeitados=rejected_items,
        provedor_ia=provider,
    )
