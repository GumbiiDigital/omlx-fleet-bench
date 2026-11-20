# What is in this repository

Question: where do I find the file I need?

Grouped by what you are looking for. A path is a link where that helps; run file names are shown as
they are.

## Pages to read

- [README.md](../README.md): the front door.
- [speed.md](speed.md), [many-users.md](many-users.md), [memory.md](memory.md),
  [answer-quality.md](answer-quality.md), [helper-setup.md](helper-setup.md): one question per page.
- [run-it.md](run-it.md): the commands, step by step.
- [method.md](method.md): how the numbers were made, and their limits.
- [CONTRIBUTING.md](../CONTRIBUTING.md): how to add your own results.

## Code

- [bench/run.py](../bench/run.py): the speed test, one row per run.
- [bench/quality.py](../bench/quality.py): the answer-quality test, one row per question.
- [bench/concurrency.py](../bench/concurrency.py): the many-users test, one row per request of a group.
- [bench/chatrows.py](../bench/chatrows.py): the row both chat tests write, and the rule that stops a run.
- [bench/report.py](../bench/report.py), [bench/quality_report.py](../bench/quality_report.py):
  summaries of your own rows.
- [bench/latency.py](../bench/latency.py): reads a row as one request: its wait, its setting, its helper state.
- [`bench/waves.py`](../bench/waves.py): reads the requests of a many-users test as groups.
- [bench/publish.py](../bench/publish.py): rebuilds the tables on the pages, `reports/` and `charts/` from `results/`.
- [bench/charts.py](../bench/charts.py), [bench/svg.py](../bench/svg.py): the chart forms and the SVG writer behind them.
- [bench/stats.py](../bench/stats.py): the small statistics the reports and charts share.
- [bench/labels.py](../bench/labels.py): setup names, their order and their chart colour, in one place.
- [bench/client.py](../bench/client.py), [bench/chat.py](../bench/chat.py): the oMLX admin and chat clients.
- [bench/validity.py](../bench/validity.py): decides whether a speed row counts.
- [bench/helper.py](../bench/helper.py): helper field names, the read, and the wait rule.
- [bench/runflow.py](../bench/runflow.py): the order of calls around a measured request, shared by both tests.
- [bench/collect.py](../bench/collect.py): reads the benchmark sections of the oMLX server log.
- [bench/qa.py](../bench/qa.py): the passkey, GSM8K and MMLU questions and their scoring, with no network.
- [`bench/matrix.py`](../bench/matrix.py): loads a run file and expands it into the planned requests.
- [bench/readable.py](../bench/readable.py): checks a page for wide tables and hard words.
- [bench/__init__.py](../bench/__init__.py): marks `bench/` as a Python package.

## Data

- [data/](../data): the fixed GSM8K and MMLU question sets, and how they were built.
- [scripts/fetch_quality_data.py](../scripts/fetch_quality_data.py): builds those two files.
- [results/](../results): the raw rows, one file per run, and the field reference.
- [reports/](../reports): the full tables behind each page.
- [charts/](../charts): the charts, light and dark.

## Settings for runs

The run files in [matrices/](../matrices) say what to run: which setups, prompt sizes and questions.

- `m3-ultra-spark.json` and `kv-cache.json`: the speed and KV cache tests on Mac A.
- `quality.json`: the answer-quality test on both Macs.
- `m3-ultra-b-speed.json`, `m3-ultra-b-kv-cache.json`, `m3-ultra-b-quality.json`: the same three tests on Mac B.
- `m3-ultra-b-speed-sweep.json`, `m3-ultra-b-256k.json`: the prompt-size test on Mac B, and the 256K attempt.
- `m3-ultra-a-helper-ready.json`, `m3-ultra-a-helper-ready-chat.json`: the helper start-up test.
- `m3-ultra-a-helper-layers-chat-32k.json`, `m3-ultra-a-helper-layers-chat-128k.json`: the layer test.
- `m3-ultra-b-many-users.json`: the many-users test on Mac B.
- `smoke.json`: a two-run check that the runner can talk to your server.
- `flash-next-moe.json`: an earlier run file for a mixture-of-experts model; its results are not published here.

## Tests

- [tests/](../tests): unit tests for the runner, with their fixtures.
- [.github/workflows/tests.yml](../.github/workflows/tests.yml): runs the tests and the publish check on a push.

Back to [the front page](../README.md).
