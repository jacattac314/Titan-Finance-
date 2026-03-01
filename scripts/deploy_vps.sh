#!/bin/bash
set -e

echo "Starting Titan-Finance setup..."

# 1. Update system
echo "Updating apt packages..."
sudo apt-get update
sudo apt-get upgrade -y

# 2. Install Docker if not present
if ! command -v docker &> /dev/null
then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
else
    echo "Docker is already installed."
fi

# 3. Add current user to docker group (optional but recommended)
sudo usermod -aG docker $USER

# 4. Git setup
if ! command -v git &> /dev/null
then
    echo "Installing Git..."
    sudo apt-get install -y git
fi

echo "========================================================"
echo "Installation complete!"
echo ""
echo "Please LOG OUT and LOG BACK IN to apply Docker permissions."
echo "Then, run the following commands:"
echo ""
echo "  git clone https://github.com/jacattac314/Titan-Finance-.git"
echo "  cd Titan-Finance-"
echo "  cp .env.example .env"
echo "  nano .env  # Add your Alpaca keys here"
echo "  docker compose up --build -d"
echo "========================================================"
