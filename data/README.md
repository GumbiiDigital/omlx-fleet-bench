# Quality data

Two fixed files, used by `matrices/quality.json`. Both are subsets of public datasets, kept small so
that the repository stays light and a run can be repeated.

## `gsm8k-200.jsonl`

- 200 of the 1,319 questions in the GSM8K test split, taken at even spacing.
- `id` is `gsm8k-<source index>`, and `source_index` is the line number in the source test file.
- `answer` keeps the GSM8K format: a worked solution ending with `#### <number>`. Only the final
  number is scored.
- Source: [openai/grade-school-math](https://github.com/openai/grade-school-math), license MIT.

## `mmlu-500.jsonl`

- 500 questions: the first 25 test rows of 20 MMLU subjects (listed in
  `scripts/fetch_quality_data.py`).
- Fields: `id`, `subject`, `question`, `choices` (4 strings), `answer` (a number from 0 to 3 that
  picks one of `choices`).
- Source: [cais/mmlu](https://huggingface.co/datasets/cais/mmlu), license MIT, read through the
  Hugging Face datasets-server JSON API.

## Rebuilding

```bash
python3 scripts/fetch_quality_data.py
# a Python build with no certificate store needs:
python3 scripts/fetch_quality_data.py --ca-bundle /etc/ssl/cert.pem
```

The script is deterministic: the same inputs give the same files.

## Limits

- These are subsets. GSM8K accuracy on 200 questions has a sampling error of roughly ±3 points at
  90% confidence; MMLU on 500 has roughly ±4 points. Compare settings inside one run, not against
  published full-test scores.
- The full MMLU test split has a different mix of subjects, so this 20-subject subset is easier than
  the full 14,042-question test.

Back to [the front page](../README.md).
