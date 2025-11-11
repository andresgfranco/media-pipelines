#!/bin/bash
# Script to run Streamlit app
# Used by Streamlit Cloud for deployment or local development

# Load AWS deployment config if available (created by deploy_to_aws.sh)
if [ -f "../.aws-deployment-config" ]; then
    echo "Loading AWS deployment configuration..."
    source ../.aws-deployment-config
fi

# Run Streamlit
# If PORT is set (e.g., by Streamlit Cloud), use it; otherwise use default
if [ -n "$PORT" ]; then
    streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
else
    streamlit run app.py
fi
