#!/bin/bash
# Helper script to deploy with Pixabay API key configured
# This ensures the API key is set as an environment variable before deployment

set -e

# Pixabay API Key
export PIXABAY_API_KEY="53206659-9f4032e12feaa7f27f3fcdea8"

echo "🔑 Pixabay API Key configured"
echo "🚀 Starting deployment..."
echo ""

# Run the main deployment script
./scripts/deploy_to_aws.sh
