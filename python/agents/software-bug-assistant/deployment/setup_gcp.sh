#!/bin/bash

# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# The script will prompt for PROJECT_ID if not set from GOOGLE_CLOUD_PROJECT.
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-""}
REGION="us-central1"
SQL_INSTANCE_NAME="software-assistant"
SQL_DATABASE_NAME="tickets-db"
SQL_ROOT_PASSWORD="admin" # Change if needed for production
TOOLBOX_SERVICE_ACCOUNT="toolbox-identity"
TOOLBOX_SERVICE_NAME="toolbox"
AGENT_SERVICE_NAME="software-bug-assistant"
ARTIFACT_REPO="adk-samples"

# --- Helper Functions ---
function print_header() {
  echo ""
  echo "========================================================================"
  echo "$1"
  echo "========================================================================"
}

# --- Main Script ---

# 1. Project and Auth Setup
print_header "Step 1: Authenticating and setting up Google Cloud project"
if [[ -z "$PROJECT_ID" ]]; then
  read -p "Please enter your Google Cloud Project ID: " PROJECT_ID
fi

if [[ -z "$PROJECT_ID" ]]; then
  echo "Error: Project ID is required."
  exit 1
fi

gcloud config set project $PROJECT_ID
echo "Project set to $PROJECT_ID"

echo "Enabling necessary Google Cloud APIs..."
gcloud services enable sqladmin.googleapis.com \
   compute.googleapis.com \
   cloudresourcemanager.googleapis.com \
   servicenetworking.googleapis.com \
   aiplatform.googleapis.com \
   run.googleapis.com \
   cloudbuild.googleapis.com \
   artifactregistry.googleapis.com \
   iam.googleapis.com \
   secretmanager.googleapis.com

echo "APIs enabled."

# 2. Create Cloud SQL Instance
print_header "Step 2: Creating Cloud SQL (Postgres) instance"
if gcloud sql instances describe $SQL_INSTANCE_NAME &>/dev/null; then
  echo "Cloud SQL instance '$SQL_INSTANCE_NAME' already exists. Skipping creation."
else
  gcloud sql instances create $SQL_INSTANCE_NAME \
     --database-version=POSTGRES_16 \
     --tier=db-custom-1-3840 \
     --region=$REGION \
     --edition=ENTERPRISE \
     --enable-google-ml-integration \
     --database-flags cloudsql.enable_google_ml_integration=on \
     --root-password=$SQL_ROOT_PASSWORD
fi

# 3. Create Database and Grant Permissions
print_header "Step 3: Creating database and granting Vertex AI permissions"
if gcloud sql databases describe $SQL_DATABASE_NAME --instance=$SQL_INSTANCE_NAME &>/dev/null; then
  echo "Database '$SQL_DATABASE_NAME' already exists. Skipping creation."
else
  gcloud sql databases create $SQL_DATABASE_NAME --instance=$SQL_INSTANCE_NAME
fi

SERVICE_ACCOUNT_EMAIL=$(gcloud sql instances describe $SQL_INSTANCE_NAME --format="value(serviceAccountEmailAddress)")
echo "Granting Vertex AI User role to Cloud SQL service account: $SERVICE_ACCOUNT_EMAIL"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
    --role="roles/aiplatform.user" \
    --condition=None

echo ""
echo "------------------------------------------------------------------------"
echo "MANUAL STEP REQUIRED:"
echo "Please go to the Cloud SQL Studio for the '$SQL_INSTANCE_NAME' instance."
echo "Connect to the '$SQL_DATABASE_NAME' database."
echo "Run the SQL commands from steps 4, 5, 6, 7, and 8 in the README.md to set up tables and data."
read -p "Press [Enter] to continue after you have completed the manual SQL steps..."
echo "------------------------------------------------------------------------"


# 9. Deploy MCP Toolbox - Setup Service Account and Secret
print_header "Step 9: Setting up service account and secret for MCP Toolbox"
SA_EMAIL="${TOOLBOX_SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe $SA_EMAIL &>/dev/null; then
  gcloud iam service-accounts create $TOOLBOX_SERVICE_ACCOUNT
fi

echo "Granting permissions to service account..."
gcloud projects add-iam-policy-binding $PROJECT_ID --member serviceAccount:$SA_EMAIL --role roles/secretmanager.secretAccessor --condition=None
gcloud projects add-iam-policy-binding $PROJECT_ID --member serviceAccount:$SA_EMAIL --role roles/cloudsql.client --condition=None

if ! gcloud secrets describe tools &>/dev/null; then
  echo "Creating Secret Manager secret 'tools' from deployment/mcp-toolbox/tools.yaml..."
  gcloud secrets create tools --data-file=deployment/mcp-toolbox/tools.yaml
fi

# 10. Deploy MCP Toolbox to Cloud Run
print_header "Step 10: Deploying MCP Toolbox to Cloud Run"
echo "Deploying MCP Toolbox service..."
gcloud run deploy $TOOLBOX_SERVICE_NAME --image us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:latest --service-account $TOOLBOX_SERVICE_ACCOUNT --region $REGION --set-secrets "/app/tools.yaml=tools:latest" --set-env-vars="PROJECT_ID=$PROJECT_ID,DB_USER=postgres,DB_PASS=$SQL_ROOT_PASSWORD" --args="--tools-file=/app/tools.yaml","--address=0.0.0.0","--port=8080" --allow-unauthenticated
MCP_TOOLBOX_URL=$(gcloud run services describe $TOOLBOX_SERVICE_NAME --region $REGION --format "value(status.url)")
echo "MCP Toolbox deployed to: $MCP_TOOLBOX_URL"

# 11. Create Artifact Registry
print_header "Step 11: Creating Artifact Registry repository"
if ! gcloud artifacts repositories describe $ARTIFACT_REPO --location=$REGION &>/dev/null; then
  gcloud artifacts repositories create $ARTIFACT_REPO --repository-format=docker --location=$REGION --description="Repository for ADK Python sample agents"
fi

# 12. Build and Push Agent Image
print_header "Step 12: Building and pushing agent container image"
gcloud builds submit --region=$REGION --tag ${REGION}-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REPO/$AGENT_SERVICE_NAME:latest

# 13. Deploy Agent to Cloud Run
print_header "Step 13: Deploying agent to Cloud Run"
if [[ -z "$GITHUB_PERSONAL_ACCESS_TOKEN" ]]; then echo "Error: GITHUB_PERSONAL_ACCESS_TOKEN is not set." && exit 1; fi

if [[ "$GOOGLE_GENAI_USE_VERTEXAI" == "TRUE" ]]; then
  echo "Deploying with Vertex AI configuration..."
  ENV_VARS="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=TRUE,MCP_TOOLBOX_URL=$MCP_TOOLBOX_URL,GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN"
else
  if [[ -z "$GOOGLE_API_KEY" ]]; then echo "Error: GOOGLE_API_KEY is not set." && exit 1; fi
  echo "Deploying with Gemini API Key (AI Studio) configuration..."
  ENV_VARS="GOOGLE_API_KEY=$GOOGLE_API_KEY,MCP_TOOLBOX_URL=$MCP_TOOLBOX_URL,GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN"
fi

gcloud run deploy $AGENT_SERVICE_NAME --image=${REGION}-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REPO/$AGENT_SERVICE_NAME:latest --region=$REGION --allow-unauthenticated --set-env-vars="$ENV_VARS"
AGENT_URL=$(gcloud run services describe $AGENT_SERVICE_NAME --region $REGION --format "value(status.url)")

print_header "Deployment Complete!"
echo "Software Bug Assistant URL: $AGENT_URL"
echo "MCP Toolbox URL: $MCP_TOOLBOX_URL"
