# Gera um executavel unico PasteCascade.exe (sem console) com PyInstaller.
# Uso:  powershell -ExecutionPolicy Bypass -File build_exe.ps1
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $proj
try {
    py -m pip install --disable-pip-version-check pyinstaller
    # (re)gera assets\paste_cascade.ico a partir do desenho vetorial
    $env:QT_QPA_PLATFORM = "offscreen"
    py -m paste_cascade.icon
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    py -m PyInstaller --noconfirm --clean --onefile --windowed --name PasteCascade `
        --icon assets\paste_cascade.ico run.pyw
    Write-Output ""
    Write-Output "Pronto: $proj\dist\PasteCascade.exe"
}
finally {
    Pop-Location
}
