# Memory: what the KV cache costs

Question: does a smaller KV cache (the memory that holds the prompt) save memory, and what does it cost in speed?

Short answer: on Mac A the Affine4 KV cache saves 24.6% of peak memory at 128K tokens and costs no
speed. On Mac B neither scheme moved memory or speed in a way this test can see.

<!-- BEGIN GENERATED: kv-cache m3-ultra-a -->
### Mac A (Qwen 27B)

The KV cache is the memory that holds the prompt. The second figure in a row is the change against Native KV cache.

| KV cache | 32K peak memory | 32K wait for the first word | 128K peak memory | 128K wait for the first word |
|---|---:|---:|---:|---:|
| Native KV cache | 21.5 GB | 109.9 s | 29.1 GB | 638.2 s (10.6 min) |
| Affine4 KV cache | 19.6 GB · −8.6% | 109.0 s · −0.7% | 21.9 GB · −24.6% | 621.0 s (10.3 min) · −2.7% |
| Affine8 KV cache | 20.1 GB · −6.3% | 109.0 s · −0.8% | 23.9 GB · −17.7% | 621.4 s (10.4 min) · −2.6% |

- Peak memory is the most memory the whole run used, not the size of the KV cache alone.
- Each figure is the mean of 3 valid runs. Run-to-run spread of reading speed is at most 0.07% everywhere.
<!-- END GENERATED: kv-cache m3-ultra-a -->

<!-- BEGIN GENERATED: kv-cache m3-ultra-b -->
### Mac B (Flash-Next)

The KV cache is the memory that holds the prompt. The second figure in a row is the change against Native KV cache.

| KV cache | 32K peak memory | 32K wait for the first word | 128K peak memory | 128K wait for the first word |
|---|---:|---:|---:|---:|
| Native KV cache | 105.1 GB | 33.5 s | 108.5 GB | 137.7 s (2.3 min) |
| Affine4 KV cache | 105.1 GB · +0.0% | 33.6 s · +0.4% | 108.5 GB · −0.0% | 137.6 s (2.3 min) · −0.1% |
| Affine8 KV cache | 105.1 GB · +0.0% | 33.6 s · +0.3% | 108.5 GB · −0.0% | 137.9 s (2.3 min) · +0.1% |

- Peak memory is the most memory the whole run used, not the size of the KV cache alone.
- Each figure is the mean of 3 valid runs. Run-to-run spread of reading speed is at most 1.47% everywhere.
<!-- END GENERATED: kv-cache m3-ultra-b -->

## What this means

- On Mac A, Affine4 is the better of the two schemes: less memory at both sizes, and the same speed.
- Affine8 saves less memory than Affine4 on that Mac, and equals it on speed.
- On Mac B neither scheme changed peak memory (105.1 GB at 32K, 108.5 GB at 128K) or the wait.
- The memory figure is the peak of the whole run, not the size of the KV cache, so no KV cache size is
  claimed here.

## One thing not explained

On Mac A both schemes convert 16 of the model's 64 cache layers, and each row records it. On Mac B no
row records a conversion, though the server accepted the setting. From these rows it is not possible
to say whether that model does not convert or the server log does not show it.

Full tables: [Mac A](../reports/m3-ultra-a/kv-cache.md) and [Mac B](../reports/m3-ultra-b/kv-cache.md).
Back to [the front page](../README.md).
