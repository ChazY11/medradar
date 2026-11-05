$ErrorActionPreference = 'Continue'
$venv = 'D:\DEPPSKK\mlenv'
$vpy = "$venv\Scripts\python.exe"
$env:HF_HOME = 'D:\DEPPSKK\ml-cache\hf'
$env:PIP_CACHE_DIR = 'D:\DEPPSKK\ml-cache\pip'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:PYTHONIOENCODING = 'utf-8'

Write-Output "=== [1/3] torch from the verified local wheel ==="
& $vpy -m pip install --timeout 120 --retries 10 'D:\DEPPSKK\ml-cache\wheels\torch-2.9.1+cu128-cp312-cp312-win_amd64.whl' 2>&1 | Select-Object -Last 12

Write-Output "=== [2/3] the rest of the stack ==="
& $vpy -m pip install --timeout 120 --retries 10 `
    "transformers==5.22.1" "peft==0.21.2" "accelerate==1.15.0" "bitsandbytes==0.50.2" `
    "datasets==5.1.0" "safetensors" "sentencepiece" "protobuf" "jsonschema" "huggingface_hub" `
    "numpy" "psutil" "pynvml" 2>&1 | Select-Object -Last 20

Write-Output "=== [3/3] freeze ==="
& $vpy -m pip freeze | Out-File -Encoding utf8 'D:\DEPPSKK\ml-work\requirements-freeze.txt'
Get-Content 'D:\DEPPSKK\ml-work\requirements-freeze.txt'
Write-Output "=== done ==="
