#!/bin/bash
# Setup script for Festival Vendor Directory
# Run once to install all dependencies

set -e

echo "=== Festival Vendor Directory Setup ==="

# Python dependencies
echo "[1/3] Installing Python packages..."
pip install pandas requests python-dotenv --break-system-packages 2>/dev/null || \
pip install pandas requests python-dotenv

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "[2/3] Creating .env file..."
    echo "DEEPSEEK_API_KEY=your_key_here" > .env
    echo "  → Edit .env and add your DeepSeek API key"
else
    echo "[2/3] .env already exists, skipping"
fi

# Create output directory
echo "[3/3] Creating output directory..."
mkdir -p output

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your DeepSeek API key"
echo "  2. Run: python -m curation.run_pipeline --input your_scraped.csv --output output/"
echo "  3. Run: python website/build_site_data.py output/curated_vendors.json website/vendors.json"
echo "  4. Open website/index.html in a browser to preview"
