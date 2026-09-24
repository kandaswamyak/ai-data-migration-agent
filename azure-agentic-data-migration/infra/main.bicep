// =============================================================================
// main.bicep
//
// Azure Agentic Data Migration — Infrastructure Template
//
// Deploys all Azure resources needed for the AI-driven migration POC:
//   • Azure OpenAI (GPT-4.1)
//   • Azure SQL Database (migration target)
//   • Azure Key Vault
//   • Azure Storage Account (plans, mappings, logs, reports)
//   • Azure Data Factory (with managed identity)
//   • Application Insights + Log Analytics
//   • Logic Apps (5 workflow stubs)
//   • Role assignments for managed identities
//
// USAGE:
//   az deployment group create \
//     --resource-group rg-data-migration \
//     --template-file main.bicep \
//     --parameters @parameters.example.json
// =============================================================================

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

@description('Base name prefix for all resources (lowercase, no spaces).')
@minLength(3)
@maxLength(18)
param baseName string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Azure SQL administrator login name.')
@secure()
param sqlAdminLogin string

@description('Azure SQL administrator password.')
@secure()
param sqlAdminPassword string

@description('Azure SQL Database SKU name.')
@allowed([
  'Basic'
  'S0'
  'S1'
  'S2'
  'S3'
  'P1'
  'P2'
  'GP_Gen5_2'
])
param sqlSkuName string = 'S1'

@description('Azure OpenAI SKU.')
@allowed([
  'S0'
])
param openAiSkuName string = 'S0'

@description('GPT-4.1 model deployment capacity (TPM in thousands).')
@minValue(1)
@maxValue(80)
param gptCapacity int = 10

@description('Storage account SKU.')
@allowed([
  'Standard_LRS'
  'Standard_GRS'
  'Standard_ZRS'
])
param storageSkuName string = 'Standard_LRS'

@description('Log Analytics workspace SKU.')
@allowed([
  'PerGB2018'
  'Free'
])
param logAnalyticsSkuName string = 'PerGB2018'

@description('Tags applied to every resource.')
param tags object = {
  project: 'ai-data-migration'
  environment: 'poc'
}

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var uniqueSuffix = uniqueString(resourceGroup().id, baseName)
var sqlServerName = '${baseName}-sql-${uniqueSuffix}'
var sqlDatabaseName = '${baseName}-db'
var openAiAccountName = '${baseName}-oai-${uniqueSuffix}'
var keyVaultName = '${baseName}-kv-${uniqueSuffix}'
var storageAccountName = toLower(replace('${baseName}st${uniqueSuffix}', '-', ''))
var dataFactoryName = '${baseName}-adf-${uniqueSuffix}'
var logAnalyticsName = '${baseName}-law-${uniqueSuffix}'
var appInsightsName = '${baseName}-ai-${uniqueSuffix}'

// Logic App names
var logicAppNames = [
  '${baseName}-la-schema-analysis'
  '${baseName}-la-approval-workflow'
  '${baseName}-la-migration-orchestrator'
  '${baseName}-la-validation-runner'
  '${baseName}-la-notification-sender'
]

// Storage container names
var storageContainers = [
  'plans'
  'mappings'
  'logs'
  'reports'
]

// Built-in role definition IDs
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// ---------------------------------------------------------------------------
// 1. Log Analytics Workspace
// ---------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: logAnalyticsSkuName
    }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------------------
// 2. Application Insights
// ---------------------------------------------------------------------------
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
  }
}

// ---------------------------------------------------------------------------
// 3. Azure OpenAI Account + GPT-4.1 Deployment
// ---------------------------------------------------------------------------
resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: openAiAccountName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: openAiSkuName
  }
  properties: {
    customSubDomainName: openAiAccountName
    publicNetworkAccess: 'Enabled'
  }
}

resource gpt41Deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openAiAccount
  name: 'gpt-41'
  sku: {
    name: 'Standard'
    capacity: gptCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1'
      version: '2025-04-14'
    }
  }
}

// ---------------------------------------------------------------------------
// 4. Azure SQL Server + Database
// ---------------------------------------------------------------------------
resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: sqlServerName
  location: location
  tags: tags
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: sqlDatabaseName
  location: location
  tags: tags
  sku: {
    name: sqlSkuName
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: 268435456000  // ~250 GB
    zoneRedundant: false
  }
}

// Allow Azure services to access the SQL Server
resource sqlFirewallAllowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAllAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ---------------------------------------------------------------------------
// 5. Azure Key Vault
// ---------------------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false // POC — set true for production
  }
}

// ---------------------------------------------------------------------------
// 6. Azure Storage Account + Containers
// ---------------------------------------------------------------------------
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take(storageAccountName, 24)
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: storageSkuName
  }
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for containerName in storageContainers: {
    parent: blobService
    name: containerName
    properties: {
      publicAccess: 'None'
    }
  }
]

// ---------------------------------------------------------------------------
// 7. Azure Data Factory (system-assigned managed identity)
// ---------------------------------------------------------------------------
resource dataFactory 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: dataFactoryName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

// ---------------------------------------------------------------------------
// 8. Logic Apps (5 workflow stubs — Consumption tier)
// ---------------------------------------------------------------------------
resource logicApps 'Microsoft.Logic/workflows@2019-05-01' = [
  for laName in logicAppNames: {
    name: laName
    location: location
    tags: tags
    identity: {
      type: 'SystemAssigned'
    }
    properties: {
      state: 'Enabled'
      definition: {
        '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
        contentVersion: '1.0.0.0'
        triggers: {
          manual: {
            type: 'Request'
            kind: 'Http'
            inputs: {
              schema: {}
            }
          }
        }
        actions: {
          Placeholder: {
            type: 'Compose'
            inputs: 'TODO: Implement ${laName} workflow logic'
            runAfter: {}
          }
        }
        outputs: {}
      }
    }
  }
]

// ---------------------------------------------------------------------------
// 9. Role Assignments — Data Factory MI → Key Vault Secrets User
// ---------------------------------------------------------------------------
resource adfKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, dataFactory.id, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      keyVaultSecretsUserRoleId
    )
    principalId: dataFactory.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// 10. Role Assignments — Data Factory MI → Storage Blob Data Contributor
// ---------------------------------------------------------------------------
resource adfStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, dataFactory.id, storageBlobDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageBlobDataContributorRoleId
    )
    principalId: dataFactory.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// 11. Role Assignments — Logic App MIs → Key Vault Secrets User
// ---------------------------------------------------------------------------
resource logicAppKeyVaultRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for i in range(0, length(logicAppNames)): {
    name: guid(keyVault.id, logicApps[i].id, keyVaultSecretsUserRoleId)
    scope: keyVault
    properties: {
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        keyVaultSecretsUserRoleId
      )
      principalId: logicApps[i].identity.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

// ---------------------------------------------------------------------------
// 12. Role Assignments — Logic App MIs → Storage Blob Data Contributor
// ---------------------------------------------------------------------------
resource logicAppStorageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for i in range(0, length(logicAppNames)): {
    name: guid(storageAccount.id, logicApps[i].id, storageBlobDataContributorRoleId)
    scope: storageAccount
    properties: {
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        storageBlobDataContributorRoleId
      )
      principalId: logicApps[i].identity.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

@description('Azure SQL Server FQDN')
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName

@description('Azure SQL Database name')
output sqlDatabaseName string = sqlDatabase.name

@description('Azure OpenAI endpoint')
output openAiEndpoint string = openAiAccount.properties.endpoint

@description('Azure OpenAI GPT-4.1 deployment name')
output gptDeploymentName string = gpt41Deployment.name

@description('Key Vault URI')
output keyVaultUri string = keyVault.properties.vaultUri

@description('Storage Account name')
output storageAccountName string = storageAccount.name

@description('Data Factory name')
output dataFactoryName string = dataFactory.name

@description('Data Factory principal ID (for additional RBAC)')
output dataFactoryPrincipalId string = dataFactory.identity.principalId

@description('Application Insights instrumentation key')
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey

@description('Application Insights connection string')
output appInsightsConnectionString string = appInsights.properties.ConnectionString

@description('Log Analytics workspace ID')
output logAnalyticsWorkspaceId string = logAnalytics.properties.customerId

@description('Logic App names')
output logicAppNames array = [for i in range(0, length(logicAppNames)): logicApps[i].name]
