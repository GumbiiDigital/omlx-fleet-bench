# KV cache: every cell

Valid runs only. Prefill speed and time to first token are mean/min/max; spread is
(max - min) / mean of prefill speed. Peak memory is MLX active memory for the run.

| Machine | Model | Variant | Prompt tokens | Valid runs | Prefill tok/s | Time to first token ms | Spread % | Peak memory GB | Flags |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | native | 32768 | 3/3 | 979.3/977.7/982.2 | 33464.2/33364.1/33517.7 | 0.5 | 105.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | affine4 | 32768 | 3/3 | 974.9/967.8/982.1 | 33613.5/33366.2/33861.0 | 1.5 | 105.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | affine8 | 32768 | 3/3 | 976.3/974.0/980.5 | 33566.8/33422.4/33644.3 | 0.7 | 105.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | native | 131072 | 3/3 | 951.5/950.0/953.1 | 137748.3/137528.1/137966.8 | 0.3 | 108.5 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | affine4 | 131072 | 3/3 | 952.9/952.1/953.3 | 137553.5/137497.5/137661.1 | 0.1 | 108.5 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | affine8 | 131072 | 3/3 | 950.6/947.8/952.8 | 137883.0/137569.9/138296.6 | 0.5 | 108.5 | - |
