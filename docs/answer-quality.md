# Answer quality: does the Spark change the answers?

Question: do the settings and the Spark change what the model answers?

Short answer: not in a way these 700 questions can see. On Mac B every answer came out the same under
all four settings. On Mac A 10 or 11 of 700 answers changed between runs even where the add-on did no
work, so a change that size is run-to-run noise, not an effect.

## The questions

700 questions, asked the same way under every setting, at temperature 0: 200 from GSM8K, 500 from
MMLU (25 from each of 20 subjects), and 6 passkey prompts (a 7-digit number planted halfway into 32K,
64K and 128K tokens of filler). Mac A made 3,530 requests and Mac B 2,824, with 0 errors.

<!-- BEGIN GENERATED: quality m3-ultra-a -->
### Mac A (Qwen 27B)

Answers right, per question set and setting. The second figure in a row is the share right.

| Setting | GSM8K (of 200) | MMLU (of 500) | Passkey (of 6) | Answers changed against Mac alone |
|---|---:|---:|---:|---:|
| Mac alone | 195 · 97.5% | 454 · 90.8% | 6 | baseline |
| Affine4 KV cache | 196 · 98.0% | 459 · 91.8% | 6 | 7 lost, 13 gained (of 700) |
| Affine8 KV cache | 195 · 97.5% | 458 · 91.6% | 6 | 2 lost, 6 gained (of 700) |
| + ANE (Apple chip) | 195 · 97.5% | 456 · 91.2% | 6 | 4 lost, 6 gained (of 700) |
| + Spark helper | 195 · 97.5% | 459 · 91.8% | 6 | 3 lost, 8 gained (of 700) |

- Answers that ran out of tokens while the model was still thinking, and count as wrong: Mac alone 16, Affine4 KV cache 17, Affine8 KV cache 12, + ANE (Apple chip) 17, + Spark helper 12 (74 in all).
- Every question was asked under every setting, at temperature 0, so the same question gets the same answer twice.
<!-- END GENERATED: quality m3-ultra-a -->

<!-- BEGIN GENERATED: quality m3-ultra-b -->
### Mac B (Flash-Next)

Answers right, per question set and setting. The second figure in a row is the share right.

| Setting | GSM8K (of 200) | MMLU (of 500) | Passkey (of 6) | Answers changed against Mac alone |
|---|---:|---:|---:|---:|
| Mac alone | 194 · 97.0% | 433 · 86.6% | 6 | baseline |
| Affine4 KV cache | 194 · 97.0% | 433 · 86.6% | 6 | 0 lost, 0 gained (of 700) |
| Affine8 KV cache | 194 · 97.0% | 433 · 86.6% | 6 | 0 lost, 0 gained (of 700) |
| + Spark helper | 194 · 97.0% | 433 · 86.6% | 6 | 0 lost, 0 gained (of 700) |

- Answers that ran out of tokens while the model was still thinking, and count as wrong: Mac alone 57, Affine4 KV cache 57, Affine8 KV cache 57, + Spark helper 57 (228 in all).
- Every question was asked under every setting, at temperature 0, so the same question gets the same answer twice.
<!-- END GENERATED: quality m3-ultra-b -->

## What this means

- Affine4 and Affine8 are really tested: the compression acts on every request, so all 700 questions
  exercise it. Neither scheme lowered accuracy.
- The Apple chip and the Spark are tested only by the 6 passkey prompts. The GSM8K and MMLU prompts
  are about 150 tokens, too short for either add-on to do work on, so those rows say "no work here",
  not "safe on short prompts".
- The Spark answered all 6 passkey prompts right, at 32K, 64K and 128K tokens.
- Affine8 sits inside that noise. Affine4 flipped about twice as many answers, in both directions
  (7 lost, 13 gained), so read its row as unchanged rather than as a gain.

## Limits

- The 95% interval is about ±2 to ±3 points. A setting that costs one point of accuracy would not show.
- The 20-subject MMLU subset is easier than the full test, so compare settings inside one table, not
  against published scores.
- 304 answers on Mac A ran out of tokens while the model was still thinking. They were asked again
  with a cap 8 times larger; the ones still cut off count as wrong. On Mac B 57 answers per setting
  were cut off and not asked again, so the Mac B MMLU figure is a floor.
- The passkey numbers come from a second run on 2026-11-17, with a unique first line in every prompt
  so that each was read cold. All 30 rows on Mac A and all 24 on Mac B read 0 cached tokens, and
  every answer was right.
- In the first passkey pass the first request with the helper at 32K took 109.7 s, and the next took
  30.9 s. That fault has a proven cause and a fix in the runner; see [helper start-up](helper-setup.md).

Full tables: [Mac A](../reports/m3-ultra-a/quality.md) and [Mac B](../reports/m3-ultra-b/quality.md).
Back to [the front page](../README.md).
