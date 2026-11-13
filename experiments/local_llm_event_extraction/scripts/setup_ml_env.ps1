# MedRadar Phase 2 - isolated ML environment bootstrap (Windows native, cu128 for SM_120)
# Everything heavy lives on D:. The medradar default environment is NOT touched.
$ErrorActionPreference = 'Continue'
$venv   = 'D:\DEPPSKK\mlenv'
$cache  = 'D:\DEPPSKK\ml-cache'
$logs   = 'D:\DEPPSKK\ml-work\logs'
New-Item -ItemType Directory -Force -Path $cache, "$cache\hf", "$cache\pip", $logs | Out-Null

$env:HF_HOME            = "$cache\hf"
$env:PIP_CACHE_DIR      = "$cache\pip"
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:PYTHONIOENCODING   = 'utf-8'

$sysPy = 'C:\Users\yjx0\AppData\Local\Programs\Python\Python312\python.exe'
$vpy   = "$venv\Scripts\python.exe"

$t0 = Get-Date
Write-Output "=== [1/4] venv $venv ==="
if (-not (Test-Path $vpy)) { & $sysPy -m venv $venv }
& $vpy -c "import sys; print(sys.version); print(sys.executable)"

Write-Output "=== [2/4] pip bootstrap ==="
& $vpy -m pip install --upgrade pip setuptools wheel --timeout 120 2>&1 | Select-Object -Last 5

Write-Output "=== [3/4] torch cu128 (large download) ==="
& $vpy -m pip install --index-url https://download.pytorch.org/whl/cu128 "torch==2.9.1+cu128" --timeout 300 2>&1 | Select-Object -Last 25

Write-Output "=== [4/4] rest of stack ==="
& $vpy -m pip install --timeout 120 `
    "transformers>=4.51,<6" `
    "accelerate>=1.4,<2" `
    "peft>=0.14,<1" `
    "bitsandbytes>=0.45,<1" `
    "datasets>=3.2,<6" `
    "safetensors" "sentencepiece" "protobuf" "jsonschema" "huggingface_hub" `
    "numpy" "pandas" "pytest" "psutil" "pynvml" 2>&1 | Select-Object -Last 30

Write-Output "=== freeze ==="
& $vpy -m pip freeze | Out-File -Encoding utf8 "D:\DEPPSKK\ml-work\requirements-freeze.txt"
Get-Content "D:\DEPPSKK\ml-work\requirements-freeze.txt"

Write-Output ("=== DONE in " + [math]::Round(((Get-Date)-$t0).TotalMinutes,1) + " min ===")
