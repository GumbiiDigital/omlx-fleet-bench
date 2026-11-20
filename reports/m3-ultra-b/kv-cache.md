# Mac B (Flash-Next): every KV cache row

What each column means:

- **Machine**: the machine name written in the results file.
- **Model**: the model the server was running.
- **Setup**: the server setting this row was run under.
- **Prompt size (tokens)**: how long the prompt was, in tokens (8K = 8,192).
- **Valid runs**: runs that passed every check, out of the runs planned.
- **Reading the prompt (tokens/s)**: mean, smallest and largest of the valid runs.
- **Wait for the first word (ms)**: mean, smallest and largest of the valid runs, in milliseconds.
- **Spread (%)**: (largest - smallest) / mean of the reading speed, in percent.
- **Peak memory (GB)**: peak memory of the whole run, in bytes / 2^30.
- **Flags**: `noisy` when the spread is over 3%; `incomplete` when a planned run is missing.

| Machine | Model | Setup | Prompt size (tokens) | Valid runs | Reading the prompt (tokens/s) | Wait for the first word (ms) | Spread (%) | Peak memory (GB) | Flags |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Native KV cache | 32768 | 3/3 | 979.3/977.7/982.2 | 33464.2/33364.1/33517.7 | 0.5 | 105.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Affine4 KV cache | 32768 | 3/3 | 974.9/967.8/982.1 | 33613.5/33366.2/33861.0 | 1.5 | 105.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Affine8 KV cache | 32768 | 3/3 | 976.3/974.0/980.5 | 33566.8/33422.4/33644.3 | 0.7 | 105.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Native KV cache | 131072 | 3/3 | 951.5/950.0/953.1 | 137748.3/137528.1/137966.8 | 0.3 | 108.5 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Affine4 KV cache | 131072 | 3/3 | 952.9/952.1/953.3 | 137553.5/137497.5/137661.1 | 0.1 | 108.5 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Affine8 KV cache | 131072 | 3/3 | 950.6/947.8/952.8 | 137883.0/137569.9/138296.6 | 0.5 | 108.5 | - |
