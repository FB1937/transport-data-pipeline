$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (Test-Path ".venv\Scripts\python.exe") {
    $python = ".venv\Scripts\python.exe"
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        throw "Python을 찾을 수 없습니다. .venv 또는 PATH에 Python을 설치하세요."
    }
}

& $python -m src.run_pipeline
if ($LASTEXITCODE -ne 0) {
    throw "대중교통 파이프라인이 실패했습니다. logs\pipeline.log를 확인하세요."
}
