# Results

Raw rows, one JSON object per line. One folder per machine, one file per run of a matrix.
`published.json` lists which files make up each published study; `bench/publish.py` reads it.

## Files

| File | Rows | What it is |
|---|---:|---|
| `m3-ultra-a/speed-2026-11-15.jsonl` | 48 | Speed matrix, 16 cells × 3 runs |
| `m3-ultra-a/speed-helper-warm-2026-11-15.jsonl` | 6 | The two noisy helper cells (8K, 32K) run again back to back, straight after the matrix |
| `m3-ultra-a/kv-cache-2026-11-15.jsonl` | 18 | KV cache matrix, 6 cells × 3 runs |
| `m3-ultra-a/quality-gpu-2026-11-16.jsonl` | 706 | Answer quality, GPU only |
| `m3-ultra-a/quality-ane-kv-helper-2026-11-16.jsonl` | 2,824 | Answer quality, the other four settings |
| `m3-ultra-a/quality-reask-8x-2026-11-16.jsonl` | 304 | The cut-off answers asked again with an 8× token cap |
| `m3-ultra-b/speed-2026-11-16.jsonl` | 24 | Speed matrix, 8 cells × 3 runs (no ANE setup on this model) |
| `m3-ultra-b/kv-cache-2026-11-16.jsonl` | 18 | KV cache matrix, 6 cells × 3 runs |
| `m3-ultra-b/quality-2026-11-16.jsonl` | 2,824 | Answer quality, all four settings |
| `m3-ultra-b/quality-passkey-cold-2026-11-17.jsonl` | 24 | The passkey prompts asked again with a unique first line, so each one was read cold |

The first machine's quality run is in two files because the first attempt stopped after the GPU block: the server
answered HTTP 409 after a settings change. The harness now waits for the model and retries, and the
other four settings were run in a second pass.

The second machine's passkey rerun is a `replace` file in `published.json`: its 24 rows take the place
of the passkey rows with the same setting, task and sample id in `quality-2026-11-16.jsonl`. The first
pass reused cached filler between prompts; the rerun read 0 cached tokens in every row.

## What was changed for publication

For `m3-ultra-a`, two values in every row, and nothing else:

- `machine`: the private host name was replaced by the label `m3-ultra-a`.
- `prefill_helper_node_id` (inside `settings_before` and `desired_settings`): the helper's node id
  was replaced by `redacted-helper-node`.

For `m3-ultra-b`, the same two, plus the `matrix` path, which points at
`matrices/m3-ultra-b-*.json` instead of the private working copy's matrix names. That copy holds no
private value, so the matrices themselves are published unchanged apart from their `note` line. The
rows were edited as text, so the harness's own line formatting is kept.

Earlier commits of this repository hold the rows under their old file names. The two warm re-run
rows were moved out of the speed file into their own file; no row was edited or dropped.

## Speed rows (`bench/run.py`)

| Field | Meaning |
|---|---|
| `timestamp` | UTC time the run started |
| `machine` | The `--machine` label |
| `matrix` | Matrix file the run came from |
| `model` | Model name on the server |
| `variant` | Setup name from the matrix: `gpu`, `ane`, `spark`, `ane_spark`, `native`, `affine4`, `affine8` |
| `prompt_size` | Target prompt size in tokens |
| `repeat_index` | 0, 1 or 2: which pass over the matrix |
| `runs_per_cell` | Planned runs for this cell |
| `helper_on`, `ane_on` | What the cell asked for |
| `desired_settings` | Model settings sent for this run |
| `settings_before` | Model settings found before the matrix started; restored at the end |
| `bench_id` | Server id of the benchmark run |
| `status` | `completed` for a good run |
| `end_event_type` | Last event of the run; `upload_skipped` means it stayed private |
| `feature_keys` | Features the server reported as active, for example `prefill_accelerator` |
| `metrics.processing_tps` | Prefill speed, prompt tokens per second |
| `metrics.ttft_ms` | Time to first token, milliseconds |
| `metrics.gen_tps`, `metrics.tpot_ms` | Decode speed and time per output token |
| `metrics.e2e_latency_s` | Whole request, seconds |
| `metrics.peak_memory_bytes` | Peak MLX active memory during the run |
| `metrics.pp` | Prompt tokens actually processed |
| `log` | The same run as parsed from the server log: cached tokens, ANE tiles and operations, KV conversion lines |
| `validity` | One boolean per rule in `docs/method.md`, and `valid`, which is true only when all hold |
| `spark_stats` | Always empty. An unused field in these early rows; the harness no longer writes it |

## Quality rows (`bench/quality.py`)

| Field | Meaning |
|---|---|
| `timestamp`, `machine`, `matrix`, `model`, `variant` | As above |
| `helper_on`, `ane_on`, `desired_settings`, `settings_before` | As above |
| `task` | `gsm8k`, `mmlu` or `passkey` |
| `sample_id` | Question id, stable across settings |
| `expected` | The right answer |
| `got` | The answer the scorer extracted from the reply |
| `correct` | True when `got` matches `expected` |
| `content` | The reply text |
| `reasoning_chars` | Length of the model's reasoning, which is not stored |
| `finish_reason` | `stop`, or `length` when the token cap cut the reply off |
| `max_tokens` | Token cap for this request (present in the re-ask file) |
| `usage` | Prompt, completion and cached token counts from the server |
| `server_timing` | Time to first token, total time and prefill speed from the server |
| `latency_s` | Wall time of the request as the client saw it |
| `status` | `completed`, or `error` with the reason |
| `note` | Present only when something needs saying: `no_answer_text` marks a reply with no answer text |
| `target_tokens`, `approximate_prompt_tokens`, `prompt_chars` | Passkey rows: the size asked for and the size built |
