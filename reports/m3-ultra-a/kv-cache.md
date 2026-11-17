# KV cache: every cell

Valid runs only. Prefill speed and time to first token are mean/min/max; spread is
(max - min) / mean of prefill speed. Peak memory is MLX active memory for the run.

| Machine | Model | Variant | Prompt tokens | Valid runs | Prefill tok/s | Time to first token ms | Spread % | Peak memory GB | Flags |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | native | 32768 | 3/3 | 298.3/298.2/298.3 | 109864.5/109849.6/109882.7 | 0.0 | 21.5 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | affine4 | 32768 | 3/3 | 300.5/300.4/300.6 | 109049.5/108997.4/109100.7 | 0.1 | 19.6 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | affine8 | 32768 | 3/3 | 300.6/300.6/300.7 | 109002.7/108977.7/109029.0 | 0.0 | 20.1 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | native | 131072 | 3/3 | 205.4/205.4/205.4 | 638153.6/638092.0/638197.8 | 0.0 | 29.1 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | affine4 | 131072 | 3/3 | 211.1/211.0/211.1 | 620965.9/620840.9/621172.9 | 0.0 | 21.9 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | affine8 | 131072 | 3/3 | 210.9/210.9/211.0 | 621366.5/621257.4/621476.0 | 0.0 | 23.9 | - |
