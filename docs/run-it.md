# Run it on your own Mac

Question: how do I try this on my own Mac and Spark, and what will it do to my server?

The commands below run the same tests that made the rows in this repository. Python 3.9 or newer,
standard library only, so there is nothing to install.

## What you need

- oMLX running on your Mac, answering at a base URL such as `http://127.0.0.1:8004`.
- The settings file the server reads, normally `$HOME/.omlx/settings.json`, and its server log.
- Your Spark paired as the helper, and its node id, which goes in `--helper-node`.
- A run file from `matrices/` to say which prompt sizes and setups to run, and a label of your own
  for the machine, passed as `--machine`.

## What a run does to your server

- **Settings are put back.** The runner saves the model settings it touches, changes only those, and
  restores them at the end, even after an error. After each study here the settings file was
  byte-identical to a copy taken before it.
- **Nothing is uploaded.** Every speed run ends with `upload_skipped`, and the runner refuses to
  start a run with that off. The quality path uses plain chat requests, which have no upload at all.
- **Your key is never printed.** It is read from the settings file and used for a session cookie.

## Steps

1. Look at what a run would do, and touch nothing:

   ```bash
   python3 bench/run.py \
     --matrix matrices/m3-ultra-spark.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-label \
     --out results/your-label/speed-DATE.jsonl \
     --dry-run
   ```

2. Run the speed test: the wait for the first word, at 8K, 32K, 64K and 128K tokens, for each setup
   in the run file. Take out `--dry-run` and the command runs it.

3. Build a summary of your own speed rows:

   ```bash
   python3 bench/report.py results/your-label/speed-DATE.jsonl --report-dir report
   ```

4. Run the answer-quality test. It takes about 85 minutes per setting on the hardware here, so about
   7 hours for all five settings in `matrices/quality.json`:

   ```bash
   python3 bench/quality.py \
     --matrix matrices/quality.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-label \
     --out results/your-label/quality-DATE.jsonl

   python3 bench/quality_report.py results/your-label/quality-DATE.jsonl --out report/quality.md
   ```

5. Run a many-users test: N requests that start at the same moment, called one group here.

   ```bash
   python3 bench/concurrency.py \
     --matrix matrices/m3-ultra-b-many-users.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-label \
     --out results/your-label/many-users-DATE.jsonl
   ```

   `bench/report.py` on a many-users file writes a speed summary with an empty table, because it
   groups speed rows only. The group tables and charts come from `python3 bench/publish.py`, which
   reads the file named under `many_users` for your machine in `results/published.json`.

6. Check the numbers in this repository before you trust them:

   ```bash
   python3 -m unittest discover -s tests
   python3 bench/publish.py --check
   ```

   The first command runs the unit tests. The second recomputes every table and chart from the raw
   rows in `results/` and fails if a single byte differs from what is committed.
   `python3 bench/publish.py` without `--check` writes them again.

## Useful options

- `--only-cells gpu:32768` (speed) and `--only-variants`, `--only-tasks`, `--limit N` (quality)
  narrow a run to one setup or a few questions.
- `--users 1,2,4` and `--waves 3` (many users) set the user counts and the number of groups.
- `--retry-capped FILE --max-tokens-scale 8` asks the cut-off answers in `FILE` again with a larger
  cap, and `quality_report.py --replace` merges them in.
- Leave the helper wait on. `--helper-ready-timeout` (seconds, default 120) limits the wait, and
  `--helper-stable-s` (default 5) says how long `ready` must hold. `--no-helper-wait` is only for
  replaying an older run.

## Add your machine

Results from other Macs, other Sparks and other models are welcome. Run a run file with your own
`--machine` label, keep the raw rows untouched, and open a pull request.
[CONTRIBUTING.md](../CONTRIBUTING.md) has the steps and the one value to redact.

Back to [the front page](../README.md). Where every file lives: [what is in this repository](files.md).
