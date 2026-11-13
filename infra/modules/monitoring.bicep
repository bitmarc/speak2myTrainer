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

// Application Insights sobre el mismo workspace: hereda su retención y su tope diario. Sin
// autenticación local, así que la ingesta exige un token de Entra (rol Monitoring Metrics
// Publisher) y la cadena de conexión no sirve como llave (ADR 0005).
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${name}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    DisableLocalAuth: true
    IngestionMode: 'LogAnalytics'
  }
}

output id string = workspace.id
output name string = workspace.name
output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
