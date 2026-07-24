# LM Profiles

Shared LM connection/request profiles live here.

These TOMLs are bundled package resources so every installed `rlmbenchy`
command has the same reusable defaults.

## Local overrides

Drop a file with the same name in
`~/.config/lukleh/rlmbenchy/lm_profiles/` (the user `lm_profiles_dir`) to
replace the bundled profile entirely. There is no partial merge — the user file
wins in full, so it must be complete. This keeps override behavior obvious:
what you see in the user file is exactly what the runner loads. Use overrides
for secret-bearing adjustments (e.g. swapping `api_key`) by copying the bundled
profile first, then editing.

An LM profile is exactly one LM endpoint/settings bundle. It should not contain
workload wiring or references to another LM profile.

Naming convention:

- Profiles vary along one axis — reasoning/thinking level. Filenames encode
  what makes each profile distinct.
- Multiple profiles per endpoint: `model-<provider>-<model>_<level>.toml`
  (e.g. `_low`, `_medium`, `_high`, `_xhigh`).
- Single profile per endpoint: unadorned `model-<provider>-<model>.toml`.
- No `_default` or `_checks` suffix — the content embodies what the profile
  is; the filename announces its axis value.

Profile schema:

- `[lm].api_base` and `[lm].model` select the provider endpoint and model ID.
- `[lm].transport` is optional. Use `chatgpt_responses` when a profile should
  force the `ChatGPTResponsesLM` wrapper instead of relying on API-base
  autodetection. Omit it or set `auto` to keep the existing heuristics.
- `[lm].api_key` or `[lm].api_key_env` are optional for providers that need an
  explicit API key.
- `[lm.request]` contains provider request kwargs passed through to DSPy/LiteLLM.

Sub-model routing belongs in run configs (`sub_lm_profile = "..."` or an
inline `[sub_lm]` block), not inside the LM profile itself.

Live profile tests:

- Every bundled `*.toml` profile is covered by
  `tests/test_lm_profile_all_live.py`.
- Every bundled profile also has a profile-specific
  `tests/test_lm_profile_*.py` module that pins its endpoint, model ID,
  request defaults, and auth/transport expectations. The all-profile test
  includes an offline guard so new profiles must add a specific test file too.
- Normal test runs exclude these endpoint calls. To run the real smoke for
  every profile, use
  `uv run pytest -m live_llm tests/test_lm_profile_all_live.py -q -s -rs`.
- To run both the generic all-profile smoke and the profile-specific live
  checks, use
  `uv run pytest -m live_llm tests/test_lm_profile_*.py -q -s -rs`.
- To smoke just one profile, target its parametrized case, for example
  `uv run pytest -m live_llm 'tests/test_lm_profile_all_live.py::test_live_bundled_lm_profile_answers[model-chatgpt-gpt-5.6-terra_medium]' -q -s -rs`.
- Live tests print progress before each endpoint call. The generic all-profile
  smoke also prints the profile filename, endpoint, model, request kwargs,
  prompt, and a truncated response preview.
- The generic smoke disables client retries, uses a small output budget, and
  wraps each provider call in a hard timeout so a slow endpoint fails instead
  of leaving the run looking stuck.
- Set `OPENROUTER_API_KEY` for OpenRouter profiles and `NVIDIA_API_KEY` for
  NVIDIA NIM profiles. ChatGPT profiles read file-backed Codex auth from
  `~/.codex/auth.json` (or `$CODEX_HOME/auth.json`); local profiles require
  their configured loopback server to be running.
- Missing auth or an unavailable loopback endpoint skips only the affected
  profile. Provider/API failures after auth is available fail the test.

ChatGPT/Codex via your ChatGPT subscription:

- Recommended GPT-5.6 profiles:
- `model-chatgpt-gpt-5.6-sol_<effort>.toml` for complex, open-ended work.
- `model-chatgpt-gpt-5.6-terra_<effort>.toml` for balanced everyday work.
- `model-chatgpt-gpt-5.6-luna_<effort>.toml` for fast, repeatable work.
- Each model has `low`, `medium`, `high`, `xhigh`, and `max` effort variants.
  Start with `medium` and increase it only when the task needs more depth.
- `ultra` is intentionally not a profile effort: in Codex it is an
  orchestration mode that delegates work to subagents, which a single
  subscription-backed Responses request cannot reproduce.
- Previous-generation `gpt-5.5` profiles remain available:
- `model-chatgpt-gpt-5.5_low.toml`
- `model-chatgpt-gpt-5.5_medium.toml`
- `model-chatgpt-gpt-5.5_high.toml`
- `model-chatgpt-gpt-5.5_xhigh.toml`
- These target `https://chatgpt.com/backend-api/codex` and the runtime now
  translates requests onto the subscription-backed `responses` transport.
- The bundled ChatGPT profiles set `transport = "chatgpt_responses"` explicitly
  so the runtime does not have to infer that wrapper choice.
- The bundled profiles intentionally set only `reasoning.effort` under
  `[lm.request]`.
- That transport ignores normal sampling/token-limit knobs such as
  `temperature`, `top_p`, and `max_tokens`; `rlmbenchy` strips them if they are
  added manually instead of forwarding unsupported parameters.
- This is an experimental compatibility transport, not a stable OpenAI
  Platform API. It calls the Codex Responses backend directly and may need
  updates when that backend changes.
- Requests identify their originator as `rlmbenchy`.
- Normal benchmark runs read a current ChatGPT access token from file-backed
  Codex auth at `~/.codex/auth.json` (or `$CODEX_HOME/auth.json`).
- rlmbenchy treats that credential file as read-only: it never refreshes tokens
  or rewrites the file. If the token is missing or expired, run
  `codex login -c cli_auth_credentials_store=file` and retry.
- Codex credentials stored only in an operating-system keyring are not
  available to this transport.
- File-backed Codex authentication stores sensitive tokens in plaintext;
  protect `auth.json` like a password.
- A value supplied through `api_key` or `api_key_env` for this transport must
  be a ChatGPT/Codex OAuth access token, not an OpenAI Platform API key.
- The official Codex websocket base `https://chatgpt.com/backend-api` still
  is intentionally rejected by `rlmbenchy`; use
  `https://chatgpt.com/backend-api/codex` instead.

OpenRouter `gpt-oss-20b` with reasoning (`_high`):

- Profile: `model-openrouter-openai-gpt-oss-20b_high.toml`.
- `reasoning_effort = "high"` — OpenRouter / LiteLLM reasoning budget hint.
  OpenAI-style levels allocate a fraction of the output-token budget to
  reasoning: `xhigh` (95%), `high` (80%), `medium` (50%), `low` (20%),
  `minimal` (10%), `none` (disabled). Empirically on the test prompt
  (4x10 domino tiling): `low` → ~300-char reasoning channel, `medium`
  → ~11k, `high` → 10k–55k (wide variance because `temperature = 1.0`).
- `include_reasoning = true` — legacy OpenRouter alias for `reasoning: {}`
  (enable reasoning with defaults). Empirically this flag is **not
  redundant** with `reasoning_effort`: setting just `reasoning_effort = "high"`
  alone sometimes yields 0 chars of reasoning and sometimes 50k+, whereas
  adding `include_reasoning = true` reliably populates the channel.
  `include_reasoning = false` (equivalent to `reasoning: { exclude: true }`)
  reliably suppresses the channel to 0 chars.
- `provider = { sort = "price" }` — OpenRouter routes the request to the
  cheapest available upstream for this model.
- `supported_params.ignore = ["provider"]` — OpenRouter's model-parameter
  metadata does not list the top-level routing `provider` field, which would
  otherwise trigger an unsupported-parameter warning at request-validation
  time. The ignore list silences the warning for that single key; other
  unsupported parameters are still flagged.
- Why `reasoning_format` is *not* on this profile: it is a llama.cpp
  server-only per-request parameter (see the cross-engine section below).
  OpenRouter does not document it, vLLM and SGLang backends do not read it,
  and empirically it had no detectable effect when we A/B-tested it against
  OpenRouter. Keeping it on the profile would only grow the
  `supported_params.ignore` list without delivering measurable behavior.
- Tests: `tests/test_lm_profile_gpt_oss_20b_high.py` (profile
  drift guard + single live call), `tests/test_openrouter_reasoning_flags.py`
  (live, parameterized characterization of each flag on OpenRouter).
- Sources for the claims above: OpenRouter reasoning-tokens guide
  (https://openrouter.ai/docs/guides/best-practices/reasoning-tokens),
  llama.cpp CLI help and server-task code cited above; vLLM
  `vllm/reasoning/__init__.py` and SGLang `python/sglang/srt/server_args.py`
  confirm those engines use `--reasoning-parser` (not per-request).

OpenRouter Gemma 4 and Qwen 3 / 3.5 `_thinking` profiles:

- Profiles:
  - `model-openrouter-google-gemma-4-31b_thinking.toml` (dense 31B)
  - `model-openrouter-google-gemma-4-26b-a4b_thinking.toml` (26B total / 4B active MoE)
  - `model-openrouter-qwen-qwen3-14b.toml`
  - `model-openrouter-qwen-qwen3.5-27b_thinking.toml`
  - `model-openrouter-qwen-qwen3.5-35b-a3b_thinking.toml`
- `reasoning = { enabled = true }` — OpenRouter's canonical structured form
  for turning on reasoning. None of these models advertise `reasoning_effort`
  in their `supported_parameters` metadata, so there is no effort-level
  knob to set; the flag is binary on/off. Empirically every profile
  surfaced a non-empty reasoning channel on the 4x10 domino-tiling test
  (Gemma 4 31B ~18k chars, Gemma 4 26B-a4b ~24k, Qwen 3-14B ~58k,
  Qwen 3.5-27B ~35k, Qwen 3.5-35B-a3b truncated at ~269k).
- Output surfacing: Gemma 4 emits reasoning inside
  `<|channel>thought\n…<channel|>` tags; Qwen 3 / 3.5 emit
  `<think>…</think>` tags. OpenRouter parses both and populates
  `message.reasoning`, which DSPy's `dspy.Reasoning` adapter consumes.
- Sampling: Gemma follows Google's Gemma 4 Best Practices
  (`temperature = 1.0`, `top_p = 0.95`, `top_k = 65`). Qwen follows
  Qwen's thinking-mode recipe (`temperature = 0.6`, `top_p = 0.95`,
  `top_k = 20`).
- `provider = { sort = "price" }` + `supported_params.ignore = ["provider"]`
  on every profile: OpenRouter's model metadata does not list the top-level
  routing `provider` field, so the ignore list silences the
  unsupported-parameter warning for that one key.
- Caveat for `qwen3.5-35b-a3b`: at the default thinking budget this model
  can emit hundreds of thousands of characters of reasoning before
  answering. On the domino-tiling prompt the upstream provider truncated
  the response; DSPy surfaced a `max_tokens=None` truncation warning. For
  production workloads with this profile, consider pinning `max_tokens`
  to a reasonable budget or using a shorter prompt.
- `chat_template_kwargs.enable_thinking` is not used here: Qwen 3.5
  defaults to thinking-enabled on OpenRouter, and OpenRouter's
  `supported_parameters` metadata does not advertise `chat_template_kwargs`
  for these models, so the canonical `reasoning` block is the reliable
  switch.
- Tests: `tests/test_lm_profile_gemma_qwen_reasoning.py` (parameterized
  live call across all five profiles, gated on `live_llm`).

NVIDIA NIM Nemotron 3 Super:

- Profile: `model-nvidia-nemotron-3-super-120b-a12b.toml`
- Targets `https://integrate.api.nvidia.com/v1` with model
  `nvidia/nemotron-3-super-120b-a12b`.
- Auth uses `api_key_env = "NVIDIA_API_KEY"`. If your shell sources
  `~/.secrets`, export it there.
- Sampling follows NVIDIA's model page recommendation: `temperature = 1.0`
  and `top_p = 0.95`.
- `chat_template_kwargs = { enable_thinking = true, force_nonempty_content = true }`
  keeps the model's reasoning mode enabled while still forcing a normal content
  channel for agent/coding workloads.
- Tests: `tests/test_lm_profile_nvidia_nemotron_3_super_120b_a12b.py`
  (static drift checks + optional live smoke).

NVIDIA NIM Google Gemma 3 27B IT:

- Profile: `model-nvidia-google-gemma-3-27b-it.toml`
- Targets `https://integrate.api.nvidia.com/v1` with model
  `google/gemma-3-27b-it`.
- Auth uses `api_key_env = "NVIDIA_API_KEY"`.
- Sampling follows Gemma 3's common instruction-tuned recipe:
  `temperature = 1.0`, `top_p = 0.95`, and `top_k = 64`.
- This profile replaced the earlier NVIDIA DeepSeek V4 Flash profile because
  the DeepSeek family was catalog-listed but did not return chat-completion
  responses in direct endpoint probes, while Gemma 3 27B returned quickly on
  the same endpoint and API key.
- Tests: `tests/test_lm_profile_nvidia_google_gemma_3_27b_it.py`
  (static drift checks + optional live smoke).

Reasoning parsing across inference engines:

DSPy's `dspy.Reasoning` adapter consumes a separate reasoning field on the
response — `message.reasoning_content` on raw OpenAI-compatible responses,
or `message.reasoning` on OpenRouter's normalized schema. If the server
does not parse `<think>…</think>` tags out of the content, the reasoning
stays inline and DSPy may assign it to a non-reasoning output field. Each
engine exposes a different mechanism for that parsing:

- **llama.cpp** — request-level field `reasoning_format` (also settable at
  server startup via `--reasoning-format`). Values: `none`, `auto`,
  `deepseek`, `deepseek-legacy`. See `common/arg.cpp:3009` and
  `tools/server/server-task.cpp:341`. `deepseek` writes thoughts to
  `message.reasoning_content`; `deepseek-legacy` additionally keeps the
  `<think>` tags in `message.content`.
- **vLLM** — server-startup flag `--reasoning-parser` only. Choices are
  model-family parser names (`deepseek_r1`, `deepseek_v3`, `openai_gptoss`,
  `qwen3`, `ernie45`, `glm45`, `hunyuan`, …); the registry lives in
  `vllm/reasoning/__init__.py`. The request body does **not** accept
  `reasoning_format` or any equivalent per-call override.
- **SGLang** — server-startup flag `--reasoning-parser` only. Choices are
  detector names (`DeepSeekR1`, `Kimi`, `Qwen3`, …); see
  `python/sglang/srt/server_args.py:3594`. Same story as vLLM: no
  per-request override.
- **TensorRT-LLM** — no dedicated reasoning-parser flag found in the tree;
  any client consuming it needs to parse thinking tags itself.

OpenRouter is a routing layer, not an engine. It normalizes upstream
reasoning into `choices[i].message.reasoning` when a provider returns one,
regardless of request-body flags. We intentionally do **not** set
`reasoning_format` on OpenRouter profiles: vLLM and SGLang upstreams do not
read it, and when routed to a llama.cpp-backed upstream, OpenRouter
normalizes the resulting `message.reasoning_content` into its own
`message.reasoning` surface anyway — so the flag has no observable effect
through OpenRouter and would only expand the `supported_params.ignore` list
for no gain.

LiteLLM `supports_reasoning()` — the version pin does not pin the answer:

`dspy.Reasoning.adapt_to_native_lm_feature` gates native-reasoning
signature rewriting on `lm.supports_reasoning`. For DSPy's stock `dspy.LM`,
that property delegates to LiteLLM's `supports_reasoning(model)`. That value
reads from `litellm.model_cost`, which is built **at import time** from a
JSON file LiteLLM fetches live from GitHub `main`:

    https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json

If the fetch fails or `LITELLM_LOCAL_MODEL_COST_MAP=True` is set, LiteLLM
falls back to the `model_prices_and_context_window_backup.json` bundled in
the installed wheel (see
`litellm/litellm_core_utils/get_model_cost_map.py`).

Consequences worth knowing before you debug "why did reasoning suddenly
start/stop working":

- Pinning `litellm==X` in `uv.lock` does **not** pin `supports_reasoning()`
  behavior on its own. Two machines on identical locks can disagree if
  GitHub `main` drifted between their process starts.
- We previously kept a local model allowlist in `rlmbenchy/rlm/reasoning.py`
  because certain models returned `False`. The allowlist was removed in
  commit `d48ebe9` ("Drop reasoning allowlist: migrate profiles to
  reasoning_effort") — but the trigger was not a LiteLLM release, it was
  the GitHub-`main` JSON silently gaining `"supports_reasoning": true`
  entries. Do not re-investigate this: the library version never moved.

How this repo handles it (current state):

1. `litellm` is pinned in `pyproject.toml` (currently `==1.86.1`), where
   the bundled backup JSON already lists the four models previously in the
   allowlist (`openrouter/openai/gpt-oss-20b`, `…/gpt-oss-120b`,
   `openrouter/qwen/qwen3.5-27b`, `…/qwen3.5-35b-a3b`) with
   `"supports_reasoning": true`.
2. `LITELLM_LOCAL_MODEL_COST_MAP=True` is set before LiteLLM is imported
   by two bootstrap hooks:
   - `rlmbenchy/_litellm_bootstrap.py`, imported at the top of
     `rlmbenchy/__init__.py` (covers CLI and library imports).
   - Repo-root `conftest.py` (covers `pytest` runs).
   Both use `os.environ.setdefault`, so an explicit override at the shell
   still wins.
3. `tests/test_litellm_model_cost_offline.py` asserts the env var is on
   and pins `supports_reasoning(model) is True` for the required local-map
   models. If a future `litellm` bump regresses either, this test fails
   before the change lands.
4. `rlmbenchy/_litellm_bootstrap.py` overlays `gpt-5.5` and the GPT-5.6
   Sol/Terra/Luna family into the pinned local model map because the pinned
   LiteLLM data predates those models. This keeps provider routing, native
   streaming detection, and reasoning detection deterministic without
   allowing LiteLLM to fetch GitHub `main` at import time.

Known gaps (models reasoning-enabled in the profile but **not** in the
bundled JSON of `litellm==1.86.1`, so `supports_reasoning(...)` returns
`False` under `LITELLM_LOCAL_MODEL_COST_MAP=True`):

- `openrouter/google/gemma-4-31b-it`
- `openrouter/google/gemma-4-26b-a4b-it`
- `openrouter/qwen/qwen3-14b`

Effect: DSPy keeps an explicit `reasoning` output field in the prompt for
these three profiles instead of deleting it. The model still emits
reasoning via OpenRouter's `reasoning = { enabled = true }` flag — the
behavior is just slightly less optimal than for the bundled models.

Fix options, in order of preference:

1. Wait for (or contribute) these entries upstream and bump `litellm`
   again. Extend `tests/test_litellm_model_cost_offline.py`'s parametrize
   list at the same time so the fix is pinned.
2. Call `litellm.register_model({...})` for the three models from the
   bootstrap. Lowest-friction local solution; write it so the test above
   picks them up too.

Do **not** reintroduce the `rlmbenchy/rlm/reasoning.py` model allowlist —
that is the historical wrong abstraction. The ChatGPT Responses transport
branch in that file is the only override that still has a reason to exist.
