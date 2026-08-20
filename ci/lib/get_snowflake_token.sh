#!/usr/bin/env sh
# Exchanges Azure AD client-credentials for an access token scoped to the
# Snowflake EXTERNAL_OAUTH security integration, and prints it to stdout.
#
# Required env vars: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
# SNOWFLAKE_OAUTH_SCOPE (the scope/resource registered against the
# Snowflake security integration, e.g. api://<app-id>/.default).
set -eu

TOKEN_RESPONSE=$(curl -sf -X POST \
  "https://login.microsoftonline.com/${AZURE_TENANT_ID}/oauth2/v2.0/token" \
  -d "client_id=${AZURE_CLIENT_ID}" \
  -d "client_secret=${AZURE_CLIENT_SECRET}" \
  -d "scope=${SNOWFLAKE_OAUTH_SCOPE}" \
  -d "grant_type=client_credentials")

echo "$TOKEN_RESPONSE" | jq -r '.access_token'
