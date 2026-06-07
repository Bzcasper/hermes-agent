#!/usr/bin/env bash
set -euo pipefail

LOG="/root/.hermes/logs/memory-healthcheck.log"
mkdir -p /root/.hermes/logs

{
    echo "=== Memory Health Check $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    
    python3 /root/.hermes/scripts/memory_health_check_v1.py 2>&1
    
} >> "$LOG" 2>&1
