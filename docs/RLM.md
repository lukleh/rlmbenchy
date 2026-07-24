# RLM

This doc specifies the RLM loop as implemented here, and records where it diverges from the paper (`docs/reference/2512.24601v2.md`). `SPEC.md` gives the high-level intent and invariants; this file gives the algorithm.

## The loop

A task run is a bounded loop. Each iteration:

1. The LM receives the question, metadata about REPL variables, and the history of prior steps (reasoning + code + stdout). It emits reasoning and a Python code block.
2. The code block executes in a persistent Python REPL. The REPL retains state (variables, imports) across iterations within the task and is isolated across tasks.
3. Execution stdout is appended to history and fed back on the next iteration.
4. If the code calls `SUBMIT(answer=...)`, a `FinalOutput` is raised, caught by the loop, and the task ends with that answer.
5. If the iteration / token / time budget is hit first, an `extract` LM call produces a final answer from the accumulated history.

Tools injected into the REPL at start: `SUBMIT`, `llm_query` (sub-LLM call), and any user-provided tools.

## Prompt inputs and `variables_info`

The action LM does not receive the original task input fields directly. It receives:

- `variables_info` - metadata about task input variables already loaded in the REPL.
- `repl_history` - prior code executions and their observed stdout.
- `iteration` - current loop position.

`variables_info` follows DSPy's RLM pattern of sending prompt-side metadata instead of the original task fields. It is built only from the task inputs passed to `RLM.forward(...)`. Each entry contains the variable name, Python type, field description/constraints when available, and total serialized length. It does not include value previews. The actual values are injected into the REPL separately, so generated code can access the full variables from code.

Because input values can be large, the action prompt should not encourage blindly printing them. Generated code should first inspect size and shape: `type(...)`, `len(...)` when available, keys, counts, schemas, and small slices. Full values should only be printed after confirming they are small enough to fit safely in `repl_history`.

This is separate from `REPLHistory` output truncation, which caps each formatted step output at 10,000 characters when feeding stdout back into the next prompt.

Design note: this prompt shape is inherited from DSPy, but deliberately omits DSPy's input-value previews. If answer quality regresses, treat preview modes as an ablation candidate: compare metadata-only against bounded previews while measuring answer quality, step count, tool calls, sub-LLM calls, token usage, and failure modes.

## Large data and `repl_history`

Large values should stay in REPL variables whenever possible. A statement like `ctx = longbench_get_code_context(task_id)` stores the full value in the persistent REPL, but it does not by itself add that value to the next LM prompt. The next prompt still only sees the code that was run and whatever stdout/stderr the code produced.

The pollution path is printing or otherwise emitting a large value:

```python
ctx = longbench_get_code_context(task_id)
print(ctx)
```

The REPL worker captures stdout/stderr for each code execution. The RLM loop appends that captured output to `repl_history`, and `repl_history` is passed to the action LM on the next iteration. DSPy's `REPLHistory` formatting caps each step output at 10,000 characters by default, using a head/tail preview plus an omitted-character marker. That prevents a multi-megabyte print from entering the next prompt in full, but it can still add about 10k characters per bad step. Repeated large prints compound across iterations.

This means there are three different sizes to keep separate:

- Full task inputs: injected into the REPL and accessible to code.
- `variables_info`: prompt metadata with names, types, descriptions, and serialized lengths, but no input value previews.
- `repl_history`: prior code and observed output, with a 10,000-character cap per step output.

Generated code should inspect large data with compact observations: `len(...)`, keys, counts, schemas, selected rows, and short slices. Avoid printing whole tool results, long contexts, full documents, transcript bodies, or code repositories. If a full value is needed later, keep it assigned to a variable and operate on it in code rather than copying it through stdout.

## Divergences from the paper

Four deliberate differences, each with the reason we made that choice.

| # | Paper | Ours | Why |
|---|-------|------|-----|
| 1 | REPL feedback is `Metadata(stdout)` — short prefix + length; full values stay in REPL memory | Full stdout string is appended to history and fed back every iteration | Simpler, easier to debug, easier to measure what the LM actually sees. The paper's metadata-only stance is a research position about semantic horizon; we haven't needed it to validate the core loop. |
| 2 | Termination: code writes to `state[Final]`, loop polls for it | Termination: `SUBMIT(...)` raises `FinalOutput`, loop catches it | Matches idiomatic Python — raise a sentinel, don't poll side-effects. No observable behavior difference. |
| 3 | Algorithm 1 loads `sub_RLM_M` into the REPL (code can recursively spawn a full RLM) | Only `llm_query()` — a sub-LLM call, not a sub-RLM | The paper's own experiments cap recursion at depth 1 (sub-LLM only). We match the paper's experiments, just not its pseudocode. |
| 4 | No fallback — if the model never writes to `state[Final]`, the loop just ends | Extract fallback: if budget hits first, a separate LM call produces a final answer from history | Operational safety. Lets us grade partial answers. Not essential to the algorithm — a failure mode to measure, not suppress. |

## Ambiguities

- **Paper inconsistency on `sub_RLM` vs `sub_LLM`.** Algorithm 1 loads `sub_RLM_M`; sections 3.2 and 4 describe experiments at recursion depth 1. We follow the experiments.
- **`Metadata(stdout)` format unspecified.** The paper says "short prefix and length" but gives no concrete definition. We sidestep this by using full stdout.
- **Root vs. sub LM distinction.** The paper implies a root model M invoked with metadata and sub-calls spawned from code. Our code uses the same LM for both the main loop and `llm_query`. If root and sub ever need different configs, this becomes a design question, not a bug.

## Where this is in code

- Main loop: `rlmbenchy/rlm/rlm.py` — `RLM.forward()`.
- REPL runtime: `rlmbenchy/rlm/repl.py`.
- Tool injection (`SUBMIT`, `llm_query`): `rlmbenchy/rlm/rlm.py` — `_inject_tools()`.
- Signatures fed to the LM: `rlmbenchy/rlm/signatures.py`.
- Types: `rlmbenchy/rlm/types.py`.
