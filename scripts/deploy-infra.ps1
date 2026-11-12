<#
.SYNOPSIS
  Despliega infra/main.bicep a nivel de suscripción y vuelca los outputs a .env.

.PARAMETER BudgetEmail
  Correo para las alertas de presupuesto. Por defecto, el usuario de la sesión de az.

.PARAMETER WhatIf
  Solo muestra los cambios (az deployment sub what-if) sin aplicarlos.
#>
param(
  [string]$BudgetEmail,
  [string]$Location = 'eastus2',
  [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$env:S2MT_DEVELOPER_PRINCIPAL_ID = az ad signed-in-user show --query id -o tsv
if (-not $BudgetEmail) { $BudgetEmail = az account show --query user.name -o tsv }
$env:S2MT_BUDGET_EMAIL = $BudgetEmail

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

az deployment sub create @common --output none
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

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
