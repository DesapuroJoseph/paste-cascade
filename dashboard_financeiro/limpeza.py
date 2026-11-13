"""Leitura e limpeza de dados financeiros, independente do layout da planilha.

Nada aqui conhece nomes de colunas: tudo recebe a coluna já mapeada pelo usuário.
"""
from __future__ import annotations

import io
import re
import unicodedata

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Leitura de arquivos
# ---------------------------------------------------------------------------

_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def listar_abas(conteudo: bytes) -> list[str]:
    """Nomes das abas de um .xlsx."""
    with pd.ExcelFile(io.BytesIO(conteudo), engine="openpyxl") as xls:
        return list(xls.sheet_names)


def ler_arquivo(conteudo: bytes, nome: str, aba: str | int = 0, linha_cabecalho: int = 0) -> pd.DataFrame:
    """Lê .csv ou .xlsx em um DataFrame com todas as colunas como texto/objeto.

    - CSV: detecta separador (; , tab |) e codificação automaticamente.
    - linha_cabecalho: índice (0 = primeira linha) da linha que contém os títulos.
    """
    nome = nome.lower()
    if nome.endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(conteudo), sheet_name=aba, header=linha_cabecalho, engine="openpyxl")
    elif nome.endswith((".csv", ".txt")):
        df = None
        ultimo_erro: Exception | None = None
        for enc in _ENCODINGS:
            try:
                df = pd.read_csv(
                    io.BytesIO(conteudo),
                    sep=None,
                    engine="python",
                    encoding=enc,
                    header=linha_cabecalho,
                    dtype=str,
                    skip_blank_lines=True,
                )
                break
            except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as e:
                ultimo_erro = e
        if df is None:
            raise ValueError(f"Não foi possível ler o CSV: {ultimo_erro}")
    else:
        raise ValueError("Formato não suportado. Envie um arquivo .xlsx ou .csv.")

    return normalizar_cabecalhos(df)


def normalizar_cabecalhos(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas/colunas totalmente vazias e garante nomes de coluna únicos e legíveis."""
    df = df.dropna(how="all").dropna(axis=1, how="all")
    nomes: list[str] = []
    vistos: dict[str, int] = {}
    for i, c in enumerate(df.columns):
        nome = str(c).strip()
        if not nome or nome.lower().startswith("unnamed:") or nome.lower() == "nan":
            nome = f"Coluna {i + 1}"
        if nome in vistos:
            vistos[nome] += 1
            nome = f"{nome} ({vistos[nome]})"
        else:
            vistos[nome] = 1
        nomes.append(nome)
    df.columns = nomes
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Sugestão automática de mapeamento (apenas pré-seleção; o usuário decide)
# ---------------------------------------------------------------------------

_PALAVRAS = {
    "data": ("data", "date", "dia", "vencimento", "pagamento", "lancamento", "competencia", "quando"),
    "valor": ("valor", "value", "amount", "montante", "preco", "price", "total", "gasto", "custo", "quantia", "quanto", "r$", "debito", "saida"),
    "categoria": ("categoria", "category", "tipo", "grupo", "classe", "classificacao", "natureza", "centro"),
    "descricao": ("descricao", "description", "historico", "detalhe", "item", "estabelecimento", "obs", "nome", "memo"),
}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower()


def sugerir_coluna(
    colunas: list[str], papel: str, excluir: set[str] | None = None, df: pd.DataFrame | None = None
) -> str | None:
    """Sugere a coluna para um papel. Primeiro pelo nome; se nenhum nome ajudar e `df`
    for informado, pelo conteúdo (data: mais linhas viram data; valor: mais linhas viram
    número; categoria: texto com poucos valores distintos; descrição: texto com muitos)."""
    excluir = {e for e in (excluir or set()) if e}
    candidatas = [c for c in colunas if c not in excluir]
    for palavra in _PALAVRAS[papel]:
        for c in candidatas:
            if palavra in _sem_acento(c):
                return c
    if df is None or not candidatas:
        return None

    amostra = df[candidatas].dropna(how="all").head(300)
    if amostra.empty:
        return None
    pontos: dict[str, float] = {}
    for c in candidatas:
        col = amostra[c].dropna()
        if col.empty:
            continue
        datas = limpar_data(col).notna().mean()
        nums = limpar_valor(col).notna().mean()
        unicos = col.astype(str).nunique() / len(col)
        texto = 1 - max(datas, nums)
        if papel == "data":
            pontos[c] = datas
        elif papel == "valor":
            pontos[c] = nums * (1 - datas)
        elif papel == "categoria":
            pontos[c] = texto * (1 - unicos)
        else:
            pontos[c] = texto * unicos
    if not pontos:
        return None
    melhor = max(pontos, key=pontos.get)
    return melhor if pontos[melhor] >= 0.5 or (papel in ("categoria", "descricao") and pontos[melhor] > 0.05) else None


# ---------------------------------------------------------------------------
# Limpeza de valores monetários
# ---------------------------------------------------------------------------

FORMATO_AUTO = "auto"
FORMATO_BR = "br"  # 1.234,56
FORMATO_US = "us"  # 1,234.56

_RE_NAO_NUMERICO = re.compile(r"[^0-9,.\-]")


def _detectar_formato(textos: pd.Series) -> str:
    """Decide, olhando a coluna inteira, se a vírgula ou o ponto é o separador decimal."""
    votos_br = votos_us = 0
    for t in textos:
        t = _RE_NAO_NUMERICO.sub("", t)
        if "," in t and "." in t:
            if t.rfind(",") > t.rfind("."):
                votos_br += 1
            else:
                votos_us += 1
        elif "," in t:
            # "12,5" / "12,50" -> decimal BR; "1,234" (3 dígitos) é ambíguo, vale menos
            depois = t.split(",")[-1]
            if t.count(",") == 1 and len(depois) != 3:
                votos_br += 2
            elif t.count(",") > 1:
                votos_us += 1
        elif "." in t:
            depois = t.split(".")[-1]
            if t.count(".") == 1 and len(depois) != 3:
                votos_us += 2
            elif t.count(".") > 1:
                votos_br += 1
    # Em empate (ex.: tudo inteiro), assume padrão brasileiro
    return FORMATO_US if votos_us > votos_br else FORMATO_BR


def _converter_texto(t: str, formato: str) -> float:
    if not t:
        return np.nan
    negativo = False
    t = t.strip()
    # Contabilidade: (123,45) ou 123,45- ou "D" (débito) no final
    if t.startswith("(") and t.endswith(")"):
        negativo = True
    t_limpo = _RE_NAO_NUMERICO.sub("", t)
    if "-" in t_limpo:  # -50,00 / 50,00- / R$ -50
        negativo = True
        t_limpo = t_limpo.replace("-", "")
    if not t_limpo or not any(ch.isdigit() for ch in t_limpo):
        return np.nan

    if formato == FORMATO_BR:
        t_limpo = t_limpo.replace(".", "").replace(",", ".")
    else:
        t_limpo = t_limpo.replace(",", "")
    try:
        v = float(t_limpo)
    except ValueError:
        return np.nan
    return -v if negativo else v


def limpar_valor(serie: pd.Series, formato: str = FORMATO_AUTO) -> pd.Series:
    """Converte uma coluna de valores monetários "sujos" para float.

    Aceita: números já numéricos, "R$ 1.234,56", "$1,234.56", "1234,5", "-50,00",
    "(50,00)", "50,00-", "€ 12", espaços (inclusive não-quebráveis), células vazias.
    Valores impossíveis de converter viram NaN.
    """
    resultado = pd.Series(np.nan, index=serie.index, dtype="float64")

    # Valores que já são numéricos (comum em .xlsx) passam direto
    numericos = serie.map(lambda x: isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool))
    if numericos.any():
        resultado[numericos] = pd.to_numeric(serie[numericos], errors="coerce").astype("float64")

    textos = serie[~numericos & serie.notna()].astype(str).str.replace(" ", " ").str.strip()
    textos = textos[~textos.str.lower().isin(["", "nan", "none", "-", "—", "null"])]
    if textos.empty:
        return resultado

    if formato == FORMATO_AUTO:
        formato = _detectar_formato(textos)
    resultado[textos.index] = textos.map(lambda t: _converter_texto(t, formato)).astype("float64")
    return resultado


# ---------------------------------------------------------------------------
# Limpeza de datas
# ---------------------------------------------------------------------------

_MESES_PT = {
    "jan": "01", "fev": "02", "mar": "03", "abr": "04", "mai": "05", "jun": "06",
    "jul": "07", "ago": "08", "set": "09", "out": "10", "nov": "11", "dez": "12",
}


_RE_MES_PT = re.compile(r"^\s*(\d{1,2})\s*(?:de\s+|[/\-.\s])\s*([a-z]{3})[a-z]*\.?\s*(?:de\s+|[/\-.\s])\s*(\d{2,4})\b")


def _traduzir_meses(t: str) -> str:
    """'15/mar/2024' ou '15 de março de 2024' -> '15/03/2024'. Outros textos ficam intactos."""
    m = _RE_MES_PT.match(_sem_acento(t))
    if m and m.group(2) in _MESES_PT:
        return f"{m.group(1)}/{_MESES_PT[m.group(2)]}/{m.group(3)}"
    return t


def _plausivel(datas: pd.Series) -> pd.Series:
    """Descarta datas fora de 1900-2200 (ex.: '12,50' lido como ano 1321) e normaliza para ns."""
    datas = pd.to_datetime(datas, errors="coerce")
    if getattr(datas.dt, "tz", None) is not None:
        datas = datas.dt.tz_localize(None)
    return datas.where(datas.dt.year.between(1900, 2200)).astype("datetime64[ns]")


_RE_DMY = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-]\d{2,4}")


def _detectar_dia_primeiro(textos: pd.Series) -> bool:
    """Olha a coluna inteira: algum '25/12' indica dia/mês; algum '12/25' indica mês/dia.
    Sem evidência, assume o padrão brasileiro (dia/mês)."""
    partes = textos.str.extract(_RE_DMY).dropna().astype(int)
    if partes.empty:
        return True
    if (partes[0] > 12).any():
        return True
    if (partes[1] > 12).any():
        return False
    return True


def limpar_data(serie: pd.Series, dia_primeiro: bool | None = None) -> pd.Series:
    """Converte uma coluna de datas em datetime64.

    Aceita objetos datetime do Excel, números seriais do Excel (ex.: 45291),
    textos dd/mm/aaaa, aaaa-mm-dd, mm/dd/aaaa e meses por extenso em português.
    dia_primeiro=None detecta a ordem (dia/mês ou mês/dia) analisando a coluna inteira.
    """
    resultado = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")

    ja_data = serie.map(lambda x: isinstance(x, (pd.Timestamp, np.datetime64)) or hasattr(x, "year"))
    if ja_data.any():
        resultado[ja_data] = _plausivel(serie[ja_data])

    resto = serie[~ja_data & serie.notna()]
    if resto.empty:
        return resultado

    # Seriais do Excel: números entre ~1927 e ~2173
    num = pd.to_numeric(resto, errors="coerce")
    seriais = num.between(10000, 100000)
    if seriais.any():
        resultado[seriais[seriais].index] = pd.to_datetime(num[seriais], unit="D", origin="1899-12-30")

    textos = resto[~seriais].astype(str).str.strip()
    textos = textos[textos != ""]
    if textos.empty:
        return resultado
    textos = textos.map(_traduzir_meses)

    if dia_primeiro is None:
        dia_primeiro = _detectar_dia_primeiro(textos)
    convertido = pd.to_datetime(textos, errors="coerce", dayfirst=dia_primeiro, format="mixed")
    resultado[textos.index] = _plausivel(convertido)
    return resultado


# ---------------------------------------------------------------------------
# Montagem do conjunto final
# ---------------------------------------------------------------------------

SINAL_ABSOLUTO = "Todos os valores são despesas (usar valor absoluto)"
SINAL_NEGATIVOS = "Somente valores negativos são despesas"
SINAL_POSITIVOS = "Somente valores positivos são despesas"


def preparar_dados(
    df: pd.DataFrame,
    col_data: str,
    col_valor: str,
    col_categoria: str | None,
    col_descricao: str | None,
    formato_numero: str = FORMATO_AUTO,
    dia_primeiro: bool | None = None,
    regra_sinal: str = SINAL_ABSOLUTO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gera o DataFrame padronizado (Data, Valor, Categoria, Descrição).

    Retorna (dados_validos, linhas_descartadas) para o usuário auditar o que ficou de fora.
    """
    out = pd.DataFrame(index=df.index)
    out["Data"] = limpar_data(df[col_data], dia_primeiro)
    out["Valor"] = limpar_valor(df[col_valor], formato_numero)
    if col_categoria:
        cat = df[col_categoria].astype("string").str.strip()
        out["Categoria"] = cat.mask(cat.isna() | (cat == ""), "Sem categoria").astype(str)
    else:
        out["Categoria"] = "Sem categoria"
    if col_descricao:
        out["Descrição"] = df[col_descricao].astype("string").fillna("").str.strip().astype(str)
    else:
        out["Descrição"] = ""

    motivo = pd.Series("", index=df.index, dtype=object)
    motivo[out["Valor"].isna()] = "Valor vazio/inválido"
    motivo[out["Data"].isna()] = motivo[out["Data"].isna()].map(lambda m: (m + "; " if m else "") + "Data vazia/inválida")

    if regra_sinal == SINAL_NEGATIVOS:
        fora = out["Valor"] >= 0
        motivo[fora & (motivo == "")] = "Não é despesa (valor não negativo)"
    elif regra_sinal == SINAL_POSITIVOS:
        fora = out["Valor"] <= 0
        motivo[fora & (motivo == "")] = "Não é despesa (valor não positivo)"

    validos = out[motivo == ""].copy()
    validos["Valor"] = validos["Valor"].abs()
    descartados = df[motivo != ""].copy()
    descartados.insert(0, "Motivo do descarte", motivo[motivo != ""])
    return validos.sort_values("Data").reset_index(drop=True), descartados
