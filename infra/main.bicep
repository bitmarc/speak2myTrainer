// Infraestructura de speak2myTrainer. Scope de suscripción: crea el grupo de recursos y el
// presupuesto, y delega el resto a módulos con scope de grupo de recursos.
targetScope = 'subscription'

@description('Región de todos los recursos.')
param location string = 'eastus2'

@description('Nombre del grupo de recursos.')
param resourceGroupName string = 'rg-speak2mytrainer'

@description('Prefijo corto para los nombres de recursos.')
@maxLength(6)
param prefix string = 's2mt'

@description('Object ID (Entra) del desarrollador que recibe roles de data plane para trabajar en local.')
param developerPrincipalId string

@description('Correo que recibe las alertas de presupuesto.')
param budgetEmail string

@description('Tope mensual en USD.')
param budgetAmount int = 15

@description('Primer día del mes actual; los presupuestos deben empezar el día 1.')
param budgetStartDate string = utcNow('yyyy-MM-01')

@description('Nombre del deployment de transcripción. Es configuración, no código.')
param transcribeDeploymentName string = 'gpt-4o-mini-transcribe'

@description('Nombre del deployment del LLM de análisis.')
param llmDeploymentName string = 'gpt-4.1-mini'

var tags = {
  project: 'speak2mytrainer'
  managedBy: 'bicep'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

var suffix = uniqueString(subscription().id, resourceGroupName)

module monitoring 'modules/monitoring.bicep' = {
  scope: rg
  params: {
    name: 'log-${prefix}-${suffix}'
    location: location
    tags: tags
  }
}

module speech 'modules/speech.bicep' = {
  scope: rg
  params: {
    name: 'spch-${prefix}-${suffix}'
    location: location
    tags: tags
  }
}

module openai 'modules/openai.bicep' = {
  scope: rg
  params: {
    name: 'oai-${prefix}-${suffix}'
    location: location
    tags: tags
    transcribeDeploymentName: transcribeDeploymentName
    llmDeploymentName: llmDeploymentName
  }
}

module cosmos 'modules/cosmos.bicep' = {
  scope: rg
  params: {
    name: 'cosmos-${prefix}-${suffix}'
    location: location
    tags: tags
  }
}

module storage 'modules/storage.bicep' = {
  scope: rg
  params: {
    name: 'st${prefix}${take(suffix, 10)}'
    location: location
    tags: tags
  }
}

module developerRoles 'modules/roles.bicep' = {
  scope: rg
  params: {
    principalId: developerPrincipalId
    principalType: 'User'
    speechAccountName: speech.outputs.name
    openaiAccountName: openai.outputs.name
    cosmosAccountName: cosmos.outputs.name
    storageAccountName: storage.outputs.name
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'budget-${prefix}'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
    }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [budgetEmail]
      }
      actual80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [budgetEmail]
      }
      actual100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [budgetEmail]
      }
    }
  }
}

output resourceGroupName string = rg.name
output logAnalyticsWorkspaceId string = monitoring.outputs.id
output speechResourceId string = speech.outputs.id
output speechEndpoint string = speech.outputs.endpoint
output speechRegion string = location
output openaiEndpoint string = openai.outputs.endpoint
output transcribeDeployment string = transcribeDeploymentName
output llmDeployment string = llmDeploymentName
output cosmosEndpoint string = cosmos.outputs.endpoint
output cosmosDatabase string = cosmos.outputs.databaseName
output storageAccountName string = storage.outputs.name
output blobEndpoint string = storage.outputs.blobEndpoint
output queueEndpoint string = storage.outputs.queueEndpoint
