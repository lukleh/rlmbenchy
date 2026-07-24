#!/usr/bin/env bash
# Run repeatable query batches against a local OpenAI-compatible LLM server.

set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8001/v1}"
MODEL="${MODEL:-gpt-oss-20b}"
MAX_TOKENS="${MAX_TOKENS:-512}"
TEMPERATURE="${TEMPERATURE:-0.2}"
TIMEOUT_SEC="${TIMEOUT_SEC:-120}"
REPEATS=1
WAIT_SEC="0"
CONCURRENCY=1
OUT_DIR="${OUT_DIR:-/tmp/llm_query_runs}"
PROMPTS_FILE="scripts/local_llm_queries.txt"
SINGLE_PROMPT=""
SYSTEM_PROMPT=""
SAVE_RAW=false
FAIL_FAST=false

usage() {
    cat <<'EOF'
Usage: run_local_llm_queries.sh [options]

Options:
  -a API_BASE      API base URL (default: http://127.0.0.1:8001/v1)
  -m MODEL         Model name (default: gpt-oss-20b)
  -k MAX_TOKENS    max_tokens per request (default: 512)
  -t TEMPERATURE   temperature (default: 0.2)
  -T TIMEOUT_SEC   curl timeout in seconds (default: 120)
  -r REPEATS       Repeat each prompt this many times (default: 1)
  -w WAIT_SEC      Sleep between requests (default: 0)
  -P CONCURRENCY   Number of parallel requests (default: 1)
  -o OUT_DIR       Output directory for run logs (default: /tmp/llm_query_runs)
  -f PROMPTS_FILE  Prompts file (one query per line; default: scripts/local_llm_queries.txt)
  -p PROMPT        Single prompt to run (overrides file mode)
  -s SYSTEM_PROMPT Optional system prompt for all requests
  -R               Save raw response JSON files
  -F               Fail fast on first request error
  -h               Show help

Examples:
  ./scripts/run_local_llm_queries.sh
  ./scripts/run_local_llm_queries.sh -r 5 -f scripts/local_llm_queries.txt
  ./scripts/run_local_llm_queries.sh -r 10 -P 4 -f scripts/local_llm_queries.txt
  ./scripts/run_local_llm_queries.sh -p "Explain KV cache in 2 sentences." -r 20 -w 0.2
EOF
}

while getopts ":a:m:k:t:T:r:w:P:o:f:p:s:RFh" opt; do
    case "${opt}" in
        a) API_BASE="${OPTARG}" ;;
        m) MODEL="${OPTARG}" ;;
        k) MAX_TOKENS="${OPTARG}" ;;
        t) TEMPERATURE="${OPTARG}" ;;
        T) TIMEOUT_SEC="${OPTARG}" ;;
        r) REPEATS="${OPTARG}" ;;
        w) WAIT_SEC="${OPTARG}" ;;
        P) CONCURRENCY="${OPTARG}" ;;
        o) OUT_DIR="${OPTARG}" ;;
        f) PROMPTS_FILE="${OPTARG}" ;;
        p) SINGLE_PROMPT="${OPTARG}" ;;
        s) SYSTEM_PROMPT="${OPTARG}" ;;
        R) SAVE_RAW=true ;;
        F) FAIL_FAST=true ;;
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

if ! [[ "${REPEATS}" =~ ^[1-9][0-9]*$ ]]; then
    echo "REPEATS must be a positive integer." >&2
    exit 1
fi

if ! [[ "${TIMEOUT_SEC}" =~ ^[1-9][0-9]*$ ]]; then
    echo "TIMEOUT_SEC must be a positive integer." >&2
    exit 1
fi

if ! [[ "${CONCURRENCY}" =~ ^[1-9][0-9]*$ ]]; then
    echo "CONCURRENCY must be a positive integer." >&2
    exit 1
fi

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "${s}"
}

declare -a PROMPTS=()
if [[ -n "${SINGLE_PROMPT}" ]]; then
    PROMPTS+=("${SINGLE_PROMPT}")
else
    if [[ ! -f "${PROMPTS_FILE}" ]]; then
        echo "Prompts file not found: ${PROMPTS_FILE}" >&2
        exit 1
    fi

    while IFS= read -r line || [[ -n "${line}" ]]; do
        line="$(trim "${line}")"
        [[ -z "${line}" ]] && continue
        [[ "${line:0:1}" == "#" ]] && continue
        PROMPTS+=("${line}")
    done <"${PROMPTS_FILE}"
fi

if [[ "${#PROMPTS[@]}" -eq 0 ]]; then
    echo "No prompts to run." >&2
    exit 1
fi

mkdir -p "${OUT_DIR}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
JSONL_FILE="${OUT_DIR%/}/query_run_${RUN_ID}.jsonl"
RAW_DIR="${OUT_DIR%/}/raw_${RUN_ID}"
TMP_DIR="$(mktemp -d)"
if [[ "${SAVE_RAW}" == "true" ]]; then
    mkdir -p "${RAW_DIR}"
fi

TOTAL_REQUESTS=$((REPEATS * ${#PROMPTS[@]}))
OK_COUNT=0
FAIL_COUNT=0
REQ_ID=0

echo "Run ID: ${RUN_ID}"
echo "Endpoint: ${API_BASE%/}/chat/completions"
echo "Model: ${MODEL}"
echo "Prompts: ${#PROMPTS[@]} | Repeats: ${REPEATS} | Total requests: ${TOTAL_REQUESTS} | Parallel: ${CONCURRENCY}"
echo "JSONL log: ${JSONL_FILE}"
if [[ "${SAVE_RAW}" == "true" ]]; then
    echo "Raw responses: ${RAW_DIR}"
fi
echo

run_one_request() {
    local req_id="$1"
    local rep="$2"
    local prompt_index="$3"
    local prompt_text="$4"

    local started_epoch ts_utc payload resp_file curl_rc http_code ended_epoch latency_s
    local ok finish_reason prompt_tokens completion_tokens total_tokens tok_s_json tok_s_text content_preview error_msg
    local raw_file_json raw_file record record_file

    started_epoch="$(date +%s.%3N)"
    ts_utc="$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')"

    payload="$(
        jq -cn \
            --arg model "${MODEL}" \
            --arg prompt "${prompt_text}" \
            --arg sys "${SYSTEM_PROMPT}" \
            --argjson max_tokens "${MAX_TOKENS}" \
            --argjson temperature "${TEMPERATURE}" \
            '{
                model: $model,
                max_tokens: $max_tokens,
                temperature: $temperature,
                messages: (
                    if $sys == "" then
                        [{role: "user", content: $prompt}]
                    else
                        [{role: "system", content: $sys}, {role: "user", content: $prompt}]
                    end
                )
            }'
    )"

    resp_file="$(mktemp)"
    curl_rc=0
    http_code="$(
        curl -sS \
            --max-time "${TIMEOUT_SEC}" \
            -o "${resp_file}" \
            -w '%{http_code}' \
            -H 'Content-Type: application/json' \
            "${API_BASE%/}/chat/completions" \
            -d "${payload}"
    )" || curl_rc=$?
    http_code="${http_code:-000}"
    ended_epoch="$(date +%s.%3N)"
    latency_s="$(awk -v a="${started_epoch}" -v b="${ended_epoch}" 'BEGIN { printf "%.3f", (b - a) }')"

    ok=false
    finish_reason=""
    prompt_tokens="null"
    completion_tokens="null"
    total_tokens="null"
    tok_s_json="null"
    tok_s_text="n/a"
    content_preview=""
    error_msg=""

    if [[ "${curl_rc}" -eq 0 && "${http_code}" == "200" ]]; then
        if jq -e '.' "${resp_file}" >/dev/null 2>&1; then
            ok=true
            finish_reason="$(jq -r '.choices[0].finish_reason // ""' "${resp_file}")"
            prompt_tokens="$(jq -r '.usage.prompt_tokens // "null"' "${resp_file}")"
            completion_tokens="$(jq -r '.usage.completion_tokens // "null"' "${resp_file}")"
            total_tokens="$(jq -r '.usage.total_tokens // "null"' "${resp_file}")"
            content_preview="$(jq -r '.choices[0].message.content // ""' "${resp_file}" | tr '\n' ' ' | cut -c1-120)"

            if [[ "${completion_tokens}" =~ ^[0-9]+$ ]]; then
                tok_s_json="$(awk -v c="${completion_tokens}" -v t="${latency_s}" 'BEGIN { if (t > 0) printf "%.2f", (c / t); else print "null" }')"
                tok_s_text="${tok_s_json}"
            fi
        else
            error_msg="response_not_json"
        fi
    else
        error_msg="curl_rc=${curl_rc} http_code=${http_code}"
        if [[ -s "${resp_file}" ]]; then
            resp_error="$(jq -r '.error.message // .error // .message // empty' "${resp_file}" 2>/dev/null || true)"
            if [[ -n "${resp_error}" ]]; then
                error_msg="${error_msg} ${resp_error}"
            fi
        fi
    fi

    raw_file_json="null"
    if [[ "${SAVE_RAW}" == "true" ]]; then
        raw_file="${RAW_DIR}/req_$(printf '%05d' "${req_id}").json"
        mv "${resp_file}" "${raw_file}"
        raw_file_json="$(jq -Rn --arg v "${raw_file}" '$v')"
    else
        rm -f "${resp_file}"
    fi

    if [[ "${ok}" == "true" ]]; then
        printf '[%s] req=%d/%d rep=%d prompt=%d status=ok code=%s latency=%ss tok_s=%s finish=%s\n' \
            "${ts_utc}" "${req_id}" "${TOTAL_REQUESTS}" "${rep}" "${prompt_index}" "${http_code}" "${latency_s}" "${tok_s_text}" "${finish_reason:-n/a}"
    else
        printf '[%s] req=%d/%d rep=%d prompt=%d status=error code=%s latency=%ss error=%s\n' \
            "${ts_utc}" "${req_id}" "${TOTAL_REQUESTS}" "${rep}" "${prompt_index}" "${http_code}" "${latency_s}" "${error_msg}"
    fi

    record="$(
        jq -cn \
            --arg ts_utc "${ts_utc}" \
            --arg run_id "${RUN_ID}" \
            --arg endpoint "${API_BASE%/}/chat/completions" \
            --arg model "${MODEL}" \
            --arg prompt "${prompt_text}" \
            --arg finish_reason "${finish_reason}" \
            --arg content_preview "${content_preview}" \
            --arg error "${error_msg}" \
            --argjson request_id "${req_id}" \
            --argjson total_requests "${TOTAL_REQUESTS}" \
            --argjson repeat_index "${rep}" \
            --argjson prompt_index "${prompt_index}" \
            --argjson http_code "${http_code}" \
            --argjson ok "$( [[ "${ok}" == "true" ]] && echo true || echo false )" \
            --argjson latency_s "${latency_s}" \
            --argjson prompt_tokens "${prompt_tokens}" \
            --argjson completion_tokens "${completion_tokens}" \
            --argjson total_tokens "${total_tokens}" \
            --argjson tok_s "${tok_s_json}" \
            --argjson raw_response_file "${raw_file_json}" \
            '{
                ts_utc: $ts_utc,
                run_id: $run_id,
                request_id: $request_id,
                total_requests: $total_requests,
                repeat_index: $repeat_index,
                prompt_index: $prompt_index,
                endpoint: $endpoint,
                model: $model,
                prompt: $prompt,
                ok: $ok,
                http_code: $http_code,
                latency_s: $latency_s,
                tok_s: $tok_s,
                finish_reason: (if $finish_reason == "" then null else $finish_reason end),
                usage: {
                    prompt_tokens: $prompt_tokens,
                    completion_tokens: $completion_tokens,
                    total_tokens: $total_tokens
                },
                content_preview: $content_preview,
                error: (if $error == "" then null else $error end),
                raw_response_file: $raw_response_file
            }'
    )"

    record_file="${TMP_DIR}/record_$(printf '%05d' "${req_id}").json"
    printf '%s\n' "${record}" >"${record_file}"

    if [[ "${ok}" == "true" ]]; then
        return 0
    fi
    return 1
}

if [[ "${FAIL_FAST}" == "true" && "${CONCURRENCY}" -gt 1 ]]; then
    echo "Warning: fail-fast (-F) is only supported with -P 1. Ignoring -F." >&2
    FAIL_FAST=false
fi

active_jobs=0
for ((rep = 1; rep <= REPEATS; rep++)); do
    for i in "${!PROMPTS[@]}"; do
        REQ_ID=$((REQ_ID + 1))
        PROMPT_INDEX=$((i + 1))
        PROMPT_TEXT="${PROMPTS[$i]}"

        if [[ "${CONCURRENCY}" -gt 1 ]]; then
            run_one_request "${REQ_ID}" "${rep}" "${PROMPT_INDEX}" "${PROMPT_TEXT}" &
            active_jobs=$((active_jobs + 1))
            if (( active_jobs >= CONCURRENCY )); then
                wait -n || true
                active_jobs=$((active_jobs - 1))
            fi
        else
            if run_one_request "${REQ_ID}" "${rep}" "${PROMPT_INDEX}" "${PROMPT_TEXT}"; then
                :
            else
                if [[ "${FAIL_FAST}" == "true" ]]; then
                    echo
                    echo "Fail-fast enabled. Stopping after request ${REQ_ID}."
                    break 2
                fi
            fi
        fi

        if awk -v w="${WAIT_SEC}" 'BEGIN { exit !(w > 0) }'; then
            sleep "${WAIT_SEC}"
        fi
    done
done

if [[ "${CONCURRENCY}" -gt 1 ]]; then
    while (( active_jobs > 0 )); do
        wait -n || true
        active_jobs=$((active_jobs - 1))
    done
fi

for ((id = 1; id <= REQ_ID; id++)); do
    rec="${TMP_DIR}/record_$(printf '%05d' "${id}").json"
    if [[ -f "${rec}" ]]; then
        cat "${rec}" >>"${JSONL_FILE}"
    fi
done

if [[ -f "${JSONL_FILE}" ]]; then
    OK_COUNT="$(jq -s '[.[] | select(.ok == true)] | length' "${JSONL_FILE}")"
    FAIL_COUNT="$(jq -s '[.[] | select(.ok != true)] | length' "${JSONL_FILE}")"
fi

rm -rf "${TMP_DIR}"

echo
echo "Done."
echo "ok=${OK_COUNT} fail=${FAIL_COUNT} total=${REQ_ID}"
echo "jsonl=${JSONL_FILE}"
