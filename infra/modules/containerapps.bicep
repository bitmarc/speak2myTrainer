// Entorno de Container Apps (Consumption), la web de Streamlit y el job de análisis, ambos con
// escalado a cero. La identidad asignada por el usuario se comparte entre la web y el job para
// asignar los roles de data plane una sola vez.
param location string
param tags object
param prefix string
param suffix string

param logAnalyticsWorkspaceName string

@description('Imagen pública en GHCR, p. ej. ghcr.io/<owner>/speak2mytrainer:<sha>. La usan la web y el job.')
param webImage string

@description('Cuenta de Storage y cola que disparan el job.')
param storageAccountName string
param queueName string

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

// Job disparado por la cola: KEDA mira la longitud de `attempts` con la identidad administrada.
// Una ejecución a la vez, porque Speech F0 admite una sola solicitud concurrente.
resource job 'Microsoft.App/jobs@2025-01-01' = {
  name: 'caj-${prefix}-worker'
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
      triggerType: 'Event'
      // Más que el peor caso: audio de 10 min a ~0.5x, más el LLM y un reintento.
      replicaTimeout: 1800
      // Los reintentos los maneja la cola (dequeue count), no Container Apps.
      replicaRetryLimit: 0
      eventTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
        scale: {
          minExecutions: 0
          maxExecutions: 1
          pollingInterval: 20
          rules: [
            {
              name: 'attempts-queue'
              type: 'azure-queue'
              metadata: {
                accountName: storageAccountName
                queueName: queueName
                queueLength: '1'
              }
              identity: identity.id
            }
          ]
        }
      }
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: webImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(
            [
              { name: 'S2MT_MODE', value: 'job' }
              { name: 'S2MT_ENV', value: 'azure' }
              { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            ],
            appSettings
          )
        }
      ]
    }
  }
}

output identityPrincipalId string = identity.properties.principalId
output identityClientId string = identity.properties.clientId
output webFqdn string = web.properties.configuration.ingress.fqdn
output webName string = web.name
output jobName string = job.name
output identityId string = identity.id
output googleRedirectUri string = 'https://${web.properties.configuration.ingress.fqdn}/.auth/login/google/callback'
