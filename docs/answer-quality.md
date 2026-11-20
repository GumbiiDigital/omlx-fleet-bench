# Answer quality: does the helper change the answers?

TODO(stage B): page text

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
