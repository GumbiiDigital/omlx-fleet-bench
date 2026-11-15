# Fleet Benchmark Plan: oMLX Prefill on Apple + Spark

Date: 2026-11-15
Status: PLAN, owner decisions taken 2026-11-15. Nothing has run. Every host change and every run waits for the owner's "Run it".

## Owner decisions (2026-11-15)

1. Repo: new public repo `omlx-fleet-bench` (harness + results). Upstream PRs stay on `GumbiiDigital/omlx-1`. Public push still needs the owner's OK.
2. Phase 2 (M5 Max, M4 Max): NOT run. M3 Ultra Macs only. No change to M5/M4.
3. Spark 3 and Spark 4: left alone.
4. Phase 5 (Flash-Next MoE): YES. Mac 2 only: Mac 3 has 72 GiB free disk, the model is 100.2 GiB.
5. (Later, same day) Do NOT repeat the same test on both Macs. Earlier runs already showed Mac 2 and Mac 3
   give nearly the same Mac-alone speed, so a copy adds nothing. New split, run at the same time:
   - Mac 3 + Spark 2: phase 1 (Qwen 27B: GPU / +ANE / +Spark / +both), then phases 3 and 4.
   - Mac 2 + Spark 1: phase 5 (Flash-Next MoE: GPU / +Spark).

## Goal

Publish data that other people can use to choose hardware and settings for long-prompt work on a Mac:
"For my Mac and my prompt size, how long do I wait for the first token, and what does each add-on buy me?"

Done = a public repo with the harness, the raw results, and charts. Anyone with oMLX can run the
harness and add their own rows.

## Why the first results were weak

| Weak point | Fix in this plan |
|---|---|
| 2 runs per setting | 3 runs per cell, run in A/B/A/B order, spread reported |
| One Mac | Two M3 Ultra Macs, each with its own Spark (checks machine-to-machine spread) |
| Prefill speed only | Time to first token, prefill tok/s, decode tok/s, total time, peak memory |
| "Same output" from one 128-token check | Passkey retrieval at 32K/64K/128K plus GSM8K and MMLU subsets, each setting |
| KV size calculated from docs | KV size measured from the server memory counters |
| Spark gain compared with a run from another session | Helper off and on in the same window, alternating |
| No way for others to repeat it | Harness + raw JSONL in a public repo |

## Fleet (checked 2026-11-15, read-only)

| Machine | Chip | GPU cores | RAM | oMLX now | Role |
|---|---|---|---|---|---|
| Mac 2 Ops | M3 Ultra | 60 | 256 GB | 0.8.0rc1 | Main Mac A |
| Mac 3 Media | M3 Ultra | 60 | 256 GB | 0.8.0rc1 | Main Mac B (same model as Mac 2: checks machine-to-machine spread) |
| M5 Max | M5 Max | 40 | 128 GB | not installed | Not used (owner) |
| M4 Max 1, M4 Max 2 | M4 Max | 40 | 128 GB | 0.5.8.dev2 | Not used (owner) |
| Spark 1 | GB10 | - | 128 GB | helper fix-4f4f4e69 | Helper for Mac 2 |
| Spark 2 | GB10 | - | 128 GB | helper 0.1.3 stock + fix image loaded | Helper for Mac 3 |
| Spark 3, Spark 4 | GB10 | - | 128 GB | busy: `glm53-flash-tf` up 6 days | Not used unless the owner frees them |
| Mac 1 | - | - | - | SSH key refused | Control seat only |

Links: Mac 2 and Mac 3 reach their Spark on 10 GbE fabric. M5/M4 ping Spark 1 at about 1 ms; link speed not checked (step 0).

## Test matrix

Model for all phases: `Jundot/Qwen3.8-27B-oQ4e-mtp` (17.5 GB, fits every Mac).
Prompt sizes: 8K, 32K, 64K, 128K. Output: 128 greedy tokens. Cold cache (0 cached tokens).

| Phase | Machines | Settings | Cells x 3 runs | Est. hours |
|---|---|---|---|---|
| 0. Setup + smoke | Mac 2, Mac 3, Spark 1, Spark 2 | harness smoke run, Spark 2 on fix image, link speed test | - | 1.5 |
| 1. Main | Mac 3 + Spark 2 | GPU / +ANE / +Spark / +ANE+Spark | 4 x 4 = 16 cells, 48 runs | 2.4 |
| ~~2. Other Macs~~ | ~~M5 Max, M4 Max 1~~ | skipped (owner) | - | 0 |
| 3. KV cache | Mac 3 | Native / Affine4 / Affine8 at 32K and 128K, measured memory | 6 cells, 18 runs | 1.7 |
| 4. Quality | Mac 3 | GPU vs ANE vs Affine4 vs Affine8 vs Spark: passkey 32K/64K/128K, GSM8K 200, MMLU 500 | 5 settings | 2.5 |
| 5. MoE | Mac 2 + Spark 1 | Flash-Next-oQ4e-mtp, GPU / +Spark, 32K and 64K (download 100.2 GiB first) | 4 cells, 12 runs | 3.0 |
| Margin | | Spark cool-down to 45 C, retries (+30%) | | 3.6 |
| **Total** | | | **78 timed runs** | **about 9 h on Mac 3; phase 5 runs on Mac 2 at the same time** |

Estimates use measured speeds for M3 Ultra. Phase 5 speeds are from the docs row (1388 -> 3574 tok/s at 32K on the reference Mac).

Phase 5 note: Flash-Next supports the Spark helper; ANE prefill does not apply (it is dense-Qwen only).

## Metrics per run

- From the oMLX log `[benchmark-pp-result]`: prefill tok/s, TTFT, decode tok/s, e2e, cached_tokens.
- From the run event: `upload_skipped` reason and the feature flags (prefill_accelerator, ANE).
- From `[benchmark-ane-summary]`: ANE tiles used (proves ANE ran).
- Spark: helper `session ready` line, peak used RAM, GPU temperature, container restart count.
- Mac: peak MLX active memory, swap at start and end.

A run counts only if: flags match the cell, 0 cached tokens, no helper drop, restart count unchanged.

## Method rules

- Private runs only (ANE-aligned prompt, `upload_skipped`). A public leaderboard upload is a separate owner choice.
- Order A/B/A/B within a cell group, so heat and time drift hit both sides.
- Spark below 45 C before each run at 64K and above.
- Put every setting back after each phase. Record before/after settings in the results.
- Report the mean, min and max per cell. Mark a cell "noisy" if the spread is over 3%.

## Repo layout (recommended: separate repo)

The harness only calls the oMLX admin API, so it does not need to live inside the oMLX source.
A separate repo keeps our fork clean for upstream PRs (like #5271).

```
omlx-fleet-bench/            (new public repo, name to confirm)
  README.md                  what, how to run, how to add your rows
  bench/
    client.py                oMLX admin API: login, settings, run, stream events
    matrix.py                loads a matrix file, expands cells, A/B order
    run.py                   runs the cells, writes one JSONL row per run
    collect.py               reads server.log / Spark stats for the run window
    report.py                tables + charts from results/*.jsonl
  matrices/
    m3-ultra-spark.yaml
    flash-next-moe.yaml
  results/<machine>/<date>.jsonl   raw rows, committed
  charts/                    PNGs from report.py
  tests/                     unit tests for matrix, parsing, report
```

Upstream PRs to `jundot/omlx` only for general fixes we find (for example a CLI benchmark or an upload opt-out),
from the existing fork `GumbiiDigital/omlx-1`.

Finish test for the build step: `python bench/report.py results/` -> one table and one chart per phase;
every cell has 3 valid runs; noisy cells are marked.

## Still open before "Run it"

- Spark 2: switch `omlx-helper-qwen-baseline` to image fix-4f4f4e69 for 128K (host change), or skip 128K + Spark on Mac 3.
- Mac 2: the paused GLM-5.3 job stays paused. Mac 2 default model is now GLM-5.3 (oMLX set it itself); the harness names the model on every call, so it is not changed.

## Risks

- ANE prefill uses private Apple APIs. A macOS update can stop it.
- Spark 2 runs the stock helper. It can drop at 128K (the bug fixed in PR #5271). Plan: run Spark 2 on the fix image, or skip 128K on Spark 2.
- Mac 3 runs the WoW Forever Colima containers. They use memory and can add noise. They are not stopped in this plan.
- 17 h of wall time over several days. Each phase is its own run, with its own "Run it".
