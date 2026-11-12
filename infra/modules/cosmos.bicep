// Cosmos DB NoSQL en nivel gratuito (1000 RU/s y 25 GB). El throughput se comparte a nivel de
// base de datos entre los tres contenedores, y el límite de la cuenta impide pasar de 1000 RU/s.
param name string
param location string
param tags object

param databaseName string = 'speak2mytrainer'
param containerNames array = ['users', 'practices', 'attempts']

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: name
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: true
    disableLocalAuth: true
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capacity: {
      totalThroughputLimit: 1000
    }
    backupPolicy: {
      type: 'Periodic'
      periodicModeProperties: {
        backupIntervalInMinutes: 1440
        backupRetentionIntervalInHours: 48
        backupStorageRedundancy: 'Local'
      }
    }
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: account
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
    options: {
      throughput: 1000
    }
  }
}

resource containers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = [
  for containerName in containerNames: {
    parent: database
    name: containerName
    properties: {
      resource: {
        id: containerName
        partitionKey: {
          paths: ['/userId']
          kind: 'Hash'
          version: 2
        }
      }
    }
  }
]

output id string = account.id
output name string = account.name
output endpoint string = account.properties.documentEndpoint
output databaseName string = database.name
