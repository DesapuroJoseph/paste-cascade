@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Dashboard Financeiro
cd /d "%~dp0"

echo ============================================================
echo   Dashboard de Analise Financeira
echo ============================================================
echo.

rem --- 1. Localizar o Python (launcher "py" ou "python" no PATH) ---
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE (
    where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
    echo [ERRO] Python nao encontrado.
    echo Instale o Python 3.10+ em https://www.python.org/downloads/
    echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
    pause
    exit /b 1
)

rem --- 2. Criar ambiente virtual local (.venv) na primeira execucao ---
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Criando ambiente virtual local ^(.venv^)...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)
set "VPY=.venv\Scripts\python.exe"

rem --- 3. Verificar dependencias e instalar so se faltar alguma ---
echo [2/3] Verificando dependencias...
"%VPY%" -c "import streamlit, pandas, plotly, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo        Instalando streamlit, pandas, plotly e openpyxl ^(somente na primeira vez^)...
    "%VPY%" -m pip install --upgrade pip --disable-pip-version-check -q
    "%VPY%" -m pip install -r requirements.txt --disable-pip-version-check
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar as dependencias. Verifique sua conexao com a internet.
        pause
        exit /b 1
    )
) else (
    echo        Tudo instalado.
)

rem --- 4. Abrir o dashboard no navegador ---
echo [3/3] Abrindo o dashboard no navegador...
echo        Para encerrar, feche esta janela ou pressione Ctrl+C.
echo.
"%VPY%" -m streamlit run app.py --server.headless false --browser.gatherUsageStats false
if errorlevel 1 pause
endlocal
