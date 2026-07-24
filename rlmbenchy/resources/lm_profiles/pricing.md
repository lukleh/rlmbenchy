# LM Profile Pricing

Per-profile pricing, sorted by OpenRouter output token price ascending.
ChatGPT profiles use the user's ChatGPT subscription and have no per-token cost.

| Profile | Model | Input ($/M tok) | Output ($/M tok) |
|---------|-------|-----------------|------------------|
| `model-openrouter-openai-gpt-oss-20b.toml` | `openai/gpt-oss-20b` | 0.03 | 0.14 |
| `model-openrouter-openai-gpt-oss-20b_high.toml` | `openai/gpt-oss-20b` | 0.03 | 0.14 |
| `model-openrouter-openai-gpt-oss-120b_high.toml` | `openai/gpt-oss-120b` | 0.039 | 0.19 |
| `model-openrouter-qwen-qwen3-14b.toml` | `qwen/qwen3-14b` | 0.06 | 0.24 |
| `model-openrouter-google-gemma-4-26b-a4b_thinking.toml` | `google/gemma-4-26b-a4b-it` | 0.08 | 0.35 |
| `model-openrouter-google-gemma-4-31b_thinking.toml` | `google/gemma-4-31b-it` | 0.13 | 0.38 |
| `model-openrouter-qwen-qwen3.5-35b-a3b_thinking.toml` | `qwen/qwen3.5-35b-a3b` | 0.1625 | 1.30 |
| `model-openrouter-qwen-qwen3.5-27b_thinking.toml` | `qwen/qwen3.5-27b` | 0.195 | 1.56 |
| `model-chatgpt-gpt-5.5_low.toml` | `chatgpt/gpt-5.5` | subscription | subscription |
| `model-chatgpt-gpt-5.5_medium.toml` | `chatgpt/gpt-5.5` | subscription | subscription |
| `model-chatgpt-gpt-5.5_high.toml` | `chatgpt/gpt-5.5` | subscription | subscription |
| `model-chatgpt-gpt-5.5_xhigh.toml` | `chatgpt/gpt-5.5` | subscription | subscription |
| `model-chatgpt-gpt-5.6-sol_low.toml` | `chatgpt/gpt-5.6-sol` | subscription | subscription |
| `model-chatgpt-gpt-5.6-sol_medium.toml` | `chatgpt/gpt-5.6-sol` | subscription | subscription |
| `model-chatgpt-gpt-5.6-sol_high.toml` | `chatgpt/gpt-5.6-sol` | subscription | subscription |
| `model-chatgpt-gpt-5.6-sol_xhigh.toml` | `chatgpt/gpt-5.6-sol` | subscription | subscription |
| `model-chatgpt-gpt-5.6-sol_max.toml` | `chatgpt/gpt-5.6-sol` | subscription | subscription |
| `model-chatgpt-gpt-5.6-terra_low.toml` | `chatgpt/gpt-5.6-terra` | subscription | subscription |
| `model-chatgpt-gpt-5.6-terra_medium.toml` | `chatgpt/gpt-5.6-terra` | subscription | subscription |
| `model-chatgpt-gpt-5.6-terra_high.toml` | `chatgpt/gpt-5.6-terra` | subscription | subscription |
| `model-chatgpt-gpt-5.6-terra_xhigh.toml` | `chatgpt/gpt-5.6-terra` | subscription | subscription |
| `model-chatgpt-gpt-5.6-terra_max.toml` | `chatgpt/gpt-5.6-terra` | subscription | subscription |
| `model-chatgpt-gpt-5.6-luna_low.toml` | `chatgpt/gpt-5.6-luna` | subscription | subscription |
| `model-chatgpt-gpt-5.6-luna_medium.toml` | `chatgpt/gpt-5.6-luna` | subscription | subscription |
| `model-chatgpt-gpt-5.6-luna_high.toml` | `chatgpt/gpt-5.6-luna` | subscription | subscription |
| `model-chatgpt-gpt-5.6-luna_xhigh.toml` | `chatgpt/gpt-5.6-luna` | subscription | subscription |
| `model-chatgpt-gpt-5.6-luna_max.toml` | `chatgpt/gpt-5.6-luna` | subscription | subscription |
| `model-local-gpt-oss-20b.toml` | `gpt-oss-20b` (local llama.cpp) | local | local |

Source: [openrouter.ai](https://openrouter.ai) model pages, fetched 2026-04-18.
Prices show OpenRouter's listed standard rate; the `provider = { sort = "price" }`
setting in profiles routes to the cheapest active provider at request time,
which may occasionally differ.
