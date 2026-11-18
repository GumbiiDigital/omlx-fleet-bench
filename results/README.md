# Results

Raw rows, one JSON object per line. One folder per machine, one file per run of a matrix. The date in
a file name is the local date the run started; the timestamps inside the rows are UTC.
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
| `m3-ultra-a/quality-passkey-cold-2026-11-17.jsonl` | 30 | The passkey prompts asked again with a unique first line, so each one was read cold |
| `m3-ultra-a/helper-ready-chat-nowait-2026-11-17.jsonl` | 12 | Chat path, no helper wait: 6 rounds of one helper-off request and then one 32K passkey request with the helper on |
| `m3-ultra-a/helper-ready-chat-wait-2026-11-17.jsonl` | 12 | The same 6 rounds with the helper wait |
| `m3-ultra-a/helper-ready-speed-nowait-2026-11-17.jsonl` | 12 | The same 6 rounds on the server's benchmark call, no helper wait |
| `m3-ultra-a/helper-ready-speed-wait-2026-11-17.jsonl` | 12 | The same 6 rounds on the server's benchmark call, with the helper wait |
| `m3-ultra-a/helper-layers-2026-11-17.jsonl` | 27 | Chat path, helper wait: Mac alone, automatic layers, and 32, 49 and 63 layers, at 32K and 128K, 3 requests per cell |
| `m3-ultra-b/speed-2026-11-16.jsonl` | 24 | Speed matrix, 8 cells × 3 runs (no ANE setup on this model) |
| `m3-ultra-b/speed-sweep-2026-11-15.jsonl` | 28 | Prompt-size sweep 1K to 128K, 14 cells × 2 runs; one 128K helper run did not use the helper |
| `m3-ultra-b/speed-sweep-rerun-2026-11-15.jsonl` | 4 | Reruns of the 128K helper cell: 2 server-conflict rows, 1 failed run, and the valid row that cell was missing |
| `m3-ultra-b/speed-256k-refused-2026-11-15.jsonl` | 2 | The 256K attempt: both rows are server refusals, kept as proof that size has no result |
| `m3-ultra-b/kv-cache-2026-11-16.jsonl` | 18 | KV cache matrix, 6 cells × 3 runs |
| `m3-ultra-b/quality-2026-11-16.jsonl` | 2,824 | Answer quality, all four settings |
| `m3-ultra-b/quality-passkey-cold-2026-11-17.jsonl` | 24 | The passkey prompts asked again with a unique first line, so each one was read cold |

The first machine's quality run is in two files because the first attempt stopped after the GPU block: the server
answered HTTP 409 after a settings change. The harness now waits for the model and retries, and the
other four settings were run in a second pass.

Both passkey reruns are `replace` files in `published.json`: each file's rows take the place of the
passkey rows with the same setting, task and sample id in that machine's main quality file. The first
pass on each machine reused cached filler between prompts; the reruns read 0 cached tokens in every
row.

## What was changed for publication

For `m3-ultra-a`, two values in every row, and nothing else:

- `machine`: the private host name was replaced by the label `m3-ultra-a`.
- `prefill_helper_node_id` (inside `settings_before` and `desired_settings`): the helper's node id
  was replaced by `redacted-helper-node`.

For `m3-ultra-b`, the same two, plus the `matrix` path, which points at
`matrices/m3-ultra-b-*.json` instead of the private working copy's matrix names. That copy holds no
private value, so the matrices themselves are published unchanged apart from their `note` line. The
rows were edited as text, so the harness's own line formatting is kept.

The prompt-size sweep files (`speed-sweep-*`, `speed-256k-refused-*`) were prepared the same way:
machine label, helper node id and matrix path only. They were measured on 2026-11-15 with a second
DGX Spark unit of the same type as the helper, one day before the speed matrix above, so the two
sets are not one series. The error rows in those files are as the harness wrote them: they carry
`error` and no metrics or log, so their fields differ from a completed row. No key was added or
removed, and no measured value was changed.

The five helper files (`helper-ready-*`, `helper-layers-*`) got the machine label and the helper
node id, and nothing else. Their chat rows carry the helper fields below and no `validity` block;
the speed-test rows carry one. Rows that a check marks not valid stay in the file:

- `helper-ready-speed-nowait`: 6 rows, all marked not valid by `helper_ready_at_start`. Every
  helper-on request in that arm began while the helper was `starting`. These 6 rows are the fault
  the study replays, and no mean in the README uses them.
- `helper-ready-speed-wait`: 0 rows marked not valid.
- The two chat files and the layer file: no `validity` block. All 24 helper-on requests across the
  chat arms and all 27 layer requests read 0 cached tokens, and every answer was correct.
- In the chat files the helper-off requests after the first round reused 140 cached tokens of the
  round before (5 rows in the no-wait file, 6 in the wait file). They are there to force the
  settings switch; they are not part of any helper-on figure.

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
| `status` | `completed` for a good run; absent on an error row, which carries `error` instead |
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

## Helper fields (rows from 2026-11-17)

Both kinds of row carry these once the harness waits for the helper. Read them together: the state
at the start says what the request could use, and the last three say whether the helper served it.

| Field | Meaning |
|---|---|
| `helper_state` | The helper's state when the request went out: `connecting`, `starting`, `ready`, or empty with the helper off |
| `helper_wait_s` | Seconds the harness waited for `ready` before the request; 0 when it did not wait |
| `helper_layers` | Layers the helper really took for this request, read after it. Empty when the helper served none |
| `helper_held`, `helper_session_since` | Layers the helper held, and the server's clock reading when that session started |
| `helper_last_prompt_at`, `helper_last_prompt_tokens`, `helper_last_prompt_seconds` | The helper's last prompt: when it started, its tokens and its seconds. Empty when the helper had served no prompt |
