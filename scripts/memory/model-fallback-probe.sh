#!/bin/bash
# model-fallback-probe.sh — every 10m, ping primary + each fallback tier.
# Reports a per-tier status summary to Telegram only when something changed.
# Uses no LLM; cheap curl probes.
set -euo pipefail

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-8664991354:AAEZvKquweRphAst2Sf1YwVzuISFsr7W1aw}"
CHAT_ID="${TELEGRAM_HOME_CHANNEL:-7577661620}"
STATE_FILE="/root/.hermes/scripts/.model-probe-state"

# Validate required vars
if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
    echo "ERROR: BOT_TOKEN or CHAT_ID not set" >&2
    exit 1
fi

LAST=""
[ -f "$STATE_FILE" ] && LAST=$(cat "$STATE_FILE" 2>/dev/null || true)

CURRENT=""

# Probe function with error handling
probe() {
    local name="$1" url="$2" model="$3" key="$4"
    local body code
    body=$(printf '{"model":"%s","messages":[{"role":"user","content":"ping"}],"max_tokens":4,"stream":false}' "$model")
    code=$(curl -sS -m 10 -o /dev/null -w "%{http_code}" -X POST "$url" \
        -H "Authorization: Bearer $key" \
        -H "Content-Type: application/json" \
        -d "$body" 2>/dev/null) || code="000"
    if [ "$code" = "200" ]; then
        CURRENT="${CURRENT}✅ ${name}\n"
    else
        CURRENT="${CURRENT}❌ ${name} (HTTP ${code})\n"
    fi
}

# Load keys from .env
load_key() {
    local var_name="$1"
    local val
    val=$(grep -E "^${var_name}=" /root/.hermes/.env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)
    echo "$val"
}

ZEN_KEY=$(load_key "OPENCODE_ZEN_API_KEY")
NIM_KEY=$(load_key "NVIDIA_API_KEY")

# Validate keys exist
if [ -z "$ZEN_KEY" ]; then
    echo "WARNING: OPENCODE_ZEN_API_KEY not found in .env" >&2
fi
if [ -z "$NIM_KEY" ]; then
    echo "WARNING: NVIDIA_API_KEY not found in .env" >&2
fi

# Probe tiers
[ -n "$ZEN_KEY" ] && probe "opencode-zen/deepseek-v4-flash-free" "https://opencode.ai/zen/v1/chat/completions" "deepseek-v4-flash-free" "$ZEN_KEY"
[ -n "$NIM_KEY" ] && probe "nvidia/deepseek-ai/deepseek-v4-flash" "https://integrate.api.nvidia.com/v1/chat/completions" "deepseek-ai/deepseek-v4-flash" "$NIM_KEY"
[ -n "$NIM_KEY" ] && probe "nvidia/qwen/qwen3-next-80b-a3b-instruct" "https://integrate.api.nvidia.com/v1/chat/completions" "qwen/qwen3-next-80b-a3b-instruct" "$NIM_KEY"
probe "ollama/gemma3:1b" "http://127.0.0.1:11434/v1/chat/completions" "gemma3:1b" "ollama"

mkdir -p "$(dirname "$STATE_FILE")"
printf "%s" "$CURRENT" > "$STATE_FILE"

# Only alert on state change
if [ "$CURRENT" != "$LAST" ]; then
    MSG="🔁 *Model chain state change*
${CURRENT}"
    curl -sS -m 5 -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" -d "parse_mode=Markdown" -d "text=${MSG}" >/dev/null 2>&1
fi
exit 0
