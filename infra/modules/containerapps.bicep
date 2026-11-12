// Entorno de Container Apps (Consumption) y la web de Streamlit con escalado a cero.
// La identidad asignada por el usuario se comparte entre la web y el job (Fase 1) para
// asignar los roles de data plane una sola vez.
param location string
param tags object
param prefix string
param suffix string

param logAnalyticsWorkspaceName string

@description('Imagen pública en GHCR, p. ej. ghcr.io/<owner>/speak2mytrainer:<sha>.')
param webImage string

@description('Client ID de Google OAuth. Vacío = la web se publica sin Easy Auth (solo Fase 0).')
param googleClientId string = ''

@secure()
param googleClientSecret string = ''

param appSettings array = []

var authEnabled = !empty(googleClientId)

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}-${suffix}'
  location: location
  tags: tags
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${prefix}-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${prefix}-web'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8501
        transport: 'auto'
        allowInsecure: false
      }
      secrets: authEnabled
        ? [
            {
              name: 'google-client-secret'
              value: googleClientSecret
            }
          ]
        : []
    }
    template: {
      containers: [
        {
          name: 'web'
          image: webImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(
            [
              { name: 'S2MT_MODE', value: 'web' }
              { name: 'S2MT_ENV', value: 'azure' }
              { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            ],
            appSettings
          )
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (authEnabled) {
  parent: web
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'google'
    }
    identityProviders: {
      google: {
        enabled: true
        registration: {
          clientId: googleClientId
          clientSecretSettingName: 'google-client-secret'
        }
        login: {
          scopes: ['openid', 'profile', 'email']
        }
      }
    }
  }
}

output identityPrincipalId string = identity.properties.principalId
output identityClientId string = identity.properties.clientId
output webFqdn string = web.properties.configuration.ingress.fqdn
output googleRedirectUri string = 'https://${web.properties.configuration.ingress.fqdn}/.auth/login/google/callback'
