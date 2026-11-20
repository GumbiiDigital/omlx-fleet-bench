# Memory: what the KV cache costs

TODO(stage B): page text

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
