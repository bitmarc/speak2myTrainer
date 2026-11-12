using 'main.bicep'

// Los valores personales llegan por variables de entorno (ver scripts/deploy-infra.ps1),
// así el repo público no contiene IDs ni correos.
param developerPrincipalId = readEnvironmentVariable('S2MT_DEVELOPER_PRINCIPAL_ID', '00000000-0000-0000-0000-000000000000')
param budgetEmail = readEnvironmentVariable('S2MT_BUDGET_EMAIL', 'alerts@example.com')
param location = 'eastus2'
