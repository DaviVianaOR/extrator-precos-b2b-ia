# Extrator de Preços B2B com Validação e Governança de Dados

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?logo=streamlit&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![Testes](https://img.shields.io/badge/Pytest-5%20passed-2EA043)

Uma ferramenta feita para equipes de **Compras, Suprimentos e Pricing** que ainda gastam horas copiando tabelas de fornecedores na mão — lidando com preços despadronizados, descontos quebrados e itens sem valor definido.

> **Demonstração em vídeo (YouTube):** [Assista à demonstração completa](https://youtu.be/M8DxH0bcs5g)

---

## O problema que ele resolve

Quem trabalha com cotação B2B conhece o cenário: cada fornecedor envia um catálogo de um jeito. Um escreve `R$ 5.790,90 / un`, outro coloca `"Sob consulta"`, outro mistura lote mínimo com desconto no meio do texto. Jogar isso direto no Excel gera retrabalho e erros de negociação.

Este pipeline automatiza o processo do começo ao fim:
1. **Coleta flexível:** lê tanto arquivos HTML locais (ideal para catálogos baixados ou demonstrações offline) quanto URLs HTTP/HTTPS com validação de segurança.
2. **Validação estrita com Pydantic:** normaliza preços, percentuais de desconto, SKUs, fornecedores e calcula o ticket mínimo por lote automaticamente.
3. **Área de Quarentena (governança real):** registros incompletos, com preço inválido ou marcados como *"Sob consulta"* **não contaminam a planilha principal** — eles são isolados automaticamente na aba de quarentena para revisão humana rápida.
4. **Dashboard + Excel executivo em 1 clique:** permite filtrar em segundos por busca (marca/SKU), categoria, fornecedor ou status de estoque, e exporta um `.xlsx` formatado em **3 abas** (*Catálogo B2B*, *Resumo por Categoria* e *Quarentena*).

---

## Modo Demo Híbrido

O projeto funciona **100% offline** logo após o clone, usando um catálogo B2B realista em `data/catalogo_demo.html` e classificação heurística local. Caso você adicione `OPENAI_API_KEY` ou `GEMINI_API_KEY` no `.env`, a categorização semântica via LLM é ativada automaticamente com fallback seguro.

---

## Estrutura do projeto

```text
extrator-precos-b2b-ia/
├── app.py                     # Dashboard Streamlit com KPIs, filtros e download .xlsx
├── data/
│   └── catalogo_demo.html     # Catálogo B2B realista para demonstração offline
├── src/
│   ├── scraper.py             # Extração HTML (BeautifulSoup + httpx) com sanitização de entrada
│   ├── normalizer.py          # Schemas Pydantic v2, cálculo de lote/desconto e quarentena
│   └── exporter.py            # Exportação Excel (.xlsx) formatada com 3 abas via openpyxl
├── tests/
│   └── test_pipeline.py       # Testes de scraping local, Pydantic, quarentena e Excel
├── .env.example
├── requirements.txt
└── run.sh
```

---

## Como rodar na sua máquina

```bash
git clone git@github.com:DaviVianaOR/extrator-precos-b2b-ia.git
cd extrator-precos-b2b-ia
chmod +x run.sh
./run.sh
```

O `run.sh` prepara o `.venv` isolado, instala as dependências e inicia o dashboard automaticamente.

> **Opcional (categorização via LLM):** copie `.env.example` para `.env` e informe `OPENAI_API_KEY` ou `GEMINI_API_KEY`.

---

## Testes automatizados

```bash
.venv/bin/pytest -q
```

A suíte valida a extração do catálogo local, a rejeição de uploads/URLs inválidos, o isolamento de registros na quarentena e a estrutura real das 3 abas do arquivo `.xlsx` gerado.

---

## Licença

Distribuído sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
