# Contributing

Results from other machines are the most useful thing you can add. Code fixes are welcome too.

## Add results from your machine

1. Pick a name for your machine that says what it is and nothing private, for example `studio-256gb`.
   Do not use a host name.
2. Run a run file from `matrices/` with `--machine your-name` and
   `--out results/your-name/<test>-<date>.jsonl`. Use `speed`, `kv-cache` or `quality` as the test
   name. The commands are in [run it](docs/run-it.md).
3. Keep the row file as the runner wrote it. Do not delete rows that failed and do not edit values.
   If you measure a case again, write the new pass to its own file.
4. Hide one value before you commit: your helper's node id, which appears in every row. The id names
   your Spark; it is not a password, but keep it private.

   Read the id from your server into a shell variable. The command prints the id alone on one line,
   so the variable holds nothing else:

   ```bash
   HELPER_ID=$(python3 bench/helper_id.py \
     --base-url http://127.0.0.1:8004 \
     --settings "$HOME/.omlx/settings.json" \
     --model your-model)
   ```

   `--model` takes your model's id, the name your server lists it under. With no `--model` the same
   command lists every model your server holds.

   A model with no helper id gets a sentence instead of an id, and the variable would then hold that
   sentence. So pair the Spark in oMLX first, then run the command again.

   Replace the id with `redacted-helper-node` in every row file. The double quotes let the shell
   expand the variable:

   macOS:

   ```bash
   sed -i '' "s/$HELPER_ID/redacted-helper-node/g" results/your-name/*.jsonl
   ```

   Linux, with the same line but no `''` after `-i`:

   ```bash
   sed -i "s/$HELPER_ID/redacted-helper-node/g" results/your-name/*.jsonl
   ```

   Then check that no row still holds the id. Every file must print `0`. Do not commit until every
   one does:

   ```bash
   grep -c "$HELPER_ID" results/your-name/*.jsonl
   ```

5. Add your machine to the published results list, `results/published.json`: its name, its display
   name, its hardware, its helper, its model, and the files that make up each test. Leave out a test
   you did not run.
6. Add your markers to the page that holds that result: [speed](docs/speed.md) for a speed test,
   [memory](docs/memory.md) for a prompt memory test, [answer quality](docs/answer-quality.md) for a
   quality test and [many users](docs/many-users.md) for a many-users test. A speed pair reads
   `<!-- BEGIN GENERATED: speed your-name -->` and `<!-- END GENERATED: speed your-name -->`.
7. Run `python3 bench/publish.py`. It writes your tables, reports and charts.
8. Open a pull request. Say which oMLX version, macOS version, model and helper software you used,
   and anything that went wrong during the run.

## What makes results comparable

- Use the run files in `matrices/` unchanged when you can. If you change one, commit it under a new
  name.
- A cold cache, and nothing else using the Mac or the Spark during the run.
- Leave the helper wait on. `--no-helper-wait` is for replaying an older run only.
- Report every pass. A second pass that looks better does not replace the first one.

## Change the code

- Python 3.9 or newer, and no extra packages. Please keep it that way.
- Run both checks before you open a pull request:

  ```bash
  python3 -m unittest discover -s tests
  python3 bench/publish.py --check
  ```

- Write page text for a person: short sentences, plain words. `python3 bench/readable.py <file>`
  tells you if a hard word slipped in, and the unit tests run it on every page.
- A change to a chart or a table changes generated files. Run `python3 bench/publish.py` and commit
  what it writes.

The name and meaning of every field in a row are in [results/README.md](results/README.md).
