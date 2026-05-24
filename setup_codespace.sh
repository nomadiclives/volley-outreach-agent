#!/usr/bin/env bash
# Volley Codespace setup — run once on first launch
set -e

echo "=== Volley Codespace Setup ==="

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

# Activate and install
source venv/bin/activate
echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Install Playwright browsers
echo "Installing Playwright Chromium..."
playwright install chromium --with-deps 2>/dev/null || playwright install chromium

# Create logs directory
mkdir -p logs

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit config.yaml with your API keys"
echo "  2. source venv/bin/activate"
echo "  3. python scripts/setup.py"
echo "  4. python main.py"
