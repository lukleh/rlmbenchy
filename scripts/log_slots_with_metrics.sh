#!/usr/bin/env bash
# Simple llama.cpp /slots tok/s monitor with generation-only sliding average.
#
# Logic:
# - Each scan combines token deltas from all active slots into one combined delta.
# - Scans with zero generated tokens are ignored for averaging.
# - Sliding-window average tok/s is computed from combined generated slots only.

set -euo pipefail

URL="http://127.0.0.1:8001/slots"
DISPLAY_INTERVAL="1"
SCAN_INTERVAL="0.2"
WINDOW_SAMPLES=30
LOG_DIR="${LOG_DIR:-${XDG_STATE_HOME:-${HOME}/.local/state}/lukleh/rlmbenchy/llm_metrics}"

usage() {
    cat <<'EOF'
Usage: log_slots_with_metrics.sh [-u URL] [-n DISPLAY_INTERVAL] [-s SCAN_INTERVAL] [-w WINDOW_SAMPLES] [-d LOG_DIR]

Options:
  -u URL              Slots endpoint (default: http://127.0.0.1:8001/slots)
  -n DISPLAY_INTERVAL Print/log interval in seconds (default: 1)
  -s SCAN_INTERVAL    Poll interval in seconds (default: 0.2)
  -w WINDOW_SAMPLES   Sliding window size in generated scan-slots (default: 30)
  -d LOG_DIR          Log directory (default: $LOG_DIR env var, else ~/.local/state/lukleh/rlmbenchy/llm_metrics)
  -h                  Show this help
EOF
}

while getopts ":u:n:s:w:d:h" opt; do
    case "${opt}" in
        u) URL="${OPTARG}" ;;
        n) DISPLAY_INTERVAL="${OPTARG}" ;;
        s) SCAN_INTERVAL="${OPTARG}" ;;
        w) WINDOW_SAMPLES="${OPTARG}" ;;
        d) LOG_DIR="${OPTARG}" ;;
        h)
            usage
            exit 0
            ;;
        :)
            echo "Option -${OPTARG} requires an argument." >&2
            usage
            exit 1
            ;;
        \?)
            echo "Invalid option: -${OPTARG}" >&2
            usage
            exit 1
            ;;
    esac
done

if ! [[ "${WINDOW_SAMPLES}" =~ ^[1-9][0-9]*$ ]]; then
    echo "WINDOW_SAMPLES must be a positive integer." >&2
    exit 1
fi

mkdir -p "${LOG_DIR}"
JSONL_FILE="${LOG_DIR%/}/slots_monitor_$(date +%Y%m%d_%H%M%S).jsonl"

declare -A LATEST_DECODED=()
declare -A LATEST_TASK_ID=()
declare -A PREV_DECODED=()

WINDOW_TOKENS=()
WINDOW_DTS=()

LAST_SCAN_EPOCH=""
LAST_DISPLAY_EPOCH="0"
LAST_COMBINED_DELTA=0
LAST_INST_TOK_S="null"

echo "Sliding-window tok/s monitor: stdout"
echo "Machine log (JSONL): ${JSONL_FILE}"
echo "Endpoint: ${URL}"
echo "Display interval: ${DISPLAY_INTERVAL}s, scan interval: ${SCAN_INTERVAL}s, window samples: ${WINDOW_SAMPLES}"
echo "Press Ctrl+C to stop."
echo

trap 'echo; echo "Stopped. JSONL file: ${JSONL_FILE}"; exit 0' INT TERM

while true; do
    NOW_EPOCH="$(date +%s.%3N)"

    RAW_JSON="$(curl -s --max-time 2 "${URL}" || true)"
    if [[ -z "${RAW_JSON}" ]]; then
        sleep "${SCAN_INTERVAL}"
        continue
    fi

    if ! ROWS="$(
        jq -r '
          if type == "array" then
            .[]
            | select(.is_processing == true)
            | [
                (.id | tostring),
                ((.next_token[0].n_decoded // .n_decoded // 0) | tonumber? // 0 | tostring),
                ((.id_task // "") | tostring)
              ]
            | @tsv
          else
            empty
          end
        ' <<<"${RAW_JSON}" 2>/dev/null
    )"; then
        sleep "${SCAN_INTERVAL}"
        continue
    fi

    declare -A ACTIVE_NOW=()
    COMBINED_DELTA=0

    if [[ -n "${ROWS}" ]]; then
        while IFS=$'\t' read -r SLOT_ID DECODED TASK_ID; do
            [[ -z "${SLOT_ID}" ]] && continue

            ACTIVE_NOW["${SLOT_ID}"]=1
            LATEST_DECODED["${SLOT_ID}"]="${DECODED}"
            LATEST_TASK_ID["${SLOT_ID}"]="${TASK_ID}"

            PREV_D="${PREV_DECODED["${SLOT_ID}"]:-}"
            SLOT_DELTA=0
            if [[ -n "${PREV_D}" ]]; then
                SLOT_DELTA=$((DECODED - PREV_D))
                if (( SLOT_DELTA < 0 )); then
                    # Counter reset (typically slot task rollover). Use current decoded.
                    SLOT_DELTA="${DECODED}"
                fi
            fi

            COMBINED_DELTA=$((COMBINED_DELTA + SLOT_DELTA))
            PREV_DECODED["${SLOT_ID}"]="${DECODED}"
        done <<<"${ROWS}"
    fi

    for SLOT_ID in "${!LATEST_DECODED[@]}"; do
        if [[ -z "${ACTIVE_NOW["${SLOT_ID}"]:-}" ]]; then
            unset "LATEST_DECODED[${SLOT_ID}]"
            unset "LATEST_TASK_ID[${SLOT_ID}]"
            unset "PREV_DECODED[${SLOT_ID}]"
        fi
    done

    SCAN_DT="0.000000"
    if [[ -n "${LAST_SCAN_EPOCH}" ]]; then
        SCAN_DT="$(awk -v now="${NOW_EPOCH}" -v prev="${LAST_SCAN_EPOCH}" 'BEGIN { d = now - prev; if (d < 0) d = 0; printf "%.6f", d }')"
    fi
    LAST_SCAN_EPOCH="${NOW_EPOCH}"
    LAST_COMBINED_DELTA="${COMBINED_DELTA}"
    LAST_INST_TOK_S="null"

    if (( COMBINED_DELTA > 0 )) && awk -v dt="${SCAN_DT}" 'BEGIN { exit !(dt > 0) }'; then
        LAST_INST_TOK_S="$(awk -v dd="${COMBINED_DELTA}" -v dt="${SCAN_DT}" 'BEGIN { printf "%.2f", (dd / dt) }')"
        WINDOW_TOKENS+=("${COMBINED_DELTA}")
        WINDOW_DTS+=("${SCAN_DT}")
        while ((${#WINDOW_TOKENS[@]} > WINDOW_SAMPLES)); do
            WINDOW_TOKENS=("${WINDOW_TOKENS[@]:1}")
            WINDOW_DTS=("${WINDOW_DTS[@]:1}")
        done
    fi

    ELAPSED_SINCE_DISPLAY="$(awk -v now="${NOW_EPOCH}" -v prev="${LAST_DISPLAY_EPOCH}" 'BEGIN { printf "%.3f", now - prev }')"
    SHOULD_DISPLAY=false
    if awk -v e="${ELAPSED_SINCE_DISPLAY}" -v i="${DISPLAY_INTERVAL}" 'BEGIN { exit !(e >= i) }'; then
        SHOULD_DISPLAY=true
    fi

    if [[ "${SHOULD_DISPLAY}" != "true" ]] || [[ "${#LATEST_DECODED[@]}" -eq 0 ]]; then
        sleep "${SCAN_INTERVAL}"
        continue
    fi

    NOW_HUMAN="$(date '+%Y-%m-%d %H:%M:%S.%3N')"
    NOW_ISO_UTC="$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')"

    ACTIVE_COUNT=0
    SLOT_LINES=()
    SLOT_JSON_OBJS=()
    for SLOT_ID in "${!LATEST_DECODED[@]}"; do
        ACTIVE_COUNT=$((ACTIVE_COUNT + 1))
        DECODED="${LATEST_DECODED["${SLOT_ID}"]}"
        TASK_ID="${LATEST_TASK_ID["${SLOT_ID}"]:-}"
        TASK_TEXT="${TASK_ID:-n/a}"
        SLOT_LINES+=("slot ${SLOT_ID}: task=${TASK_TEXT} decoded=${DECODED}")
        SLOT_JSON_OBJS+=(
            "$(jq -cn \
                --arg id "${SLOT_ID}" \
                --arg task_id "${TASK_ID}" \
                --argjson decoded "${DECODED}" \
                '{id: $id, task_id: (if $task_id == "" then null else $task_id end), decoded: $decoded}')"
        )
    done

    WINDOW_COUNT="${#WINDOW_TOKENS[@]}"
    AVG_TOK_S_JSON="null"
    AVG_TOK_S_TEXT="n/a"
    if (( WINDOW_COUNT > 0 )); then
        SUM_TOKENS=0
        SUM_DT="0.000000"
        for idx in "${!WINDOW_TOKENS[@]}"; do
            SUM_TOKENS=$((SUM_TOKENS + WINDOW_TOKENS[idx]))
            SUM_DT="$(awk -v s="${SUM_DT}" -v d="${WINDOW_DTS[idx]}" 'BEGIN { printf "%.6f", (s + d) }')"
        done
        if awk -v dt="${SUM_DT}" 'BEGIN { exit !(dt > 0) }'; then
            AVG_TOK_S_JSON="$(awk -v tok="${SUM_TOKENS}" -v dt="${SUM_DT}" 'BEGIN { printf "%.2f", (tok / dt) }')"
            AVG_TOK_S_TEXT="${AVG_TOK_S_JSON}"
        fi
    fi

    INST_TOK_S_TEXT="n/a"
    if [[ "${LAST_INST_TOK_S}" != "null" ]]; then
        INST_TOK_S_TEXT="${LAST_INST_TOK_S}"
    fi

    SLOTS_JSON="$(printf '%s\n' "${SLOT_JSON_OBJS[@]}" | jq -cs '.')"
    SNAPSHOT_JSON="$(jq -cn \
        --arg ts "${NOW_HUMAN}" \
        --arg ts_utc "${NOW_ISO_UTC}" \
        --argjson ts_epoch "${NOW_EPOCH}" \
        --arg endpoint "${URL}" \
        --argjson active "${ACTIVE_COUNT}" \
        --argjson generated_tokens_last_scan "${LAST_COMBINED_DELTA}" \
        --argjson inst_tok_s "${LAST_INST_TOK_S}" \
        --argjson total_tok_s "${AVG_TOK_S_JSON}" \
        --argjson window_samples "${WINDOW_COUNT}" \
        --argjson slots "${SLOTS_JSON}" \
        '{ts: $ts, ts_utc: $ts_utc, ts_epoch: $ts_epoch, endpoint: $endpoint, active: $active, generated_tokens_last_scan: $generated_tokens_last_scan, inst_tok_s: $inst_tok_s, total_tok_s: $total_tok_s, window_samples: $window_samples, slots: $slots}')"

    printf '[%s] active=%d generated_last_scan=%d inst_tok_s=%s total_tok_s=%s window_samples=%d\n' \
        "${NOW_HUMAN}" "${ACTIVE_COUNT}" "${LAST_COMBINED_DELTA}" "${INST_TOK_S_TEXT}" "${AVG_TOK_S_TEXT}" "${WINDOW_COUNT}"
    printf '%s\n' "${SLOT_LINES[@]}"
    printf '\n'

    printf '%s\n' "${SNAPSHOT_JSON}" >>"${JSONL_FILE}"
    LAST_DISPLAY_EPOCH="${NOW_EPOCH}"
    sleep "${SCAN_INTERVAL}"
done
