# 💰 Dashboard de Análise Financeira

Dashboard em **Python + Streamlit + Pandas + Plotly** que funciona com **qualquer planilha de gastos** (`.xlsx` ou `.csv`), sem depender de nomes ou da ordem das colunas.

## Como usar (Windows)

1. Instale o [Python 3.10+](https://www.python.org/downloads/) marcando **"Add python.exe to PATH"**.
2. Dê **dois cliques em `iniciar_dashboard.bat`**.
   - Na primeira vez ele cria um ambiente isolado (`.venv`) e instala `streamlit`, `pandas`, `plotly` e `openpyxl` — leva 1–2 minutos.
   - Nas próximas vezes só verifica e abre o navegador direto.
3. Arraste sua planilha para a página. **Pronto** — o dashboard descobre sozinho a aba, a linha dos títulos e quais colunas são Data, Valor, Categoria e Descrição.
   Se algum número parecer errado, abra o painel **⚙️ Algo errado nos números?** para corrigir manualmente.

Para encerrar, feche a janela preta do terminal.

## Funcionalidades

| Recurso | Detalhes |
|---|---|
| Upload | `.xlsx` (com escolha de aba) e `.csv` (separador `;` `,` tab ou `\|` e codificação detectados) |
| Detecção automática | Aba, linha do cabeçalho e colunas detectadas por nome **e** por conteúdo; ajuste manual opcional |
| Planilhas com título | Linhas de título/vazias no topo são puladas automaticamente |
| Limpeza de valores | `R$ 1.234,56`, `$1,234.56`, `-50,00`, `(50,00)`, `50,00-`, células vazias; formato BR/US detectado pela coluna inteira |
| Limpeza de datas | Datas do Excel, números seriais, `dd/mm/aaaa`, `aaaa-mm-dd`, `mm/dd/aaaa`, `15 de março de 2026`, `05/abr/2026` |
| Extratos bancários | Se houver valores positivos e negativos, separa entradas de saídas automaticamente |
| KPIs | Total de despesas, média diária, nº de lançamentos, maior categoria |
| Gráficos | Barras horizontais por categoria (ordenadas, com "Outras") e tendência temporal por dia/semana/mês com média móvel |
| Filtros | Período e categorias |
| Auditoria | Tabela de linhas ignoradas e o motivo; download do CSV limpo |

## Estrutura

```
dashboard_financeiro/
├── app.py                  # Interface Streamlit
├── limpeza.py              # Leitura, mapeamento e limpeza (sem nomes de colunas fixos)
├── iniciar_dashboard.bat   # Atalho de dois cliques para Windows
├── requirements.txt
├── .streamlit/config.toml
├── exemplos/               # 3 planilhas com layouts diferentes para testar
└── tests/test_limpeza.py
```

## Rodar manualmente / testes

```bash
pip install -r requirements.txt
streamlit run app.py
```

```bash
pip install pytest
python -m pytest tests
```
