<#
.SYNOPSIS
  Configura el login sin secretos (OIDC) de GitHub Actions en Azure. Es idempotente.

.DESCRIPTION
  Crea la app registration `gh-speak2mytrainer`, con credenciales federadas para la rama main y
  los pull requests del repo, y le asigna roles mínimos:
    - Container Apps Contributor sobre la web y Container Apps Jobs Contributor sobre el job,
      para actualizar la imagen;
    - Managed Identity Operator sobre la identidad de las apps, que ambos usan;
    - Cognitive Services OpenAI User sobre Azure OpenAI, para el set de evaluación.
  Después guarda AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID y
  AZURE_OPENAI_ENDPOINT como variables del repo (no son secretos).

  Requiere que las apps ya estén desplegadas (deploy-infra.ps1 -WebImage ...) y `gh auth login`.
#>
param(
  [string]$Repo = 'bitmarc/speak2myTrainer',
  [string]$AppName = 'gh-speak2mytrainer'
)

$ErrorActionPreference = 'Stop'

$outputs = az deployment sub show --name speak2mytrainer --query properties.outputs -o json | ConvertFrom-Json
$rg = $outputs.resourceGroupName.value
if (-not $outputs.webName.value) { throw 'Primero despliega las apps: deploy-infra.ps1 -WebImage ...' }
$subscription = az account show --query id -o tsv
$tenant = az account show --query tenantId -o tsv

$appId = az ad app list --display-name $AppName --query '[0].appId' -o tsv
if (-not $appId) {
  $appId = az ad app create --display-name $AppName --query appId -o tsv
  Write-Host "App registration creada: $appId"
}
$principalId = az ad sp list --filter "appId eq '$appId'" --query '[0].id' -o tsv
if (-not $principalId) { $principalId = az ad sp create --id $appId --query id -o tsv }

$existing = az ad app federated-credential list --id $appId --query '[].subject' -o tsv
$subjects = @{
  'main'         = "repo:${Repo}:ref:refs/heads/main"
  'pull-request' = "repo:${Repo}:pull_request"
}
foreach ($name in $subjects.Keys) {
  if ($existing -notcontains $subjects[$name]) {
    $credential = @{
      name      = $name
      issuer    = 'https://token.actions.githubusercontent.com'
      subject   = $subjects[$name]
      audiences = @('api://AzureADTokenExchange')
    } | ConvertTo-Json -Compress
    $file = New-TemporaryFile
    Set-Content -Path $file -Value $credential -Encoding utf8
    az ad app federated-credential create --id $appId --parameters "@$file" --output none
    Remove-Item $file
    Write-Host "Credencial federada: $($subjects[$name])"
  }
}

function Grant([string]$Role, [string]$Scope) {
  $found = az role assignment list --assignee $principalId --role $Role --scope $Scope --query '[0].id' -o tsv
  if (-not $found) {
    az role assignment create --assignee-object-id $principalId --assignee-principal-type ServicePrincipal `
      --role $Role --scope $Scope --output none
    Write-Host "Rol $Role en $(Split-Path -Leaf $Scope)"
  }
}

$rgId = "/subscriptions/$subscription/resourceGroups/$rg"
$openaiId = az cognitiveservices account list -g $rg --query "[?kind=='OpenAI'].id | [0]" -o tsv
Grant 'Container Apps Contributor' "$rgId/providers/Microsoft.App/containerApps/$($outputs.webName.value)"
Grant 'Container Apps Jobs Contributor' "$rgId/providers/Microsoft.App/jobs/$($outputs.jobName.value)"
Grant 'Managed Identity Operator' $outputs.identityId.value
Grant 'Cognitive Services OpenAI User' $openaiId

gh variable set AZURE_CLIENT_ID --repo $Repo --body $appId
gh variable set AZURE_TENANT_ID --repo $Repo --body $tenant
gh variable set AZURE_SUBSCRIPTION_ID --repo $Repo --body $subscription
gh variable set AZURE_OPENAI_ENDPOINT --repo $Repo --body $outputs.openaiEndpoint.value
gh variable set AZURE_OPENAI_LLM_DEPLOYMENT --repo $Repo --body $outputs.llmDeployment.value
Write-Host 'Listo: GitHub Actions puede desplegar y correr la evaluación sin secretos.'
