$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "가상환경이 없습니다. 먼저 .venv\Scripts\python.exe를 준비하세요."
}

& ".venv\Scripts\python.exe" -m src.run_pipeline
if ($LASTEXITCODE -ne 0) {
    throw "대중교통 파이프라인이 실패했습니다. logs\pipeline.log를 확인하세요."
}
