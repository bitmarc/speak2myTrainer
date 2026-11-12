// Log Analytics con retención mínima y tope diario para no salir de los 5 GB gratis al mes.
param name string
param location string
param tags object

@description('Tope diario de ingesta en GB (~5 GB al mes).')
param dailyQuotaGb string = '0.16'

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: json(dailyQuotaGb)
    }
  }
}

output id string = workspace.id
output name string = workspace.name
