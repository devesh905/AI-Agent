#!/bin/bash
# Lucy AI Assistant Startup Script
# Fixes all permissions and starts the service

echo "🚀 Starting Lucy AI Assistant..."

# 1. Fix directory permissions
echo "📁 Fixing directory permissions..."
sudo chown -R asterisk:asterisk /home/devesh/ai-asterisk/
sudo chmod -R 755 /home/devesh/ai-asterisk/
sudo chmod 777 /home/devesh/ai-asterisk/data/

# 2. Fix script permissions
echo "🔧 Fixing script permissions..."
sudo chmod +x /home/devesh/ai-asterisk/agi/agi_script.py
sudo chmod +x /home/devesh/ai-asterisk/ai_logic/groq_ai_enhanced.py

# 3. Fix audio directories
echo "🔊 Fixing audio directories..."
sudo chown -R asterisk:asterisk /var/lib/asterisk/sounds/
sudo chmod -R 755 /var/lib/asterisk/sounds/
sudo mkdir -p /var/lib/asterisk/sounds/recordings
sudo chown asterisk:asterisk /var/lib/asterisk/sounds/recordings

# 4. Create/fix log file
echo "📝 Setting up log file..."
sudo touch /tmp/agi_debug.log
sudo chmod 666 /tmp/agi_debug.log

# 5. Restart Asterisk
echo "♻️  Restarting Asterisk..."
sudo systemctl restart asterisk
sleep 2

# 6. Check status
echo "✅ Checking Asterisk status..."
sudo systemctl status asterisk --no-pager | head -5

echo ""
echo "🎉 Lucy is ready! Call 900 to test."
echo "📊 Monitor logs: tail -f /tmp/agi_debug.log"
echo "📞 Asterisk console: sudo asterisk -rvvv"
