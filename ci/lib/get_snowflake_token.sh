#!/usr/bin/env sh
# Exchanges Azure AD client-credentials for a Snowflake EXTERNAL_OAUTH
# access token and prints it to stdout.
#
# Required env vars: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
# SNOWFLAKE_OAUTH_SCOPE (e.g. api://<app-id>/.default).
set -eu

TOKEN_RESPONSE=$(curl -sf -X POST \
  "https://login.microsoftonline.com/${AZURE_TENANT_ID}/oauth2/v2.0/token" \
  -d "client_id=${AZURE_CLIENT_ID}" \
  -d "client_secret=${AZURE_CLIENT_SECRET}" \
  -d "scope=${SNOWFLAKE_OAUTH_SCOPE}" \
  -d "grant_type=client_credentials")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')

if [ -z "$ACCESS_TOKEN" ]; then
  echo "get_snowflake_token.sh: response had no access_token field" >&2
  exit 1
fi

echo "$ACCESS_TOKEN"
