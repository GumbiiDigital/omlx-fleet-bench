# Method

What this repository measures, how, and what it does not measure. It is written so that someone
else can repeat the runs and hold their rows against these.

## The question

"For my Mac and my prompt size, how long do I wait for the first token, and what does each add-on
buy me?"

Three add-ons are measured:

- **ANE prefill**: the Apple Neural Engine does part of the prompt read.
- **Prefill helper**: a second machine with an NVIDIA GPU (here a GB10, the DGX Spark) reads the
  first layers of the prompt and hands the result to the Mac.
- **KV cache schemes**: Affine4 and Affine8 store part of the key-value cache in fewer bits.

## Studies

| Study | Matrix | What changes | Cells | Requests |
|---|---|---|---:|---:|
| Speed | `matrices/m3-ultra-spark.json` | GPU only, + ANE, + helper, + ANE + helper, at 8K, 32K, 64K, 128K | 16 | 48 |
| KV cache | `matrices/kv-cache.json` | Native, Affine4, Affine8, at 32K and 128K, GPU only | 6 | 18 |
| Answer quality | `matrices/quality.json` | GPU only, + ANE, Affine4, Affine8, + helper on GSM8K 200, MMLU 500, passkey 6 | 15 groups | 3,530 |

Speed and KV cache use the oMLX benchmark endpoint: `code_python` context profile, 128 greedy output
tokens, cold cache, 3 runs per cell. Runs are ordered across variants (run 1 of every cell, then
run 2, then run 3), so heat and drift over time land on every variant alike.

Answer quality uses chat requests at temperature 0. One request is one row.

`matrices/smoke.json` is a two-run check that the harness can talk to your server.
`matrices/flash-next-moe.json` is a matrix for a mixture-of-experts model; no results from it are
published here.

## What makes a speed row count

A speed row is valid only when all of these hold:

- the status is `completed`;
- the last event is `upload_skipped`, so the run stayed private;
- the server log shows 0 cached tokens, so the cache was cold;
- the feature flags match the cell: `prefill_accelerator` is present for helper rows and absent for
  the others;
- the helper session was `ready` when the request started. A row that records no state, as older
  rows do, is not failed by this rule;
- for ANE rows, the server log shows that ANE operations ran. The planned tile count alone is not
  accepted, because the server can plan ANE tiles and then not use them.

`bench/validity.py` makes the call and records each check in the row. Rows that fail stay in the
file. Nothing is deleted.

## The helper wait

A settings change unloads the model and ends the helper session, and the new session takes a while
to be ready; a request that arrives in between is read on the Mac alone. After a settings change,
both runners ask `GET /admin/api/prefill-helper/models/<model>` and wait for `state: ready` before
sending the request (`--helper-ready-timeout`, seconds, default 120). `--no-helper-wait` sends the
request after one read instead, which is only for replaying an older run. Each row records
`helper_state`, the state at the start of its own request (`null` when the helper was off), and
`helper_wait_s`, the seconds spent waiting for it.

## Noise

A cell is marked noisy when the spread of prefill speed over its valid runs, (max − min) / mean, is
over 3%. Two causes have shown up so far: the first run after a model load, and helper runs that
follow several minutes of Mac-only work. Helper throughput was 5% (8K) to 17% (32K) higher when
helper runs came back to back.

To measure one cell again, use `--only-cells variant:size` and write to a new file. Do not loop
until the number looks good. Publish both passes, as this repository does.

## Heat

The helper GPU peaked at 57 °C during these runs. That figure was read outside the harness, which
does not record helper temperature or helper memory.

## Settings safety

The harness saves the model settings it is about to touch (up to 7 fields), sends only those fields,
and restores the saved values in a `finally` block. The proof after a study is a settings file that
is byte-identical to a copy taken before it.

## Answer-quality rules

- A row is scored, not filtered. Wrong answers stay in the file, because accuracy is the measurement.
- A reply with no answer text (only reasoning, usually because the token cap ran out) is scored
  wrong. Caps are 2,048 tokens for GSM8K, 1,024 for MMLU and 256 for a passkey.
- `--retry-capped` asks cut-off answers again with a larger cap, in the same setting. The report
  puts the new answer in the place of the old one and says how many are still cut off.
- GSM8K is scored on the final number only. MMLU is scored on the letter. Passkey is scored on the
  7-digit number appearing in the reply, ignoring commas.
- Passkey prompts are built from filler text sized at about 1.11 tokens per word, measured against
  the server's own token count. The real prompts came out at 99.6% to 99.7% of the target size.
- Every passkey prompt starts with a line that is unique to its setting and sample. Without it the
  server answers a repeated prompt from its prompt cache, and the setting under test never reads the
  prompt. The quality rows published here were recorded before that line was added; the README says
  what that means for them.
- Settings are applied once per setting and restored at the end.

## Reading the quality numbers

- The chart shows a 95% Wilson interval for each accuracy. It describes one setting on one question
  set. It is not a test of the difference between two settings.
- The table also gives paired counts: how many answers a setting got right that the baseline got
  wrong, and the reverse. The same questions are asked under every setting, so these counts show
  movement that an unchanged accuracy can hide.
- ANE prefill and the helper do no visible work on short prompts. Their rows on GSM8K and MMLU are
  therefore a measure of run-to-run variation, not of the add-on.

## Limits

- One Mac, one helper, one model, one pre-release oMLX build.
- Cold cache and one request at a time. No warm-cache or concurrent numbers.
- Three runs per cell.
- The size of the KV cache is not measured. Peak MLX active memory is reported instead.
- Helper memory and temperature are not recorded.
- Decode speed varies with the multi-token prediction path and is not studied.
- The quality subsets are small: about 3 points of sampling error for GSM8K 200 and about 4 for
  MMLU 500 at 90% confidence (see `data/README.md`). Compare settings inside one run, not against
  published full-test scores.
- `bench/report.py` merges every JSONL file under the folder it is given. To report one study, give
  it that study's file.
