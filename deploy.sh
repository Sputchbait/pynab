#!/bin/bash
# Weather Service Deployment Script for Aaron's Bunny
# Date: 2026-06-09

set -e

BUNNY_HOST="pi@192.168.1.234"
BUNNY_PASS="0269NABmagi01"
REMOTE_PATH="/opt/pynab"
LOCAL_PATH="/Users/CLEMA023/Desktop/CLAUDE/Nabaztag/pynab-source"

echo "=========================================="
echo "Weather Service Deployment"
echo "Target: Aaron's Bunny (192.168.1.234)"
echo "=========================================="
echo ""

# Step 1: Create backup
echo "[1/6] Creating backup..."
sshpass -p "$BUNNY_PASS" ssh -o StrictHostKeyChecking=no $BUNNY_HOST \
  "cd $REMOTE_PATH && sudo cp -r nabweatherd nabweatherd.backup-\$(date +%Y%m%d-%H%M%S)"
echo "✓ Backup created"
echo ""

# Step 2: Update dependencies
echo "[2/6] Updating dependencies..."
sshpass -p "$BUNNY_PASS" ssh -o StrictHostKeyChecking=no $BUNNY_HOST \
  "cd $REMOTE_PATH && sudo -u pi venv/bin/pip uninstall -y meteofrance-api || true"
echo "✓ Removed meteofrance-api"
echo "  (Using built-in requests library - Python 3.7 compatible)"
echo ""

# Step 3: Deploy new files
echo "[3/6] Deploying new files..."
sshpass -p "$BUNNY_PASS" scp -o StrictHostKeyChecking=no \
  "$LOCAL_PATH/nabweatherd/openmeteo_client.py" \
  "$BUNNY_HOST:$REMOTE_PATH/nabweatherd/"
sshpass -p "$BUNNY_PASS" scp -o StrictHostKeyChecking=no \
  "$LOCAL_PATH/nabweatherd/wmo_codes.py" \
  "$BUNNY_HOST:$REMOTE_PATH/nabweatherd/"
echo "✓ New files deployed"
echo ""

# Step 4: Deploy updated files
echo "[4/6] Deploying updated files..."
sshpass -p "$BUNNY_PASS" scp -o StrictHostKeyChecking=no \
  "$LOCAL_PATH/nabweatherd/nabweatherd.py" \
  "$LOCAL_PATH/nabweatherd/views.py" \
  "$LOCAL_PATH/nabweatherd/models.py" \
  "$BUNNY_HOST:$REMOTE_PATH/nabweatherd/"
sshpass -p "$BUNNY_PASS" scp -o StrictHostKeyChecking=no \
  "$LOCAL_PATH/requirements.txt" \
  "$BUNNY_HOST:$REMOTE_PATH/"
echo "✓ Updated files deployed"
echo ""

# Step 5: Restart service
echo "[5/6] Restarting nabweatherd service..."
sshpass -p "$BUNNY_PASS" ssh -o StrictHostKeyChecking=no $BUNNY_HOST \
  "sudo systemctl restart nabweatherd"
sleep 2
echo "✓ Service restarted"
echo ""

# Step 6: Check service status
echo "[6/6] Checking service status..."
sshpass -p "$BUNNY_PASS" ssh -o StrictHostKeyChecking=no $BUNNY_HOST \
  "sudo systemctl status nabweatherd --no-pager | head -15"
echo ""

echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Open web UI: http://192.168.1.234/nabweatherd/settings"
echo "2. Search for: Issaquah Washington"
echo "3. Select location and save"
echo ""
echo "Monitor logs with:"
echo "  ssh pi@192.168.1.234"
echo "  sudo journalctl -u nabweatherd -f"
