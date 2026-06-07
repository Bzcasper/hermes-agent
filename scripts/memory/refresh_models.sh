#!/bin/bash
# refresh_models.sh — daily model audit + rotation
# Checks all Zen free models, updates config with best available, restarts gateway.
# Sends Telegram summary directly (no gateway delivery race condition).
set -euo pipefail

LOG="/root/.hermes/logs/model_rotation.log"
HERMES_ENV="/root/.hermes/.env"
CONFIG="/root/.hermes/config.yaml"
TS=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

if [ ! -f "$HERMES_ENV" ] || [ ! -f "$CONFIG" ]; then
    echo "ERROR: .env or config.yaml missing" >&2
    exit 1
fi

set -a; . "$HERMES_ENV"; set +a

# Validate required Telegram vars
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_HOME_CHANNEL:-}" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_HOME_CHANNEL not set" >&2
    exit 1
fi

BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
CHAT_ID="${TELEGRAM_HOME_CHANNEL}"

send_telegram() {
    local text="$1"
    curl -sS -m 10 -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" -d "parse_mode=Markdown" -d "text=${text}" >/dev/null 2>&1
}

ZEN_KEY=$(grep "^OPENCODE_ZEN_API_KEY" "$HERMES_ENV" | head -1 | cut -d= -f2- | tr -d '"')
ZEN_URL="https://opencode.ai/zen/v1/chat/completions"

echo "[$TS] refresh_models.sh starting" >> "$LOG"

# 1. Probe all Zen free models
declare -A MODEL_STATUS
FREE_MODELS=("nemotron-3-ultra-free" "deepseek-v4-flash-free" "minimax-m3-free" "nemotron-3-super-free" "mimo-v2.5-free" "qwen3.6-plus-free")

for model in "${FREE_MODELS[@]}"; do
    RESP=$(curl -sS -m 15 -X POST "$ZEN_URL" \
        -H "Authorization: Bearer $ZEN_KEY" \
        -H "Content-Type: application/json" \
        -H "User-Agent: opencode-cli/1.0.0" \
        -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":4}" 2>&1)
    
    if echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('choices') else 1)" 2>/dev/null; then
        MODEL_STATUS[$model]="OK"
        echo "[$TS] $model: OK" >> "$LOG"
    else
        ERR=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',{}).get('message','unknown')[:80])" 2>/dev/null || echo "timeout")
        MODEL_STATUS[$model]="FAIL: $ERR"
        echo "[$TS] $model: FAIL ($ERR)" >> "$LOG"
    fi
done

# 2. Build working model list (OK only)
WORKING=()
for model in "${FREE_MODELS[@]}"; do
    if [ "${MODEL_STATUS[$model]}" = "OK" ]; then
        WORKING+=("$model")
    fi
done

echo "[$TS] Working models: ${#WORKING[@]}/${#FREE_MODELS[@]}" >> "$LOG"

# 3. Update config with best available models
if [ ${#WORKING[@]} -gt 0 ]; then
    python3 -c "
import yaml, sys

working = sys.argv[1].split(',')
with open('$CONFIG', 'r') as f:
    cfg = yaml.safe_load(f) or {}

# Set main model to first working
cfg['model']['provider'] = 'opencode-zen'
cfg['model']['default'] = working[0]

# Build fallback chain from all working models
cfg['fallback_providers'] = [{'provider': 'opencode-zen', 'model': m} for m in working]
# Add Ollama as last resort
cfg['fallback_providers'].append({'provider': 'ollama', 'model': 'gemma3:1b'})

# Update auxiliary text tasks
for task in cfg.get('auxiliary', {}):
    if cfg['auxiliary'][task].get('provider') != 'nvidia':
        cfg['auxiliary'][task]['provider'] = 'opencode-zen'
        cfg['auxiliary'][task]['model'] = working[0] if len(working) > 0 else 'nemotron-3-super-free'
        cfg['auxiliary'][task]['base_url'] = ''
        cfg['auxiliary'][task]['api_key'] = ''

with open('$CONFIG', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print(f'Config updated: main={working[0]}, fallback={len(working)} free models')
" "$(IFS=,; echo "${WORKING[*]}")"
    
    # 4. Restart gateway
    echo "[$TS] Restarting gateway..." >> "$LOG"
    systemctl restart hermes-gateway 2>/dev/null || true
    # Wait for gateway to become active (max 30s)
    for i in {1..30}; do
        if systemctl is-active hermes-gateway >/dev/null 2>&1; then
            echo "[$TS] Gateway restarted OK (${i}s)" >> "$LOG"
            GATEWAY_STATUS="✅ running"
            break
        fi
        sleep 1
    done
    if [ "$GATEWAY_STATUS" != "✅ running" ]; then
        echo "[$TS] Gateway restart FAILED after 30s" >> "$LOG"
        GATEWAY_STATUS="❌ failed"
    fi
else
    echo "[$TS] ERROR: No working models!" >> "$LOG"
    GATEWAY_STATUS="❌ no models"
fi

# 5. Summary
SUMMARY="🔁 *Daily Model Audit* ${TS}

Models: ${#WORKING[@]}/${#FREE_MODELS[@]} working
Main: \`${WORKING[0]:-none}\`
Fallback: $((${#WORKING[@]}-1)) free + Ollama
Gateway: $GATEWAY_STATUS

\`\`\`
$(for m in "${FREE_MODELS[@]}"; do echo "  $m: ${MODEL_STATUS[$m]}"; done)
\`\`\`"

echo "[$TS] refresh complete" >> "$LOG"
send_telegram "$SUMMARY"
exit 0
