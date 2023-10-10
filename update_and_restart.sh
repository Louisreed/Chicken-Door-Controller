#!/bin/bash

# Navigate to your repository's directory if not already there
# cd /path/to/your/repo  # Uncomment and set the path if needed

# Pull the latest code from the 'main' branch
git pull origin main

# Reload the systemd daemon to read any changes
sudo systemctl daemon-reload

# Restart the chickenDoorController service
sudo systemctl restart chickenDoorController.service

# Print a message indicating the operations were successful
echo "Updated code and restarted service."
