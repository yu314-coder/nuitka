#!/bin/bash
# This script installs system packages from a packages.txt file

if [ ! -f "$1" ]; then
    echo "Packages file not found: $1"
    exit 1
fi

echo "Installing system packages from $1..."
# Read the file line by line
while read package; do
    # Skip empty lines and comments
    if [[ -z "$package" || "$package" == \#* ]]; then
        continue
    fi
    
    echo "Installing: $package"
    sudo apt-get update -y
    sudo apt-get install -y $package
done < "$1"

echo "All system packages installed successfully."