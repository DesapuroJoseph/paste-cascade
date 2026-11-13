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
def carregar(conteudo: bytes, nome: str, aba, linha_cabecalho: int, formato_tabela: str, ano: int) -> pd.DataFrame:
    return lp.montar_tabela(lp.ler_cru(conteudo, nome, aba), linha_cabecalho, formato_tabela, ano)



@st.cache_data(show_spinner="Analisando a planilha…")
def detectar(conteudo: bytes, nome: str) -> dict:
    return lp.detectar_tudo(conteudo, nome)


# ---------------------------------------------------------------------------
# 1. Upload
# ---------------------------------------------------------------------------
st.title("💰 Dashboard de Análise Financeira")

arquivo = st.file_uploader(
    "Arraste sua planilha de gastos aqui (ou clique em **Browse files**)",
    type=["xlsx", "xlsm", "csv", "txt"],
)

if arquivo is None:
    st.info(
        "**Como usar:** é só enviar a planilha acima (Excel ou CSV). "
        "O dashboard descobre sozinho onde estão as datas, os valores e as categorias. "
        "Não precisa arrumar nem renomear nada."
    )
    st.stop()

conteudo = arquivo.getvalue()
eh_excel = arquivo.name.lower().endswith((".xlsx", ".xlsm"))

try:
    auto = detectar(conteudo, arquivo.name)
except Exception as e:
    st.error(f"Não consegui abrir este arquivo: {e}")
    st.stop()

mapa = auto["mapa"]
deteccao_ok = bool(mapa.get("data") and mapa.get("valor") and auto["linhas_validas"] > 0)


def indice(sugestao, opcoes: list) -> int:
    return opcoes.index(sugestao) if sugestao in opcoes else 0


# ---------------------------------------------------------------------------
# 2. Ajustes manuais — escondidos; só abrem sozinhos se a detecção falhar
# ---------------------------------------------------------------------------
resumo_slot = st.empty()
ajustes = st.expander(
    "⚙️ Algo errado nos números? Clique aqui para ajustar as colunas" if deteccao_ok
    else "⚠️ Não consegui identificar as colunas sozinho — indique abaixo",
    expanded=not deteccao_ok,
)

with ajustes:
    c1, c2 = st.columns(2)
    aba = 0
    if eh_excel:
        abas = lp.listar_abas(conteudo)
        aba = c1.selectbox("Aba da planilha", abas, index=indice(auto["aba"], abas)) if len(abas) > 1 else abas[0]
    linha_cab = c2.number_input(
        "Linha onde estão os títulos das colunas", min_value=1, max_value=200,
        value=int(auto["linha_cabecalho"]) + 1 if aba == auto["aba"] else 1,
    ) - 1
    _rotulos_layout = {
        lp.FORMATO_LISTA: "Lista de lançamentos (uma linha por gasto, com coluna de data)",
        lp.FORMATO_MENSAL: "Grade mensal (itens nas linhas, meses nas colunas)",
    }
    _opcoes_layout = list(_rotulos_layout)
    formato_tabela = st.radio(
        "Como a planilha está organizada?", _opcoes_layout,
        index=_opcoes_layout.index(auto.get("formato", lp.FORMATO_LISTA)),
        format_func=_rotulos_layout.get, horizontal=True,
    )

try:
    bruto = carregar(conteudo, arquivo.name, aba, int(linha_cab), formato_tabela, int(auto.get("ano", 2026)))
except Exception as e:
    st.error(f"Erro ao ler o arquivo: {e}")
    st.stop()

if bruto.empty or len(bruto.columns) < 2:
    st.warning("Não encontrei uma tabela de gastos com essas opções. Abra ⚙️ acima e tente outra aba, "
               "outra linha de títulos ou outra organização da planilha.")
    with st.expander("Ver as primeiras linhas do arquivo", expanded=True):
        st.dataframe(lp.ler_cru(conteudo, arquivo.name, aba).head(30).astype(str), width="stretch")
    st.stop()

colunas = list(bruto.columns)
if aba != auto["aba"] or int(linha_cab) != auto["linha_cabecalho"] or formato_tabela != auto.get("formato"):
    mapa = lp.sugerir_mapeamento(bruto)  # usuário mudou a aba/linha: re-detecta
opcoes_opc = [NENHUMA] + colunas

with ajustes:
    c1, c2, c3, c4 = st.columns(4)
    col_data = c1.selectbox("📅 Data", colunas, index=indice(mapa.get("data"), colunas))
    col_valor = c2.selectbox(
        "💵 Valor", colunas,
        index=indice(mapa.get("valor"), colunas) if mapa.get("valor") else min(1, len(colunas) - 1),
    )
    col_cat = c3.selectbox("🏷️ Categoria", opcoes_opc, index=indice(mapa.get("categoria"), opcoes_opc))
    col_desc = c4.selectbox("📝 Descrição", opcoes_opc, index=indice(mapa.get("descricao"), opcoes_opc))

    c1, c2, c3 = st.columns(3)
    fmt_label = c1.radio("Formato dos números", ["Automático", "Brasileiro (1.234,56)", "Americano (1,234.56)"])
    formato = {"Automático": lp.FORMATO_AUTO, "Brasileiro (1.234,56)": lp.FORMATO_BR}.get(fmt_label, lp.FORMATO_US)
    data_label = c2.radio("Formato das datas", ["Automático", "Dia/Mês/Ano", "Mês/Dia/Ano"])
    dia_primeiro = {"Automático": None, "Dia/Mês/Ano": True}.get(data_label, False)
    _amostra = lp.limpar_valor(bruto[col_valor], formato)
    _misto = bool((_amostra < 0).any() and (_amostra > 0).any())
    # Extrato com entradas e saídas: o lado menos frequente costuma ser a receita
    _idx_sinal = (1 if (_amostra < 0).sum() >= (_amostra > 0).sum() else 2) if _misto else 0
    regra_sinal = c3.radio(
        "Quais linhas são despesas?",
        [lp.SINAL_ABSOLUTO, lp.SINAL_NEGATIVOS, lp.SINAL_POSITIVOS],
        index=_idx_sinal,
        help="Para extratos que misturam entradas e saídas, o dashboard já escolhe sozinho.",
    )

if col_data == col_valor:
    st.error("A coluna de **Data** e a de **Valor** precisam ser diferentes. Ajuste em ⚙️ acima.")
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
    resumo_slot.error(
        "Não encontrei gastos válidos com as colunas escolhidas. Abra o painel ⚙️ abaixo e indique "
        "qual coluna tem as **datas** e qual tem os **valores**."
    )
    with st.expander("Ver as primeiras linhas do arquivo", expanded=True):
        st.dataframe(lp.ler_cru(conteudo, arquivo.name, aba).head(30).astype(str), width="stretch")
    st.stop()

mensal = formato_tabela == lp.FORMATO_MENSAL
_partes = [f"📅 **{col_data}**", f"💵 **{col_valor}**"]
if col_cat != NENHUMA:
    _partes.append(f"🏷️ **{col_cat}**")
if col_desc != NENHUMA:
    _partes.append(f"📝 **{col_desc}**")
_extra = " Entradas (valores do lado oposto) foram ignoradas." if _misto and regra_sinal != lp.SINAL_ABSOLUTO else ""
if mensal:
    resumo_slot.success(
        f"✅ Planilha lida automaticamente como **grade mensal**: {dados['Data'].dt.to_period('M').nunique()} meses, "
        f"{dados['Descrição'].nunique()} itens, {dados['Categoria'].nunique()} categorias. "
        "Linhas de total, saldo e receitas foram ignoradas."
    )
else:
    resumo_slot.success(f"✅ Planilha lida automaticamente: {' · '.join(_partes)}.{_extra}")


# ---------------------------------------------------------------------------
# 3. Filtros
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🔎 Filtros")
    dmin, dmax = dados["Data"].min().date(), dados["Data"].max().date()
    if mensal:  # cada valor representa o mês inteiro
        dmax = (dados["Data"].max() + pd.offsets.MonthEnd(0)).date()
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
    if mensal:  # a planilha só tem valores por mês
        granularidade = "Mês"
    else:
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
