<#
.SYNOPSIS
  Despliega infra/main.bicep a nivel de suscripción y vuelca los outputs a .env.

.PARAMETER BudgetEmail
  Correo para las alertas de presupuesto. Por defecto, el usuario de la sesión de az.

.PARAMETER WebImage
  Imagen de GHCR para la web. Si se indica, también se despliegan Container Apps.

.PARAMETER GoogleClientId
  Client ID de Google OAuth. Con él (y el secreto) se activa Easy Auth en la web.

.PARAMETER GoogleClientSecret
  Secreto de Google OAuth. Si no se pasa y hay GoogleClientId, se pide por consola.

.PARAMETER WhatIf
  Solo muestra los cambios (az deployment sub what-if) sin aplicarlos.
#>
param(
  [string]$BudgetEmail,
  [string]$Location = 'eastus2',
  [string]$WebImage,
  [string]$GoogleClientId,
  [securestring]$GoogleClientSecret,
  [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$env:S2MT_DEVELOPER_PRINCIPAL_ID = az ad signed-in-user show --query id -o tsv
if (-not $BudgetEmail) { $BudgetEmail = az account show --query user.name -o tsv }
$env:S2MT_BUDGET_EMAIL = $BudgetEmail

$env:S2MT_DEPLOY_APPS = if ($WebImage) { 'true' } else { 'false' }
$env:S2MT_WEB_IMAGE = $WebImage
$env:S2MT_GOOGLE_CLIENT_ID = $GoogleClientId
$env:S2MT_GOOGLE_CLIENT_SECRET = ''
if ($GoogleClientId) {
  if (-not $GoogleClientSecret) { $GoogleClientSecret = Read-Host 'Google client secret' -AsSecureString }
  $env:S2MT_GOOGLE_CLIENT_SECRET = [System.Net.NetworkCredential]::new('', $GoogleClientSecret).Password
}

$deploymentName = 'speak2mytrainer'
$common = @(
  '--name', $deploymentName,
  '--location', $Location,
  '--parameters', (Join-Path $root 'infra/main.bicepparam')
)

if ($WhatIf) {
  az deployment sub what-if @common
  exit $LASTEXITCODE
}

try {
  az deployment sub create @common --output none
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
  Remove-Item Env:S2MT_GOOGLE_CLIENT_SECRET -ErrorAction SilentlyContinue
}

$outputs = az deployment sub show --name $deploymentName --query properties.outputs -o json | ConvertFrom-Json

$lines = @(
  "# Generado por scripts/deploy-infra.ps1. No se versiona.",
  "S2MT_ENV=local",
  "AZURE_OPENAI_ENDPOINT=$($outputs.openaiEndpoint.value)",
  "AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT=$($outputs.transcribeDeployment.value)",
  "AZURE_OPENAI_LLM_DEPLOYMENT=$($outputs.llmDeployment.value)",
  "AZURE_SPEECH_RESOURCE_ID=$($outputs.speechResourceId.value)",
  "AZURE_SPEECH_ENDPOINT=$($outputs.speechEndpoint.value)",
  "AZURE_SPEECH_REGION=$($outputs.speechRegion.value)",
  "AZURE_COSMOS_ENDPOINT=$($outputs.cosmosEndpoint.value)",
  "AZURE_COSMOS_DATABASE=$($outputs.cosmosDatabase.value)",
  "AZURE_STORAGE_BLOB_ENDPOINT=$($outputs.blobEndpoint.value)",
  "AZURE_STORAGE_QUEUE_ENDPOINT=$($outputs.queueEndpoint.value)"
)
$lines | Set-Content -Path (Join-Path $root '.env') -Encoding utf8
Write-Host "Listo. Outputs escritos en .env"
if ($outputs.webFqdn.value) {
  Write-Host "Web:                https://$($outputs.webFqdn.value)"
  Write-Host "Redirect URI (Google): $($outputs.googleRedirectUri.value)"
}
