# Speed: how long does a Mac make you wait?

TODO(stage B): page text

<!-- BEGIN GENERATED: speed m3-ultra-a -->
### Mac A (Qwen 27B)

The wait for the first word, in seconds. The second figure is how many times shorter the wait is than on the Mac alone.

| Setup | 8K | 32K | 64K | 128K |
|---|---:|---:|---:|---:|
| Mac alone | 24.5 s | 109.8 s | 252.8 s (4.2 min) | 638.1 s (10.6 min) |
| + ANE (Apple chip) | 18.8 s · 1.3× | 87.2 s · 1.3× | 207.5 s (3.5 min) · 1.2× | 548.3 s (9.1 min) · 1.2× |
| + Spark helper | 8.6 s · 2.8× | 35.1 s · 3.1× | 76.9 s · 3.3× | 189.8 s (3.2 min) · 3.4× |
| + ANE + Spark helper | 7.8 s · 3.1× | 29.6 s · 3.7× | 66.4 s · 3.8× | 166.1 s (2.8 min) · 3.8× |

Reading the prompt, in tokens per second:

| Setup | 8K | 32K | 64K | 128K |
|---|---:|---:|---:|---:|
| Mac alone | 335 | 298 | 259 | 205 |
| + ANE (Apple chip) | 435 | 376 | 316 | 239 |
| + Spark helper | 955 | 933 | 852 | 691 |
| + ANE + Spark helper | 1,052 | 1,106 | 987 | 789 |

- Each figure is the mean of 3 valid runs. Every run read its prompt with a cold cache (0 cached tokens).
- Run-to-run spread of reading speed is at most 2.9% everywhere except + Spark helper at 8K (7.5%), + Spark helper at 32K (4.3%).
- Run again back to back, 3 runs each: + Spark helper at 8K: 1,004 tokens/s (955 in the first pass), + Spark helper at 32K: 1,094 tokens/s (933 in the first pass).
<!-- END GENERATED: speed m3-ultra-a -->

<!-- BEGIN GENERATED: speed m3-ultra-b -->
### Mac B (Flash-Next)

The wait for the first word, in seconds. The second figure is how many times shorter the wait is than on the Mac alone.

| Setup | 8K | 32K | 64K | 128K |
|---|---:|---:|---:|---:|
| Mac alone | 8.5 s | 33.3 s | 68.0 s | 137.2 s (2.3 min) |
| + Spark helper | 6.1 s · 1.4× | 16.1 s · 2.1× | 30.0 s · 2.3× | 58.8 s · 2.3× |

Reading the prompt, in tokens per second:

| Setup | 8K | 32K | 64K | 128K |
|---|---:|---:|---:|---:|
| Mac alone | 966 | 983 | 963 | 955 |
| + Spark helper | 1,353 | 2,030 | 2,185 | 2,230 |

- Each figure is the mean of 3 valid runs. Every run read its prompt with a cold cache (0 cached tokens).
- Run-to-run spread of reading speed is at most 2.9% everywhere except + Spark helper at 32K (4.1%).
<!-- END GENERATED: speed m3-ultra-b -->

<!-- BEGIN GENERATED: speed-sweep m3-ultra-b -->
### Mac B (Flash-Next)

The wait for the first word at each prompt size, and how many times shorter it is with the helper.

| Prompt size | Mac alone | + Spark helper | Faster by |
|---|---:|---:|---:|
| 1K | 1.7 s | 1.5 s | 1.1× |
| 4K | 5.8 s | 4.2 s | 1.4× |
| 8K | 8.7 s | 6.0 s | 1.5× |
| 16K | 16.6 s | 9.5 s | 1.8× |
| 32K | 33.4 s | 15.9 s | 2.1× |
| 64K | 67.8 s | 30.5 s | 2.2× |
| 128K | 137.1 s (2.3 min) | 58.4 s | 2.3× |

- Each figure is the mean of 2 valid runs. Every run read its prompt with a cold cache (0 cached tokens).
<!-- END GENERATED: speed-sweep m3-ultra-b -->
