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
- Your Spark paired as the helper, and its node id.
- A run file from `matrices/` to say which prompt sizes and setups to run, and a name of your own for
  your machine, passed as `--machine`.

## Where the helper's node id comes from

The server keeps its Spark id in a model setting named `prefill_helper_node_id`, and the runner sends
that same id when you pass it as `--helper-node`. If your Spark is already paired, the value is there
to copy: it is in the model settings your server holds, and the file you pass to `--settings`
(normally `$HOME/.omlx/settings.json`) is where oMLX keeps its own copy. An empty value means the
Spark is not paired yet, and this repository does not cover pairing it.

In every command below, `YOUR_HELPER_NODE_ID` is the placeholder you replace with that value.

## Which run file fits which Mac

| Run file | Mac | What it tests |
|---|---|---|
| `matrices/m3-ultra-spark.json` | Mac A | speed, four setups at four prompt sizes |
| `matrices/kv-cache.json`, `matrices/m3-ultra-b-kv-cache.json` | Mac A, Mac B | the prompt memory settings, alone on the Mac |
| `matrices/quality.json`, `matrices/m3-ultra-b-quality.json` | Mac A, Mac B | answers, 700 questions (five settings on Mac A, four on Mac B) |
| `matrices/m3-ultra-a-helper-ready.json`, `matrices/m3-ultra-a-helper-ready-chat.json` | Mac A | the helper start-up wait |
| `matrices/m3-ultra-a-helper-layers-chat-32k.json`, `matrices/m3-ultra-a-helper-layers-chat-128k.json` | Mac A | how many layers the Spark holds |
| `matrices/m3-ultra-b-speed.json` | Mac B | speed, two setups at four prompt sizes |
| `matrices/m3-ultra-b-speed-sweep.json` | Mac B | the wait at seven prompt sizes, 1K to 128K |
| `matrices/m3-ultra-b-many-users.json` | Mac B | groups of users sending at the same moment |
| `matrices/m3-ultra-b-256k.json` | Mac B | the 256K attempt, which the server refused |
| `matrices/smoke.json` | both | a two-run check that the runner can talk to your server |
| `matrices/flash-next-moe.json` | both | a model that uses only part of itself for each word; no published results |

Where a row names two files, they are one test split in two: the start-up pair by the way a prompt is
sent, the layer pair by prompt size, and the rest one file for each Mac.

## What a run does to your server

- **Settings are put back.** The runner saves the model settings it touches, changes only those, and
  restores them at the end, even after an error. After each test here the settings file was
  exactly the same as a copy taken before it.
- **Seven settings, and only while the run lasts.** Which Spark the Mac sends long prompts to. How
  many model layers the Spark holds. Whether the Apple Neural Engine helps read the prompt. And four
  settings for the 4-bit prompt memory: on or off, which setting, how many bits, and whether the last
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

1. Start with the two-run check that the runner can talk to your server. It makes two rows and its
   time is not recorded:

   ```bash
   python3 bench/run.py \
     --matrix matrices/smoke.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --server-log "$HOME/.omlx/logs/server.log" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-name \
     --out results/your-name/smoke-DATE.jsonl
   ```

2. Look at what the speed run would do, and touch nothing. This one sends no request, so it makes no
   rows and its time is not recorded:

   ```bash
   python3 bench/run.py \
     --matrix matrices/m3-ultra-spark.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --server-log "$HOME/.omlx/logs/server.log" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-name \
     --out results/your-name/speed-DATE.jsonl \
     --dry-run
   ```

3. Run the speed test: the wait for the first word at 8K, 32K, 64K and 128K tokens, for each setup in
   the run file. This is the same command as step 2, without `--dry-run`. It took about 2 hours 23
   minutes on Mac A (48 runs) and about 1 hour 40 minutes on Mac B (24 runs):

   ```bash
   python3 bench/run.py \
     --matrix matrices/m3-ultra-spark.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --server-log "$HOME/.omlx/logs/server.log" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-name \
     --out results/your-name/speed-DATE.jsonl
   ```

4. Build a summary of your own speed rows. It only reads the row file, so its time is not recorded:

   ```bash
   python3 bench/report.py results/your-name/speed-DATE.jsonl --report-dir report
   ```

5. Run the answer-quality test. On Mac A the five settings took about 1 hour 16 minutes for the 706
   answers with the Mac alone and about 5 hours 42 minutes for the 2,824 answers with the add-ons. On
   Mac B the four settings took about 7 hours 43 minutes (2,824 answers):

   ```bash
   python3 bench/quality.py \
     --matrix matrices/quality.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-name \
     --out results/your-name/quality-DATE.jsonl

   python3 bench/quality_report.py results/your-name/quality-DATE.jsonl --out report/quality.md
   ```

6. Run a many-users test: N requests that start at the same moment, called one group here. It took
   about 56 minutes on Mac B (180 requests):

   ```bash
   python3 bench/concurrency.py \
     --matrix matrices/m3-ultra-b-many-users.json \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --helper-node YOUR_HELPER_NODE_ID \
     --machine your-name \
     --out results/your-name/many-users-DATE.jsonl
   ```

   `bench/report.py` on a many-users file writes a speed summary with an empty table, because it
   groups speed rows only. The group tables and charts come from `python3 bench/publish.py`, which
   reads the file listed for your machine in the published results list.

7. Check the numbers in this repository before you trust them. These read the files only, so their
   time is not recorded:

   ```bash
   python3 -m unittest discover -s tests
   python3 bench/publish.py --check
   ```

   The first command runs the unit tests. The second recomputes every table and chart from the raw
   rows in `results/` and fails if a single byte differs from what is committed.
   `python3 bench/publish.py` without `--check` writes them again.

## Useful options

- `--dry-run` prints the plan and sends nothing.
- `--only-cells gpu:32768` (speed) runs one setup at one prompt size.
- `--only-variants`, `--only-tasks` and `--limit N` (quality) run some settings, some question sets, or
  the first N questions of each set.
- `--users 1,2,4` and `--waves 3` (many users) set how many users a group holds and how many groups to
  run.
- `--retry-capped FILE --max-tokens-scale 8` asks the answers that ran out of tokens again with a
  bigger cap, and `quality_report.py --replace` puts the new answers in place of the old ones.
- `--helper-ready-timeout` (seconds, default 120) is how long the run waits for the Spark to be ready.
- `--helper-stable-s` (default 5) is how long the Spark must stay ready before the run trusts it.
- `--no-helper-wait` skips that wait; use it only to replay an older run.

## Add your machine

Results from other Macs, other Sparks and other models are welcome. Run a run file with your own
`--machine` name, keep the raw rows untouched, and open a pull request.
[CONTRIBUTING.md](../CONTRIBUTING.md) has the steps and the one value to hide.

Back to [the front page](../README.md). Where every file lives: [what is in this repository](files.md).
