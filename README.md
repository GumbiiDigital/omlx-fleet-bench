# omlx-fleet-bench

Harness for repeatable **private** oMLX throughput benchmarks across Mac + Spark settings.
Raw rows live under `results/<machine>/`; this repo is meant to be shared so others can add their own machines.

## Private runs only

Every benchmark start sets `align_prompt_to_ane: true`. That keeps prompts ANE-aligned so runs end with
`upload_skipped` and never hit the public leaderboard. Do not disable this flag in matrix files.

## Layout

- `bench/client.py` — admin API login, settings restore, bench start/poll/stream
- `bench/matrix.py` — JSON matrices → ordered run list (A/B across variants)
- `bench/run.py` — executes cells, appends JSONL per run
- `bench/collect.py` — parse `server.log` benchmark lines
- `bench/report.py` — markdown tables + SVG TTFT charts
- `matrices/*.json` — experiment definitions

## Dry run (no API calls)

```bash
cd omlx-fleet-bench
python3 bench/run.py \
  --matrix matrices/m3-ultra-spark.json \
  --helper-node YOUR_SPARK_NODE_ID \
  --dry-run \
  --base-url http://127.0.0.1:8004 \
  --settings /path/to/omlx/settings.json \
  --server-log /path/to/server.log \
  --machine mac-2-ops \
  --out results/mac-2-ops/2026-11-15.jsonl
```

## Real run (on the Mac next to oMLX)

Use the Mac-local paths for `settings.json` and `server.log`. The harness reads the API key from
`settings.json` (`auth.api_key`) and never prints it.

```bash
python3 bench/run.py \
  --matrix matrices/m3-ultra-spark.json \
  --helper-node YOUR_SPARK_NODE_ID \
  --base-url http://127.0.0.1:8004 \
  --settings "$HOME/Library/Application Support/omlx/settings.json" \
  --server-log /path/to/server.log \
  --machine mac-2-ops \
  --out results/mac-2-ops/2026-11-15.jsonl
```

Filter cells with `--only-cells gpu:32768,ane:32768`.

## Report

```bash
python3 bench/report.py results/
# writes report/summary.md and report/charts/*.svg
# exit 0 when every cell has enough valid runs and none are noisy (>3% spread)
```

## Adding your machine

1. Run the harness with `--machine your-label` and `--out results/your-label/DATE.jsonl`.
2. Commit the JSONL under `results/your-label/` (or open a PR with just your rows).
3. Regenerate the report locally before publishing.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Python 3.9+, standard library only.