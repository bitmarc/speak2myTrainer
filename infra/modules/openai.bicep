// Azure OpenAI con los deployments de transcripción y de análisis de texto.
param name string
param location string
param tags object

param transcribeDeploymentName string
param transcribeModelVersion string = '2025-12-15'
@description('Capacidad en miles de tokens por minuto.')
param transcribeCapacity int = 10

param llmDeploymentName string
param llmModelVersion string = '2025-04-14'
param llmCapacity int = 50

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: name
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource transcribe 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: transcribeDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: transcribeCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini-transcribe'
      version: transcribeModelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

// Los deployments de una misma cuenta no se pueden crear en paralelo.
resource llm 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: llmDeploymentName
  dependsOn: [transcribe]
  sku: {
    name: 'GlobalStandard'
    capacity: llmCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1-mini'
      version: llmModelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

output id string = account.id
output name string = account.name
output endpoint string = account.properties.endpoint
