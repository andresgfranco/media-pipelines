#!/bin/bash
# Script to run Streamlit app
# Used by Streamlit Cloud for deployment

streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
