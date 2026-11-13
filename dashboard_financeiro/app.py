"""Dashboard de Análise Financeira — funciona com qualquer planilha de gastos.

Execute com:  streamlit run app.py   (ou dê dois cliques em iniciar_dashboard.bat)
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import limpeza as lp

st.set_page_config(page_title="Dashboard Financeiro", page_icon="💰", layout="wide")

COR_SERIE = "#2a78d6"   # azul — cor única para série única (barras e linha)
COR_MEDIA = "#898781"   # cinza neutro para a média móvel / referência
NENHUMA = "(nenhuma)"


def brl(v: float) -> str:
    """Formata número no padrão monetário brasileiro: R$ 1.234,56."""
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def rotulo_data(d: pd.Timestamp, granularidade: str, longo: bool = False) -> str:
    """Rótulos de data em português, independentes do idioma do sistema."""
    if granularidade == "Mês":
        return f"{MESES[d.month - 1]}/{d.year}"
    if granularidade == "Semana":
        return f"semana de {d:%d/%m/%Y}" if longo else f"{d.day:02d}/{MESES[d.month - 1]}"
    return f"{d:%d/%m/%Y}" if longo else f"{d.day:02d}/{MESES[d.month - 1]}"


def estilizar(fig: go.Figure, altura: int = 420) -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(font_size=13),
        separators=",.",  # vírgula decimal, ponto de milhar
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.18)", zeroline=False)
    return fig


@st.cache_data(show_spinner="Lendo arquivo…")
def carregar(conteudo: bytes, nome: str, aba, linha_cabecalho: int) -> pd.DataFrame:
    return lp.ler_arquivo(conteudo, nome, aba, linha_cabecalho)


# ---------------------------------------------------------------------------
# 1. Upload
# ---------------------------------------------------------------------------
st.title("💰 Dashboard de Análise Financeira")
st.caption("Envie qualquer planilha de gastos (.xlsx ou .csv) e indique na barra lateral o que cada coluna significa.")

arquivo = st.file_uploader("Arquivo de gastos", type=["xlsx", "xlsm", "csv", "txt"])

if arquivo is None:
    st.info(
        "👆 Faça upload de um arquivo para começar.\n\n"
        "O dashboard não depende de nomes de colunas fixos: depois do upload você escolhe, "
        "na barra lateral, qual coluna é a **Data**, o **Valor**, a **Categoria** e a **Descrição**."
    )
    st.stop()

conteudo = arquivo.getvalue()
eh_excel = arquivo.name.lower().endswith((".xlsx", ".xlsm"))

with st.sidebar:
    st.header("📄 Leitura do arquivo")
    aba = 0
    if eh_excel:
        try:
            abas = lp.listar_abas(conteudo)
        except Exception as e:  # arquivo corrompido / protegido
            st.error(f"Não consegui abrir o Excel: {e}")
            st.stop()
        aba = st.selectbox("Aba da planilha", abas) if len(abas) > 1 else abas[0]
    linha_cab = st.number_input(
        "Linha do cabeçalho", min_value=1, max_value=200, value=1,
        help="Número da linha onde estão os títulos das colunas (use se a planilha tiver um título ou linhas em branco no topo).",
    ) - 1

try:
    bruto = carregar(conteudo, arquivo.name, aba, int(linha_cab))
except Exception as e:
    st.error(f"Erro ao ler o arquivo: {e}")
    st.stop()

if bruto.empty or len(bruto.columns) < 2:
    st.warning("O arquivo parece vazio ou tem menos de 2 colunas. Verifique a aba e a linha do cabeçalho.")
    st.dataframe(bruto.head(20), width="stretch")
    st.stop()

# ---------------------------------------------------------------------------
# 2. Mapeamento dinâmico de colunas
# ---------------------------------------------------------------------------
colunas = list(bruto.columns)


def indice(sugestao: str | None, opcoes: list[str]) -> int:
    return opcoes.index(sugestao) if sugestao in opcoes else 0


with st.sidebar:
    st.header("🧭 Mapeamento de colunas")
    sug_data = lp.sugerir_coluna(colunas, "data", df=bruto)
    sug_valor = lp.sugerir_coluna(colunas, "valor", {sug_data}, df=bruto)
    sug_cat = lp.sugerir_coluna(colunas, "categoria", {sug_data, sug_valor}, df=bruto)
    sug_desc = lp.sugerir_coluna(colunas, "descricao", {sug_data, sug_valor, sug_cat}, df=bruto)

    col_data = st.selectbox("Qual coluna é a Data?", colunas, index=indice(sug_data, colunas))
    col_valor = st.selectbox(
        "Qual coluna é o Valor Monetário?", colunas,
        index=indice(sug_valor, colunas) if sug_valor else min(1, len(colunas) - 1),
    )
    opcoes_opc = [NENHUMA] + colunas
    col_cat = st.selectbox("Qual coluna é a Categoria?", opcoes_opc, index=indice(sug_cat, opcoes_opc))
    col_desc = st.selectbox("Qual coluna é a Descrição?", opcoes_opc, index=indice(sug_desc, opcoes_opc))

    with st.expander("⚙️ Opções de interpretação"):
        fmt_label = st.radio(
            "Formato dos números",
            ["Automático", "Brasileiro (1.234,56)", "Americano (1,234.56)"],
        )
        formato = {"Automático": lp.FORMATO_AUTO, "Brasileiro (1.234,56)": lp.FORMATO_BR}.get(fmt_label, lp.FORMATO_US)
        data_label = st.radio("Formato das datas", ["Automático", "Dia/Mês/Ano", "Mês/Dia/Ano"])
        dia_primeiro = {"Automático": None, "Dia/Mês/Ano": True}.get(data_label, False)
        _amostra = lp.limpar_valor(bruto[col_valor], formato)
        _misto = (_amostra < 0).any() and (_amostra > 0).any()
        # Extrato com entradas e saídas: o lado menos frequente costuma ser a receita
        _idx_sinal = (1 if (_amostra < 0).sum() >= (_amostra > 0).sum() else 2) if _misto else 0
        regra_sinal = st.radio(
            "Quais linhas são despesas?",
            [lp.SINAL_ABSOLUTO, lp.SINAL_NEGATIVOS, lp.SINAL_POSITIVOS],
            index=_idx_sinal,
            help="Útil para extratos bancários que misturam entradas e saídas. "
                 "Quando o arquivo tem valores positivos e negativos, a opção é pré-selecionada automaticamente.",
        )
    if _misto:
        st.caption("ℹ️ A coluna de valor tem positivos e negativos — interpretado como extrato com entradas e saídas.")

if col_data == col_valor:
    st.error("A coluna de **Data** e a de **Valor** precisam ser diferentes. Ajuste o mapeamento na barra lateral.")
    st.stop()

dados, descartados = lp.preparar_dados(
    bruto,
    col_data,
    col_valor,
    None if col_cat == NENHUMA else col_cat,
    None if col_desc == NENHUMA else col_desc,
    formato,
    dia_primeiro,
    regra_sinal,
)

if dados.empty:
    st.error(
        "Nenhuma linha válida após a limpeza. Confira se as colunas de Data e Valor estão mapeadas corretamente "
        "e, se necessário, ajuste o formato dos números/datas nas opções de interpretação."
    )
    with st.expander("Ver amostra do arquivo original"):
        st.dataframe(bruto.head(30), width="stretch")
    st.stop()

# ---------------------------------------------------------------------------
# 3. Filtros
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🔎 Filtros")
    dmin, dmax = dados["Data"].min().date(), dados["Data"].max().date()
    periodo = st.date_input("Período", value=(dmin, dmax), min_value=dmin, max_value=dmax, format="DD/MM/YYYY")
    categorias = sorted(dados["Categoria"].unique())
    cats_sel = st.multiselect("Categorias", categorias, placeholder="Todas")

ini, fim = (periodo if isinstance(periodo, (tuple, list)) and len(periodo) == 2 else (dmin, dmax))
filtro = dados["Data"].dt.date.between(ini, fim)
if cats_sel:
    filtro &= dados["Categoria"].isin(cats_sel)
df = dados[filtro]

if df.empty:
    st.warning("Nenhum gasto no período/categorias selecionados.")
    st.stop()

# ---------------------------------------------------------------------------
# 4a. KPIs
# ---------------------------------------------------------------------------
total = df["Valor"].sum()
dias = (pd.Timestamp(fim) - pd.Timestamp(ini)).days + 1
media_diaria = total / max(dias, 1)
por_cat = df.groupby("Categoria", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total de despesas", brl(total))
k2.metric("Média diária", brl(media_diaria), help=f"Total ÷ {dias} dias do período selecionado ({ini:%d/%m/%Y} a {fim:%d/%m/%Y}).")
k3.metric("Nº de lançamentos", f"{len(df):,}".replace(",", "."))
_top = por_cat.iloc[0]
k4.metric(f"Maior categoria: {_top['Categoria']}", brl(_top["Valor"]), help=f"{_top['Valor'] / total:.1%} do total no período.")

if len(descartados):
    st.caption(f"⚠️ {len(descartados)} linha(s) do arquivo foram ignoradas na limpeza — veja os detalhes no fim da página.")

st.divider()

# ---------------------------------------------------------------------------
# 4b. Barras horizontais por categoria
# ---------------------------------------------------------------------------
c_esq, c_dir = st.columns([5, 6], gap="large")

with c_esq:
    st.subheader("Gastos por categoria")
    top_n = st.slider("Quantidade de categorias exibidas", 3, max(3, min(30, len(por_cat))), min(10, max(3, len(por_cat)))) \
        if len(por_cat) > 3 else len(por_cat)
    plot_cat = por_cat.head(top_n).copy()
    restante = por_cat.iloc[top_n:]["Valor"].sum()
    if restante > 0:
        plot_cat = pd.concat([plot_cat, pd.DataFrame({"Categoria": ["Outras"], "Valor": [restante]})], ignore_index=True)
    plot_cat["Percentual"] = plot_cat["Valor"] / total
    plot_cat["Rótulo"] = plot_cat["Valor"].map(brl)

    fig_bar = px.bar(
        plot_cat.iloc[::-1],  # maior no topo
        x="Valor", y="Categoria", orientation="h", text="Rótulo",
        custom_data=["Rótulo", "Percentual"],
    )
    fig_bar.update_traces(
        marker_color=COR_SERIE, marker_line_width=0, width=0.7,
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>%{customdata[1]:.1%} do total<extra></extra>",
    )
    fig_bar.update_xaxes(title=None, showticklabels=False, range=[0, plot_cat["Valor"].max() * 1.3])
    fig_bar.update_yaxes(title=None, gridcolor="rgba(0,0,0,0)")
    st.plotly_chart(estilizar(fig_bar, altura=max(320, 34 * len(plot_cat) + 60)), width="stretch")

# ---------------------------------------------------------------------------
# 4c. Linha de tendência temporal
# ---------------------------------------------------------------------------
with c_dir:
    st.subheader("Tendência de gastos no tempo")
    granularidade = st.radio("Agrupar por", ["Dia", "Semana", "Mês"], index=2 if dias > 92 else (1 if dias > 31 else 0), horizontal=True)
    freq = {"Dia": "D", "Semana": "W-MON", "Mês": "MS"}[granularidade]
    serie = df.set_index("Data")["Valor"].resample(freq, label="left", closed="left").sum().reset_index()
    janela = {"Dia": 7, "Semana": 4, "Mês": 3}[granularidade]
    PLURAL = {"Dia": "dias", "Semana": "semanas", "Mês": "meses"}
    serie["Média móvel"] = serie["Valor"].rolling(janela, min_periods=1).mean()
    serie["Período"] = serie["Data"].map(lambda d: rotulo_data(d, granularidade, longo=True))
    serie["ValorTxt"] = serie["Valor"].map(brl)
    serie["MediaTxt"] = serie["Média móvel"].map(brl)

    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(
        x=serie["Data"], y=serie["Valor"], name="Gastos", mode="lines+markers",
        line=dict(color=COR_SERIE, width=2), marker=dict(size=8 if len(serie) <= 60 else 4),
        customdata=serie[["Período", "ValorTxt", "MediaTxt"]],
        hovertemplate="<b>%{customdata[0]}</b><br>Gastos: %{customdata[1]}<br>Média móvel: %{customdata[2]}<extra></extra>",
    ))
    if len(serie) > janela:
        fig_line.add_trace(go.Scatter(
            x=serie["Data"], y=serie["Média móvel"], name=f"Média móvel ({janela} {PLURAL[granularidade]})",
            mode="lines", line=dict(color=COR_MEDIA, width=2, dash="dot"), hoverinfo="skip",
        ))
    fig_line = estilizar(fig_line)
    fig_line.update_layout(showlegend=len(fig_line.data) > 1, legend=dict(orientation="h", y=1.08, x=0))
    fig_line.update_yaxes(title=None, tickprefix="R$ ", tickformat=",.0f", rangemode="tozero")
    passo = max(1, -(-len(serie) // 10))  # no máximo ~10 rótulos no eixo
    marcas = serie["Data"].iloc[::passo]
    fig_line.update_xaxes(tickvals=marcas, ticktext=[rotulo_data(d, granularidade) for d in marcas], tickangle=0)
    fig_line.update_xaxes(title=None, showspikes=True, spikemode="across", spikethickness=1, spikedash="solid", spikecolor="rgba(128,128,128,0.5)")
    st.plotly_chart(fig_line, width="stretch")

# ---------------------------------------------------------------------------
# 5. Tabelas de apoio
# ---------------------------------------------------------------------------
st.divider()
with st.expander(f"📋 Lançamentos considerados ({len(df)})"):
    st.dataframe(
        df.sort_values("Data", ascending=False),
        width="stretch", hide_index=True,
        column_config={
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        },
    )
    st.download_button(
        "⬇️ Baixar dados limpos (CSV)",
        df.to_csv(index=False, sep=";", decimal=",", date_format="%d/%m/%Y").encode("utf-8-sig"),
        file_name="gastos_limpos.csv", mime="text/csv",
    )

with st.expander(f"📊 Resumo por categoria ({len(por_cat)})"):
    resumo = por_cat.assign(Percentual=lambda d: d["Valor"] / total * 100)
    st.dataframe(
        resumo, width="stretch", hide_index=True,
        column_config={
            "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
            "Percentual": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
        },
    )

if len(descartados):
    with st.expander(f"🗑️ Linhas ignoradas na limpeza ({len(descartados)})"):
        st.caption("Linhas sem data/valor válidos (ex.: totais, subtítulos, células vazias) ou que não são despesas pela regra escolhida.")
        st.dataframe(descartados.astype(str), width="stretch")
