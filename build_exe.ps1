$ErrorActionPreference = "Stop"

Write-Host "[1/4] Kich hoat venv..."
& ".\.venv\Scripts\Activate.ps1"

Write-Host "[2/4] Cai dat build tools..."
python -m pip install --upgrade pip
python -m pip install pyinstaller

Write-Host "[3/4] Build exe (onedir)..."
pyinstaller --noconfirm --clean --onedir --name LegalAgentAssistant `
  --collect-all streamlit `
  --collect-all chromadb `
  --collect-all sentence_transformers `
  --collect-all transformers `
  --collect-all tokenizers `
  --collect-all pypandoc `
  --collect-submodules pkg_resources `
  --hidden-import=tqdm `
  --hidden-import=sqlite3 `
  --add-data "app.py;." `
  --add-data "Config;Config" `
  --add-data "Core;Core" `
  --add-data "Document_processing;Document_processing" `
  --add-data "Vector_store;Vector_store" `
  --add-data "Data;Data" `
  launcher.py

Write-Host "[4/4] Build hoan tat. Thu muc output: .\dist\LegalAgentAssistant"
Write-Host "Chay: .\dist\LegalAgentAssistant\LegalAgentAssistant.exe"
