# Contributing

Results from other machines are the most useful thing you can add. Code fixes are welcome too.

## Add results from your machine

1. Pick a label for your machine that says what it is and nothing private, for example
   `studio-256gb` or `m3-ultra-b`. Do not use a host name.
2. Run a run file from `matrices/` with `--machine your-label` and
   `--out results/your-label/<test>-<date>.jsonl`. Use `speed`, `kv-cache` or `quality` as the test
   name. The commands are in [docs/run-it.md](docs/run-it.md).
3. Keep the JSONL as the runner wrote it. Do not delete rows that failed and do not edit values.
   If you measure a case again, write the new pass to its own file.
4. Redact one value before you commit: your helper's node id, which appears as
   `prefill_helper_node_id` in every row. Replace it with `redacted-helper-node`.

   macOS:

   ```bash
   sed -i '' 's/YOUR-NODE-ID/redacted-helper-node/g' results/your-label/*.jsonl
   ```

   Linux:

   ```bash
   sed -i 's/YOUR-NODE-ID/redacted-helper-node/g' results/your-label/*.jsonl
   ```

5. Add your machine to `results/published.json`: its label, display name, hardware, helper, model,
   and the files that make up each test. Leave out a test you did not run.
6. Add your markers to the page that holds that result: `docs/speed.md` for a speed test,
   `docs/memory.md` for a KV cache test, `docs/answer-quality.md` for a quality test and
   `docs/many-users.md` for a many-users test. A speed pair reads
   `<!-- BEGIN GENERATED: speed your-label -->` and `<!-- END GENERATED: speed your-label -->`.
7. Run `python3 bench/publish.py`. It writes your tables, reports and charts.
8. Open a pull request. Say which oMLX version, macOS version, model and helper software you used,
   and anything that went wrong during the run.

## What makes results comparable

- Use the run files in `matrices/` unchanged when you can. If you change one, commit it under a new
  name.
- A cold cache, and nothing else using the Mac or the Spark during the run.
- Leave the helper wait on. `--helper-ready-timeout` (seconds, default 120) limits the wait, and
  `--helper-stable-s` (default 5) says how long `ready` must hold with one session start. Every
  request is made after a one-token probe of the model, and each row records `helper_state`,
  `helper_wait_s`, `helper_layers`, `helper_held`, `helper_session_since`, `helper_last_prompt_at`,
  `helper_last_prompt_tokens` and `helper_last_prompt_seconds`. `--no-helper-wait` is for replaying
  an older run only.
- Report every pass. A second pass that looks better does not replace the first one.

## Change the code

- Python 3.9 or newer, standard library only. Please keep it that way.
- Run both checks before you open a pull request:

  ```bash
  python3 -m unittest discover -s tests
  python3 bench/publish.py --check
  ```

- Write page text for a person: short sentences, plain words, and `python3 bench/readable.py <file>`
  tells you if a hard word slipped in. The unit tests run it on every page.
- A change to a chart or a table changes generated files. Run `python3 bench/publish.py` and commit
  what it writes.
