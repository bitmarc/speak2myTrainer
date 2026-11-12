// Azure AI Speech. F0 es el primario (5 h de STT y 0.5 M caracteres de TTS al mes).
// El recurso S0 de failover se agrega en la Fase 2. Sin llaves: auth con Entra, que exige
// subdominio propio.
param name string
param location string
param tags object

@allowed(['F0', 'S0'])
param sku string = 'F0'

resource speech 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'SpeechServices'
  sku: {
    name: sku
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

output id string = speech.id
output name string = speech.name
output endpoint string = speech.properties.endpoint
