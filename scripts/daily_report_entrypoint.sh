#!/bin/bash
# Entrypoint for the daily-report container.
# Sets up cron jobs for pre-market and post-market analysis, then runs crond.
#
# US market hours (Eastern): 9:30 AM - 4:00 PM ET
# Pre-market -15min:  9:15 AM ET = 21:15 Beijing (UTC+8) = 13:15 UTC
# Post-market +15min: 4:15 PM ET = 04:15 Beijing (UTC+8) = 20:15 UTC
#
# Also supports manual trigger via: docker compose exec daily-report python daily_report.py

set -e

# Write environment variables to a file so cron can access them
printenv | grep -E "^(GITHUB_COPILOT_TOKEN|OPENAI_API_KEY|ALPHA_VANTAGE_API_KEY|FEISHU_WEBHOOK_URL|TRADINGAGENTS_|PATH=)" > /tmp/env.sh 2>/dev/null || true
sed -i 's/^/export /' /tmp/env.sh

# Create cron schedule
# Pre-market: 9:15 AM ET = 13:15 UTC (Mon-Fri)
# Post-market: 4:15 PM ET = 20:15 UTC (Mon-Fri)
cat > /tmp/crontab << 'EOF'
15 13 * * 1-5 . /tmp/env.sh && cd /home/appuser/app && /opt/venv/bin/python3 daily_report.py >> /tmp/daily_report.log 2>&1
15 20 * * 1-5 . /tmp/env.sh && cd /home/appuser/app && /opt/venv/bin/python3 daily_report.py >> /tmp/daily_report.log 2>&1
EOF

echo "=== TradingAgents Daily Report Scheduler ==="
echo "Schedule (UTC):"
echo "  Pre-market:  13:15 UTC / 21:15 Beijing / 9:15 AM ET (Mon-Fri)"
echo "  Post-market: 20:15 UTC / 04:15 Beijing / 4:15 PM ET (Mon-Fri)"
echo ""
echo "Manual trigger: docker compose exec daily-report python3 daily_report.py"
echo "View logs:      docker compose exec daily-report cat /tmp/daily_report.log"
echo "============================================="

# Install crontab and start cron in foreground
crontab /tmp/crontab
exec cron -f
