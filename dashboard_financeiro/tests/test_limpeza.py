import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import limpeza as lp  # noqa: E402

EXEMPLOS = RAIZ / "exemplos"
TOTAL_EXEMPLOS = 131096.38


@pytest.mark.parametrize("entrada,esperado", [
    ("R$ 1.234,56", 1234.56), ("1234,5", 1234.5), ("-50,00", -50.0), ("(50,00)", -50.0),
    ("50,00-", -50.0), ("R$ 12,00", 12.0), ("  7  ", 7.0), ("1.000.000", 1000000.0),
])
def test_valor_brasileiro(entrada, esperado):
    s = pd.Series([entrada, "R$ 9,99"])
    assert lp.limpar_valor(s).iloc[0] == pytest.approx(esperado)


@pytest.mark.parametrize("entrada,esperado", [
    ("$1,234.56", 1234.56), ("-$5.50", -5.5), ("1,000,000", 1000000.0), ("€ 12.30", 12.3),
])
def test_valor_americano(entrada, esperado):
    s = pd.Series([entrada, "$9.99"])
    assert lp.limpar_valor(s).iloc[0] == pytest.approx(esperado)


def test_valor_vazios_e_numericos():
    s = pd.Series([None, "", "nan", "-", "abc", 10, 2.5, np.nan])
    r = lp.limpar_valor(s)
    assert r.isna().tolist() == [True, True, True, True, True, False, False, True]
    assert r.iloc[5] == 10 and r.iloc[6] == 2.5


def test_formato_forcado():
    assert lp.limpar_valor(pd.Series(["1.234"]), lp.FORMATO_BR).iloc[0] == 1234
    assert lp.limpar_valor(pd.Series(["1.234"]), lp.FORMATO_US).iloc[0] == pytest.approx(1.234)


def test_datas_variadas():
    s = pd.Series(["31/01/2026", "2026-02-15", 45292, "15 de março de 2026", "05/abr/2026", "", None, "lixo"])
    r = lp.limpar_data(s)
    assert r.iloc[0] == pd.Timestamp("2026-01-31")
    assert r.iloc[1] == pd.Timestamp("2026-02-15")
    assert r.iloc[2] == pd.Timestamp("2024-01-01")
    assert r.iloc[3] == pd.Timestamp("2026-03-15")
    assert r.iloc[4] == pd.Timestamp("2026-04-05")
    assert r.iloc[5:].isna().all()


def test_data_dia_primeiro_auto():
    br = lp.limpar_data(pd.Series(["02/03/2026", "25/12/2026"]))
    assert br.iloc[0] == pd.Timestamp("2026-03-02")
    us = lp.limpar_data(pd.Series(["03/02/2026", "12/25/2026"]))
    assert us.iloc[0] == pd.Timestamp("2026-03-02")


def test_sugestao_de_colunas():
    cols = ["Dt. Lançamento", "Histórico", "Tipo de gasto", "Valor (R$)"]
    assert lp.sugerir_coluna(cols, "data") == "Dt. Lançamento"
    assert lp.sugerir_coluna(cols, "valor") == "Valor (R$)"
    assert lp.sugerir_coluna(cols, "categoria") == "Tipo de gasto"
    assert lp.sugerir_coluna(cols, "descricao") == "Histórico"


def test_exemplo_csv_br():
    df = lp.ler_arquivo((EXEMPLOS / "extrato_banco_br.csv").read_bytes(), "extrato_banco_br.csv")
    ok, fora = lp.preparar_dados(df, "Dt. Lançamento", "Valor (R$)", "Tipo de gasto", "Histórico",
                                 regra_sinal=lp.SINAL_NEGATIVOS)
    assert ok["Valor"].sum() == pytest.approx(TOTAL_EXEMPLOS)
    assert "Salário" in fora["Histórico"].tolist()  # receita positiva ficou de fora


def test_exemplo_xlsx_com_titulo():
    conteudo = (EXEMPLOS / "controle_gastos_2026.xlsx").read_bytes()
    assert lp.listar_abas(conteudo) == ["Gastos", "Metas"]
    df = lp.ler_arquivo(conteudo, "controle_gastos_2026.xlsx", "Gastos", linha_cabecalho=2)
    ok, fora = lp.preparar_dados(df, "Quando", "Quanto", "Grupo", "Onde gastei")
    assert ok["Valor"].sum() == pytest.approx(TOTAL_EXEMPLOS)
    assert len(fora) == 0


def test_exemplo_csv_us():
    df = lp.ler_arquivo((EXEMPLOS / "expenses_us.csv").read_bytes(), "expenses_us.csv")
    ok, _ = lp.preparar_dados(df, "date", "amount", "category", "memo")
    assert ok["Valor"].sum() == pytest.approx(TOTAL_EXEMPLOS)
    assert ok["Data"].min() == pd.Timestamp("2026-01-03")
    assert ok["Data"].max() == pd.Timestamp("2026-10-31")  # nenhuma data invertida (mês/dia)


def test_sem_categoria():
    df = pd.DataFrame({"a": ["01/01/2026", "02/01/2026"], "b": ["10", "20"]})
    ok, _ = lp.preparar_dados(df, "a", "b", None, None)
    assert ok["Categoria"].unique().tolist() == ["Sem categoria"]
    assert ok["Valor"].sum() == 30


def test_sugestao_pelo_conteudo():
    df = pd.DataFrame({
        "A": ["03/01/2026", "04/01/2026", "05/01/2026", "06/01/2026"],
        "B": ["Padaria do João", "Uber centro", "Farmácia X", "Cinema"],
        "C": ["Mercado", "Transporte", "Saúde", "Mercado"],
        "D": ["12,50", "30,00", "8,90", "45,00"],
    })
    cols = list(df.columns)
    assert lp.sugerir_coluna(cols, "data", df=df) == "A"
    assert lp.sugerir_coluna(cols, "valor", {"A"}, df=df) == "D"
    assert lp.sugerir_coluna(cols, "categoria", {"A", "D"}, df=df) == "C"
    assert lp.sugerir_coluna(cols, "descricao", {"A", "D", "C"}, df=df) == "B"


def test_data_fora_do_intervalo_nao_quebra():
    r = lp.limpar_data(pd.Series(["12,50", "0001-01-01", "9999-12-31", "01/02/2026"]))
    assert r.iloc[:3].isna().all() and r.iloc[3] == pd.Timestamp("2026-02-01")


@pytest.mark.parametrize("arquivo,aba,linha,mapa", [
    ("extrato_banco_br.csv", 0, 0, ("Dt. Lançamento", "Valor (R$)", "Tipo de gasto", "Histórico")),
    ("controle_gastos_2026.xlsx", "Gastos", 2, ("Quando", "Quanto", "Grupo", "Onde gastei")),
    ("expenses_us.csv", 0, 0, ("date", "amount", "category", "memo")),
])
def test_deteccao_automatica_completa(arquivo, aba, linha, mapa):
    r = lp.detectar_tudo((EXEMPLOS / arquivo).read_bytes(), arquivo)
    assert r["aba"] == aba and r["linha_cabecalho"] == linha
    assert tuple(r["mapa"].values()) == mapa


@pytest.mark.parametrize("arquivo,linha,total,ano", [
    ("grade_mensal_secoes.xlsx", 2, 81207.90, 2026),  # título, seções, receitas, subtotais, saldo
    ("grade_mensal_datas.xlsx", 0, 57076.00, 2025),   # meses salvos como data no cabeçalho
])
def test_grade_mensal(arquivo, linha, total, ano):
    conteudo = (EXEMPLOS / arquivo).read_bytes()
    r = lp.detectar_tudo(conteudo, arquivo)
    assert r["formato"] == lp.FORMATO_MENSAL and r["linha_cabecalho"] == linha
    df = lp.montar_tabela(lp.ler_cru(conteudo, arquivo, r["aba"]), r["linha_cabecalho"], r["formato"], r["ano"])
    m = r["mapa"]
    ok, _ = lp.preparar_dados(df, m["data"], m["valor"], m["categoria"], m["descricao"])
    assert ok["Valor"].sum() == pytest.approx(total)
    assert ok["Data"].dt.year.unique().tolist() == [ano]
    assert not ok["Descrição"].str.contains("Total|Salário|SALDO", case=False).any()


@pytest.mark.parametrize("titulo,esperado", [
    ("Janeiro", (1, None)), ("fev/26", (2, 2026)), ("Mar 2025", (3, 2025)), ("01/2026", (1, 2026)),
    ("2026-12", (12, 2026)), ("Março de 2024", (3, 2024)), ("Descrição", None), ("Total", None),
])
def test_interpretar_mes(titulo, esperado):
    assert lp.interpretar_mes(titulo) == esperado
