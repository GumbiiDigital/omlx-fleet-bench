# Contributing

Results from other machines are the most useful thing you can add. Code fixes are welcome too.

## Add results from your machine

1. Pick a label for your machine that says what it is and nothing private, for example
   `m4-max-128gb` or `m3-ultra-b`. Do not use a host name.
2. Run a matrix with `--machine your-label` and `--out results/your-label/<study>-<date>.jsonl`.
   Use `speed`, `kv-cache` or `quality` as the study name. The commands are in the README.
3. Keep the JSONL as the harness wrote it. Do not delete rows that failed and do not edit values.
   If you measure a cell again, write the new pass to its own file.
4. Redact one value before you commit: your helper's node id, which appears as
   `prefill_helper_node_id` in every row. Replace it with `redacted-helper-node`.

   ```bash
   sed -i '' 's/YOUR-NODE-ID/redacted-helper-node/g' results/your-label/*.jsonl
   ```

5. Add your machine to `results/published.json`: its label, hardware, helper, model, and the files
   that make up each study. Leave out a study you did not run.
6. Add a section for your machine to `README.md` with the three marker pairs, for example
   `<!-- BEGIN GENERATED: speed your-label -->` and `<!-- END GENERATED: speed your-label -->`.
7. Run `python3 bench/publish.py`. It writes your tables, reports and charts.
8. Open a pull request. Say which oMLX version, macOS version, model and helper software you used,
   and anything that went wrong during the run.

## What makes results comparable

- Use the matrices in `matrices/` unchanged when you can. If you change one, commit it under a new
  name.
- Cold cache, and nothing else using the Mac or the helper during the run.
- Leave the helper wait on. `--helper-ready-timeout` (seconds, default 120) is how long a run waits
  for the helper session after a settings change; `--no-helper-wait` sends the request at once and
  is for replaying an older run only. Each row records `helper_state` and `helper_wait_s`.
- Report every pass. A second pass that looks better does not replace the first one.

## Change the code

- Python 3.9 or newer, standard library only. Please keep it that way.
- Run both checks before you open a pull request:

  ```bash
  python3 -m unittest discover -s tests
  python3 bench/publish.py --check
  ```

- A change to a chart or a table changes generated files. Run `python3 bench/publish.py` and commit
  what it writes.
