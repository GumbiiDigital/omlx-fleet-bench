# Method

What this repo measures, how, and what it does not measure. Written so a stranger can repeat the runs
and compare their rows with ours.

## Question

"For my Mac and my prompt size, how long do I wait for the first token, and what does each add-on buy me?"

Two add-ons are measured: ANE prefill (Apple Neural Engine does part of the prompt read) and the
prefill accelerator (an NVIDIA GB10 box, called the helper, reads the first N layers).

## Test matrix

Model for every phase: `Jundot/Qwen3.8-27B-oQ4e-mtp`. Prompt sizes 8K, 32K, 64K, 128K. Output 128 greedy
tokens. Context profile `code_python`. Cold cache (0 cached tokens). 3 runs per cell, ordered across
variants so heat and time drift hit every side.

| Phase | What | Cells | Runs |
|---|---|---|---|
| 1 | `matrices/m3-ultra-spark.json`: GPU / + ANE / + helper / + ANE + helper at 4 sizes | 16 | 48 |
| 3 | `matrices/kv-cache.json`: native / Affine4 / Affine8 KV at 32K and 128K | 6 | 18 |
| 5 | `matrices/flash-next-moe.json`: MoE model, GPU / + helper (not run in this repo yet) | 4 | 12 |

Phase 2 (other Mac models) and phase 4 (answer quality: passkey, GSM8K, MMLU) are **not built here**.

## What a row records

Per run: timestamp, machine label, matrix, model, variant, prompt size, repeat index, the settings sent
(`desired_settings`), the settings found before the run (`settings_before`), the bench id, the status,
the terminal event type (`upload_skipped` expected), the feature flags the server reported, metrics from
`[benchmark-pp-result]` (prefill tokens/s, time to first token, decode tokens/s, end-to-end, peak memory),
the parsed log line, a validity verdict, and `spark_stats` (empty unless `--spark-stats-cmd` is given).

## Rules that make a row count

A row is valid only when all of these hold:

- status is `completed`;
- the terminal event is `upload_skipped` (the run stayed private);
- cached tokens are 0 (cold cache);
- the feature flags match the cell: `prefill_accelerator` present for helper rows and absent otherwise;
- for ANE rows, the log shows ANE operations actually ran (the tile estimate alone is not enough).

`bench/validity.py` makes the call and writes the reasons. Rows that fail stay in the file; they are not
deleted.

## Noise

A cell is noisy when the spread of prefill tokens/s over valid runs is over 3%.
`report.py` marks it. The usual causes seen so far: the first run after a model load, and helper runs
that follow several minutes of Mac-only work (helper throughput is 5% to 15% higher when it runs back to
back). Re-measure one cell with `--only-cells variant:size`; do not loop.

## Heat

The plan says the helper GPU should be below 45 C before 64K and 128K runs, and that a run is stopped if
the GPU reaches 85 C. In the runs in this repo the helper peaked at 57 C and never reached the stop mark.

## Settings safety

The harness snapshots the model settings it touches (up to 7 fields), applies only those fields with a
PUT, and restores the snapshot in a `finally` block. Proof after a phase: `settings` file byte-identical,
or the model settings file identical, to a copy taken before the phase.

## Limits

- KV cache size in GB is not measured. Peak MLX active memory is reported instead.
- Spark memory and temperature are not collected unless `--spark-stats-cmd` is passed.
- `report.py` merges every JSONL under the folder it is given. Report one phase by giving it a folder
  that holds only that phase's file.
- Decode tokens/s varies with the MTP (multi-token prediction) path and is not studied here.
