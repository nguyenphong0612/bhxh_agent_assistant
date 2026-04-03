$ErrorActionPreference = "Continue"

# Khoi dong Ollama service neu chua chay
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "Ollama command not found."
    exit 0
}

# Kiem tra model va pull neu chua co
$model = "qwen2.5:7b"
$list = ollama list | Out-String
if ($list -notmatch [regex]::Escape($model)) {
    Write-Host "Dang tai model $model ..."
    ollama pull $model
}

exit 0
