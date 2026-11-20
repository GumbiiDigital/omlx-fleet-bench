# How we measured

Question: how were these numbers made, and what can they not tell you?

Short answer: two Macs, each with a Spark beside it, one model on each, three runs per case with a
cold cache. Every row is kept, including the ones a check marks not valid. Nothing here is a
leaderboard, and nothing here is an official oMLX result.

## The question

For my Mac and my prompt size, how long do I wait for the first word, and what does each add-on buy me?

Three add-ons are measured:

- **The Apple chip.** The Apple Neural Engine reads part of the prompt.
- **The helper.** A second machine with an NVIDIA GPU (here a GB10, the DGX Spark) reads the first
  layers of the prompt and hands the result to the Mac.
- **KV cache schemes.** Affine4 and Affine8 store part of the key-value cache in fewer bits.

## The tests

| Test | Run file | What changes | Cases | Requests |
|---|---|---|---:|---:|
| Speed | `matrices/m3-ultra-spark.json` | Mac alone, + Apple chip, + Spark, + both, at 8K, 32K, 64K, 128K | 16 | 48 |
| KV cache | `matrices/kv-cache.json` | Native, Affine4, Affine8, at 32K and 128K, Mac alone | 6 | 18 |
| Answer quality | `matrices/quality.json` | Five settings, on GSM8K 200, MMLU 500, passkey 6 | 15 | 3,530 |

Speed and KV cache use the server's own benchmark call: `code_python` context profile, 128 output
tokens, a cold cache, 3 runs per case. The runs are ordered by pass, not by case: run 1 of every case,
then run 2, then run 3. Heat and drift over time therefore land on every setting alike.

Answer quality uses chat requests at temperature 0. One request is one row.

`matrices/smoke.json` is a two-run check that the runner can talk to your server.
`matrices/flash-next-moe.json` is a run file for a mixture-of-experts model; no results from it are
published here.

## What makes a speed row count

A speed row is valid only when all of these hold:

- the status is `completed`;
- the last event is `upload_skipped`, so the run stayed private;
- the server log shows 0 cached tokens, so the cache was cold;
- the feature flags match the case: `prefill_accelerator` is present for helper rows and absent for
  the others;
- the helper session was up and stable when the request started. A wait that gave up on a `ready` it
  did not see hold does not count. A row that records no state, as older rows do, is not failed by
  this rule;
- the helper served the request (`helper_served`): its last prompt is at or after the request start.
  A row where that field could not be read, as older rows, is not failed by this rule;
- for Apple chip rows, the server log shows that Apple chip operations ran. The planned tile count
  alone is not accepted, because the server can plan tiles and then not use them.

`bench/validity.py` makes the call and records each check in the row. Rows that fail stay in the file.
Nothing is deleted.

## The helper wait

A settings change unloads the model and loads it again, and the helper starts a new session that
attaches to the loaded model. Both chat runners therefore do the same three things before a request:
send the settings, ask the model for one token so the load happens, then wait for the helper.

The wait accepts `ready` only when it holds for `--helper-stable-s` seconds (default 5) with the same
session start (`since`), because the session from before the change can read `ready` for a moment.
`--helper-ready-timeout` (seconds, default 120) limits the whole wait. `--no-helper-wait` skips the
wait but keeps the probe and the state read, for replaying an older run.

Each row records the state at its request (`helper_state`, `helper_wait_s`) and, once the request
ends, `helper_layers`, `helper_held`, `helper_session_since`, `helper_last_prompt_at`,
`helper_last_prompt_tokens` and `helper_last_prompt_seconds`.

## Noise

A case is marked noisy when the spread of reading speed over its valid runs, (max − min) / mean, is
over 3%. Two causes have shown up so far: the first run after a model load, and helper runs that
follow several minutes of Mac-only work. Helper throughput was 5% (8K) to 17% (32K) higher when
helper runs came back to back.

To measure one case again, use `--only-cells setting:size` and write to a new file. Do not loop until
the number looks good. Publish both passes, as this repository does.

## Heat

The helper GPU peaked at 57 °C during these runs. That figure was read outside the runner, which does
not record helper temperature or helper memory.

## Settings safety

The runner saves the model settings it is about to touch (up to 7 fields), sends only those fields,
and restores the saved values in a `finally` block. The proof after a test is a settings file that is
byte-identical to a copy taken before it.

## Answer-quality rules

- A row is scored, not filtered. Wrong answers stay in the file, because accuracy is the measurement.
- A reply with no answer text (only reasoning, usually because the token cap ran out) is scored
  wrong. Caps are 2,048 tokens for GSM8K, 1,024 for MMLU and 256 for a passkey.
- `--retry-capped` asks cut-off answers again with a larger cap, in the same setting. The report puts
  the new answer in the place of the old one and says how many are still cut off.
- GSM8K is scored on the final number only. MMLU is scored on the letter. Passkey is scored on the
  7-digit number in the reply, ignoring commas.
- Passkey prompts are built from filler text sized at about 1.11 tokens per word, measured against
  the server's own token count. The real prompts came out at 99.6% to 99.7% of the target size.
- Every passkey prompt starts with a line that is unique to its setting and sample. Without it the
  server answers a repeated prompt from its prompt cache, and the setting under test never reads the
  prompt. The passkey numbers published here come from a second run with that line: 0 cached tokens
  in every row.
- Settings are applied once per setting and restored at the end.

## Reading the quality numbers

- The chart shows a 95% Wilson interval for each accuracy. It describes one setting on one question
  set. It is not a test of the difference between two settings.
- The table also gives paired counts: how many answers a setting got right that the baseline got
  wrong, and the reverse. The same questions are asked under every setting, so these counts show
  movement that an unchanged accuracy can hide.
- The Apple chip and the helper do no visible work on short prompts. Their rows on GSM8K and MMLU are
  therefore a measure of run-to-run variation, not of the add-on.

## Limits

- One Mac, one helper, one model, one pre-release oMLX build, on each pair.
- Cold cache. Every test but one sends one request at a time; the many-users test sends up to 8 at
  once, and it is the only concurrent result here. No warm-cache numbers.
- Three runs per case, and 2 in the prompt-size test on Mac B.
- The size of the KV cache is not measured. Peak MLX active memory is reported instead.
- Helper memory and temperature are not recorded.
- Decode speed varies with the multi-token prediction path and is not studied.
- The quality question sets are small: about 3 points of sampling error for GSM8K 200 and about 4 for
  MMLU 500 at 90% confidence (see [data/README.md](../data/README.md)). Compare settings inside one
  run, not against published full-test scores.
- `bench/report.py` merges every JSONL file under the folder it is given. To report one test, give it
  that test's file.

## Many users at once

`bench/concurrency.py` runs one group at a time: one prompt size, one setting, and N chat requests
released together (`--users`, `--waves`). Before a group it sends the settings, probes the model and
waits for the helper, as both other runners do, then releases the requests through one gate, so no
request begins before the whole group does. Each request carries its own prompt and its own offset
from the group start. A row is one request, and a group counts only when every request came back.

Back to [the front page](../README.md).
