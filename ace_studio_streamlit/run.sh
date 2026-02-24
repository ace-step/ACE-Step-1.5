#!/bin/bash
# Quick start script for ACE Studio Streamlit UI

set -e

echo "🎹 ACE Studio - Quick Start"
echo "=================================="

# Check Python
echo "Checking Python..."
python --version

# Check if venv exists
if [ ! -d "../.venv" ]; then
    echo "Creating virtual environment..."
    python -m venv ../.venv
fi

# Activate venv
echo "Activating virtual environment..."
source ../.venv/bin/activate

# Install dependencies
echo "Installing Streamlit dependencies..."
pip install -q -r requirements.txt

# Run the app
echo ""
echo "=================================="
echo "✅ Setup complete!"
echo "🚀 Starting ACE Studio..."
echo "📱 Open: http://localhost:8501"
echo "=================================="
echo ""

streamlit run main.py
