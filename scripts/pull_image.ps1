param(
    [Parameter(Mandatory=$true)]
    [string]$ImageTag
)

$ErrorActionPreference = "Stop"

Write-Host "🔄 Pulling Docker image: $ImageTag..." -ForegroundColor Cyan

try {
    docker pull $ImageTag
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Successfully pulled $ImageTag" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to pull $ImageTag" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Error pulling $ImageTag: $_" -ForegroundColor Red
    exit 1
}
