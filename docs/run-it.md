# Run it on your own Mac

Question: how do I try this on my own Mac and Spark, and what will it do to my server?

The commands below run the same tests that made the numbers in this repository. Python 3.9 or newer,
and no extra packages to install.

**Every settings change makes your server unload the model and load it again.** Do not run this on a
server that other people use.

Words on this page:

- **helper**: the DGX Spark that reads long prompts for the Mac.
- **settings file**: the file your oMLX server reads when it starts.
- **server log**: the file the server writes while it runs; the runner reads it to prove a run was cold.
- **row file**: the file a run writes, one line per request.
- **dry run**: a command that prints the plan and touches nothing.

## What you need

- oMLX running on your Mac, answering at an address such as `http://127.0.0.1:8004`.
- The settings file the server reads, normally `$HOME/.omlx/settings.json`, and its server log.
- Your Spark paired as the helper. You also need the helper's own name, the node id, which goes in
  `--helper-node`; this repository does not cover finding it, so see the oMLX helper's own guide.
- A run file from `matrices/` to say which prompt sizes and setups to run, and a name of your own for
  your machine, passed as `--machine`.

## Which run file fits which Mac

- The files whose names start with `m3-ultra-b` were run on Mac B, the Flash-Next machine.
- The other files were run on Mac A, the Qwen 27B machine.

Pick the one that matches your model, or start with `matrices/smoke.json`, a two-run check that the
runner can talk to your server.

## What a run does to your server

- **Settings are put back.** The runner saves the model settings it touches, changes only those, and
  restores them at the end, even after an error. After each test here the settings file was
  exactly the same as a copy taken before it.
- **Seven settings, and only while the run lasts.** Which Spark the Mac sends long prompts to. How
  many model layers the Spark holds. Whether the Apple Neural Engine helps read the prompt. And four
  settings for the 4-bit prompt memory: on or off, which scheme, how many bits, and whether the last
  layers are left as they are.
- **Nothing is uploaded.** Every speed run ends by confirming that it uploaded nothing, and the
  runner refuses to start a run with that turned off. The quality test uses plain chat requests, which
  have no upload at all.
- **Your key is never printed.** It is read from the settings file and used to log in.

## Steps

0. Get the code:

   ```bash
   git clone https://github.com/GumbiiDigital/omlx-fleet-bench
   cd omlx-fleet-bench
   ```

1. Look at what a run would do, and touch nothing:

   ```bash
   python3 bench/run.py \
     --matrix matrices/m3-ultra-spark.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --server-log "$HOME/.omlx/logs/server.log" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-label \
     --out results/your-label/speed-DATE.jsonl \
     --dry-run
   ```

2. Run the speed test: the wait for the first word at 8K, 32K, 64K and 128K tokens, for each setup in
   the run file. This is the same command as step 1, without `--dry-run`:

   ```bash
   python3 bench/run.py \
     --matrix matrices/m3-ultra-spark.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --server-log "$HOME/.omlx/logs/server.log" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-label \
     --out results/your-label/speed-DATE.jsonl
   ```

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
   reads the file listed for your machine in the published results list.

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
  `--helper-stable-s` (default 5) says how long the helper must stay ready. `--no-helper-wait` is only
  for replaying an older run.

## Add your machine

Results from other Macs, other Sparks and other models are welcome. Run a run file with your own
`--machine` name, keep the raw rows untouched, and open a pull request.
[CONTRIBUTING.md](../CONTRIBUTING.md) has the steps and the one value to hide.

Back to [the front page](../README.md). Where every file lives: [what is in this repository](files.md).
