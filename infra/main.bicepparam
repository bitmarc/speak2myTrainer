using 'main.bicep'

// Los valores personales llegan por variables de entorno (ver scripts/deploy-infra.ps1),
// así el repo público no contiene IDs, correos ni secretos.
param developerPrincipalId = readEnvironmentVariable('S2MT_DEVELOPER_PRINCIPAL_ID', '00000000-0000-0000-0000-000000000000')
param budgetEmail = readEnvironmentVariable('S2MT_BUDGET_EMAIL', 'alerts@example.com')
param location = 'eastus2'

param deployApps = bool(readEnvironmentVariable('S2MT_DEPLOY_APPS', 'false'))
param webImage = readEnvironmentVariable('S2MT_WEB_IMAGE', '')
param googleClientId = readEnvironmentVariable('S2MT_GOOGLE_CLIENT_ID', '')
param googleClientSecret = readEnvironmentVariable('S2MT_GOOGLE_CLIENT_SECRET', '')
param adminEmail = readEnvironmentVariable('S2MT_ADMIN_EMAIL', '')
