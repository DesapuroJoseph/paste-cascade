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
    """Lê .csv ou .xlsx usando a linha `linha_cabecalho` (0 = primeira) como títulos das colunas.

    - CSV: separador (; , tab |) e codificação detectados; linhas com nº de campos diferente
      (títulos no topo, totais no fim) não quebram a leitura.
    - XLSX: números e datas continuam com o tipo original do Excel.
    """
    return com_cabecalho(ler_cru(conteudo, nome, aba), linha_cabecalho)


def eh_excel(nome: str) -> bool:
    return nome.lower().endswith((".xlsx", ".xlsm", ".xls"))


def ler_cru(conteudo: bytes, nome: str, aba: str | int = 0) -> pd.DataFrame:
    """Lê a planilha inteira sem cabeçalho (todas as linhas como dados)."""
    if eh_excel(nome):
        return pd.read_excel(io.BytesIO(conteudo), sheet_name=aba, header=None, engine="openpyxl")
    if not nome.lower().endswith((".csv", ".txt")):
        raise ValueError("Formato não suportado. Envie um arquivo .xlsx ou .csv.")
    texto = None
    for enc in _ENCODINGS:
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError("Não foi possível decodificar o CSV.")
    linhas = [l for l in texto.splitlines()]
    amostra = [l for l in linhas if l.strip()][:50]
    # separador = o que aparece de forma mais consistente (mesma contagem) nas linhas
    def consistencia(sep: str) -> tuple[int, int]:
        contagens = [l.count(sep) for l in amostra if l.count(sep) > 0]
        if not contagens:
            return (0, 0)
        moda = max(set(contagens), key=contagens.count)
        return (contagens.count(moda), moda)
    sep = max([";", ",", "\t", "|"], key=consistencia)
    import csv
    registros = list(csv.reader(linhas, delimiter=sep))
    largura = max((len(r) for r in registros), default=0)
    registros = [r + [""] * (largura - len(r)) for r in registros]
    df = pd.DataFrame(registros, dtype=object)
    return df.replace(r"^\s*$", np.nan, regex=True)


def _texto_cabecalho(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    if isinstance(x, (pd.Timestamp,)) or hasattr(x, "year"):
        return pd.Timestamp(x).strftime("%Y-%m")  # cabeçalho de mês salvo como data no Excel
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x).strip()


def com_cabecalho(cru: pd.DataFrame, linha: int) -> pd.DataFrame:
    """Usa a linha `linha` do DataFrame cru como títulos e devolve as linhas abaixo dela."""
    if cru.empty or linha >= len(cru):
        return pd.DataFrame()
    df = cru.iloc[linha + 1:].copy()
    df.columns = [_texto_cabecalho(c) for c in cru.iloc[linha]]
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


# ---------------------------------------------------------------------------
# Formato "grade mensal": itens nas linhas, meses nas colunas
# ---------------------------------------------------------------------------

_MES_NUM = {
    "jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "out": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}
_RE_MES_NOME = re.compile(r"^([a-z]{3})[a-z]*\.?\s*(?:(?:de\s+|[/\-\s'])\s*(\d{2,4}))?$")
_RE_MES_NUM = re.compile(r"^(?:(\d{1,2})[/\-](\d{2}|\d{4})|(\d{4})[/\-](\d{1,2}))$")
_RE_ANO = re.compile(r"\b(20\d{2}|19\d{2})\b")
_RE_RECEITA = re.compile(r"receita|entrada|renda\b|salario|rendimento|ganho|provento|recebid")
_RE_TOTAL = re.compile(r"\b(sub)?total|soma\b|saldo|resultado|media\b|balanco")


def _ano(a: str | None) -> int | None:
    if not a:
        return None
    a = int(a)
    return a + 2000 if a < 100 else a


def interpretar_mes(titulo: str) -> tuple[int, int | None] | None:
    """'Janeiro', 'jan/26', 'Fev 2026', '01/2026', '2026-03' -> (mês, ano ou None)."""
    t = _sem_acento(str(titulo)).strip()
    m = _RE_MES_NOME.match(t)
    if m and m.group(1) in _MES_NUM:
        return _MES_NUM[m.group(1)], _ano(m.group(2))
    m = _RE_MES_NUM.match(t)
    if m:
        mes, ano = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        if 1 <= int(mes) <= 12:
            return int(mes), _ano(ano)
    return None


def _vazio(x) -> bool:
    return x is None or (isinstance(x, float) and np.isnan(x)) or (isinstance(x, str) and not x.strip())


def converter_mensal(df: pd.DataFrame, ano_padrao: int) -> pd.DataFrame | None:
    """Transforma uma grade mensal em lista de lançamentos (Data, Valor, Categoria, Descrição).

    - Linhas só com texto (ex.: "MORADIA") viram a categoria das linhas abaixo.
    - Linhas de total/subtotal/saldo e de receitas/entradas são ignoradas.
    Retorna None se a tabela não tiver pelo menos 2 colunas de mês.
    """
    meses = {c: interpretar_mes(c) for c in df.columns}
    meses = {c: v for c, v in meses.items() if v}
    if len(meses) < 2:
        return None
    rotulos = [c for c in df.columns if c not in meses and not _RE_TOTAL.search(_sem_acento(c))]
    # colunas de rótulo = as que têm texto (não números) nas linhas
    rotulos = [c for c in rotulos
               if df[c].dropna().map(lambda x: isinstance(x, str) and not _celula_e_dado(x)).mean() > 0.5]
    if not rotulos:
        return None
    unicos = {c: df[c].dropna().nunique() for c in rotulos}
    desc_col = max(rotulos, key=lambda c: unicos[c])
    cat_col = next((c for c in rotulos if c != desc_col and unicos[c] < unicos[desc_col]), None)

    registros = []
    secao = None
    em_receitas = False
    for _, linha in df.iterrows():
        valores = [linha[c] for c in meses]
        rotulo = next((str(linha[c]).strip() for c in [desc_col] + rotulos if not _vazio(linha[c])), "")
        if not rotulo and all(_vazio(v) for v in valores):
            continue
        rot_norm = _sem_acento(rotulo)
        if all(_vazio(v) for v in valores):  # linha de seção
            secao = rotulo
            em_receitas = bool(_RE_RECEITA.search(rot_norm))
            if re.search(r"despesa|gasto|saida|custo", rot_norm):
                em_receitas = False
            continue
        if _RE_TOTAL.search(rot_norm):
            continue
        categoria = str(linha[cat_col]).strip() if cat_col and not _vazio(linha[cat_col]) else (secao or rotulo)
        cat_norm = _sem_acento(categoria)
        if em_receitas or _RE_RECEITA.search(cat_norm) or _RE_RECEITA.search(rot_norm):
            continue
        for c, (mes, ano) in meses.items():
            v = linha[c]
            if _vazio(v):
                continue
            registros.append({
                "Data": pd.Timestamp(year=ano or ano_padrao, month=mes, day=1),
                "Valor": v,
                "Categoria": categoria,
                "Descrição": rotulo,
            })
    if not registros:
        return None
    return pd.DataFrame(registros)


def _ano_do_contexto(cru: pd.DataFrame, *textos: str) -> int:
    for t in textos:
        m = _RE_ANO.search(str(t))
        if m:
            return int(m.group(1))
    topo = " ".join(str(x) for x in cru.head(10).to_numpy().ravel() if isinstance(x, str))
    m = _RE_ANO.search(topo)
    return int(m.group(1)) if m else pd.Timestamp.today().year


# ---------------------------------------------------------------------------
# Detecção automática completa (aba, linha do cabeçalho, formato e colunas)
# ---------------------------------------------------------------------------

FORMATO_LISTA = "lista"
FORMATO_MENSAL = "mensal"


def _celula_e_dado(x) -> bool:
    """True se a célula parece um dado (número ou data), e não um título de coluna."""
    if _vazio(x):
        return False
    if isinstance(x, (int, float, np.integer, np.floating, pd.Timestamp)) or hasattr(x, "year"):
        return True
    s = pd.Series([str(x).strip()])
    return bool(limpar_valor(s).notna().iloc[0] or limpar_data(s).notna().iloc[0])


def linhas_candidatas(cru: pd.DataFrame, max_linhas: int = 30, max_candidatas: int = 12) -> list[int]:
    """Linhas do topo que parecem títulos: ≥2 células preenchidas, em sua maioria texto."""
    candidatas = []
    for pos in range(min(max_linhas, len(cru))):
        celulas = [c for c in cru.iloc[pos] if not _vazio(c)]
        if len(celulas) < 2:
            continue
        texto = sum(1 for c in celulas if isinstance(c, str) and (interpretar_mes(c) or not _celula_e_dado(c)))
        datas_mes = sum(1 for c in celulas if hasattr(c, "year"))  # meses salvos como data
        if (texto + datas_mes) / len(celulas) >= 0.6:
            candidatas.append(pos)
        if len(candidatas) >= max_candidatas:
            break
    return candidatas or [0]


def sugerir_mapeamento(df: pd.DataFrame) -> dict[str, str | None]:
    colunas = list(df.columns)
    data = sugerir_coluna(colunas, "data", df=df)
    valor = sugerir_coluna(colunas, "valor", {data}, df=df)
    cat = sugerir_coluna(colunas, "categoria", {data, valor}, df=df)
    desc = sugerir_coluna(colunas, "descricao", {data, valor, cat}, df=df)
    return {"data": data, "valor": valor, "categoria": cat, "descricao": desc}


def montar_tabela(cru: pd.DataFrame, linha: int, formato: str, ano_padrao: int) -> pd.DataFrame:
    """Tabela pronta para o mapeamento, no formato de lista de lançamentos."""
    df = com_cabecalho(cru, linha)
    if formato == FORMATO_MENSAL:
        convertida = converter_mensal(df, ano_padrao)
        return convertida if convertida is not None else pd.DataFrame()
    return df


def _linhas_validas(df: pd.DataFrame, mapa: dict) -> int:
    if df.empty or not (mapa.get("data") and mapa.get("valor")):
        return 0
    ok, _ = preparar_dados(df, mapa["data"], mapa["valor"], mapa["categoria"], mapa["descricao"])
    return len(ok)


def detectar_tudo(conteudo: bytes, nome: str) -> dict:
    """Testa cada aba × linhas candidatas a cabeçalho × formato (lista ou grade mensal)
    e fica com a combinação que produz mais lançamentos válidos.

    Retorna {"aba", "linha_cabecalho", "formato", "ano", "mapa", "linhas_validas"}.
    """
    abas = listar_abas(conteudo) if eh_excel(nome) else [0]
    melhor = {"aba": abas[0], "linha_cabecalho": 0, "formato": FORMATO_LISTA,
              "ano": pd.Timestamp.today().year, "mapa": {}, "linhas_validas": -1}
    for aba in abas:
        try:
            cru = ler_cru(conteudo, nome, aba)
        except Exception:
            continue
        if cru.empty:
            continue
        ano = _ano_do_contexto(cru, aba if isinstance(aba, str) else "", nome)
        for linha in linhas_candidatas(cru):
            for formato in (FORMATO_LISTA, FORMATO_MENSAL):
                try:
                    df = montar_tabela(cru, linha, formato, ano)
                    if df.empty or len(df.columns) < 2:
                        continue
                    mapa = sugerir_mapeamento(df)
                    validas = _linhas_validas(df, mapa)
                except Exception:
                    continue
                if validas > melhor["linhas_validas"]:
                    melhor = {"aba": aba, "linha_cabecalho": linha, "formato": formato, "ano": ano,
                              "mapa": mapa, "linhas_validas": validas}
    return melhor
