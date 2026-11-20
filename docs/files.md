# What is in this repository

Question: where do I find the file I need?

Grouped by what you are looking for. Every file name is a link, so you can open it.

Words on this page:

- **run file**: the list of setups and prompt sizes a test runs.
- **row file**: the file a run writes, one line per request.
- **report**: a full table made from the rows, for a reader who wants to check them.
- **chart**: a picture of one result, in a dark and a light version.

## Pages to read

- [The front page](../README.md): the short answer and the way in.
- [Speed](speed.md): how long a Mac makes you wait, and what the Spark takes off.
- [Many users](many-users.md): several prompts sent at the same moment.
- [Memory](memory.md): what the prompt memory costs.
- [Answer quality](answer-quality.md): whether the Spark changes the answers.
- [Helper start-up](helper-setup.md): the slow first request, and how many layers to give the Spark.
- [Run it](run-it.md): the commands, step by step.
- [Method](method.md): how the numbers were made, and their limits.

## The tests you can run

- [The speed test runner](../bench/run.py): one row per run.
- [The answer-quality runner](../bench/quality.py): one row per question.
- [The many-users runner](../bench/concurrency.py): one row per request of a group.
- [The run-file loader](../bench/matrix.py): reads a run file and expands it into the planned requests.
- [The runner around a measured request](../bench/runflow.py): the order of calls, shared by the chat tests.

## What reads the rows

- [The speed report](../bench/report.py): a table and charts from your own speed rows.
- [The quality report](../bench/quality_report.py): accuracy per setting, from your own quality rows.
- [The request reader](../bench/latency.py): reads a row as one request, with its wait and its helper state.
- [The group reader](../bench/waves.py): reads the requests of a many-users test as groups.
- [The page builder](../bench/publish.py): rebuilds the tables on the pages, the reports and the charts.
- [The page checker](../bench/readable.py): checks a page for wide tables, hard words and long lists.

## What draws and names things

- [The chart forms](../bench/charts.py): bar panels, dot panels with a range, and line panels.
- [The SVG writer](../bench/svg.py): the small writer behind every chart.
- [The statistics](../bench/stats.py): the few figures the reports and charts share.
- [The setup names](../bench/labels.py): each setup's name, order and colour, in one place.

## How a run talks to the server

- [The admin and chat clients](../bench/client.py): how a run logs in and sends a request.
- [The chat client](../bench/chat.py): the chat call the quality and many-users tests use.
- [The helper id reader](../bench/helper_id.py): prints the Spark id your server keeps for a model.
- [The helper fields](../bench/helper.py): what the runner reads from the helper, and the wait rule.
- [The server log reader](../bench/collect.py): reads the benchmark sections of the oMLX server log.
- [The quality questions](../bench/qa.py): the passkey, GSM8K and MMLU questions and their scoring.

## How a row is judged

- [The validity checker](../bench/validity.py): decides whether a speed row counts.
- [The chat row](../bench/chatrows.py): the row both chat tests write, and the rule that stops a run.
- [The row field reference](../results/README.md): the name and meaning of every field in a row.

## Data

- [The question sets](../data): the fixed GSM8K and MMLU questions, and how they were built.
- [The fetcher](../scripts/fetch_quality_data.py): builds those two question files.
- [The raw rows](../results): one file per run, and the field reference.
- [The full tables](../reports): the tables behind each page.
- [The charts](../charts): every chart, light and dark.

## Run files for the Qwen 27B machine

- `m3-ultra-spark.json`: the speed test, four setups at four prompt sizes.
- `kv-cache.json`: the prompt memory test.
- `quality.json`: the answer-quality test, which both Macs ran.
- `m3-ultra-a-helper-ready.json` and `m3-ultra-a-helper-ready-chat.json`: the helper start-up test.
- `m3-ultra-a-helper-layers-chat-32k.json` and `m3-ultra-a-helper-layers-chat-128k.json`: the layer test.

## Run files for the Flash-Next machine

- `m3-ultra-b-speed.json`: the speed test.
- `m3-ultra-b-kv-cache.json`: the prompt memory test.
- `m3-ultra-b-quality.json`: the answer-quality test.
- `m3-ultra-b-speed-sweep.json`: the prompt-size test, from 1K to 128K.
- `m3-ultra-b-many-users.json`: the many-users test.
- `m3-ultra-b-256k.json`: the 256K attempt, which the server refused.

## Shared run files

- `smoke.json`: a two-run check that the runner can talk to your server.
- `flash-next-moe.json`: an earlier file for a mixture-of-experts model; its results are not here.

## Tests

- [The unit tests](../tests): tests for the runner, with their fixtures.
- [The test workflow](../.github/workflows/tests.yml): runs the tests and the page check on a push.

Back to [the front page](../README.md).
