# Mac A (Qwen 27B): every KV cache row

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
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | Native KV cache | 32768 | 3/3 | 298.3/298.2/298.3 | 109864.5/109849.6/109882.7 | 0.0 | 21.5 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | Affine4 KV cache | 32768 | 3/3 | 300.5/300.4/300.6 | 109049.5/108997.4/109100.7 | 0.1 | 19.6 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | Affine8 KV cache | 32768 | 3/3 | 300.6/300.6/300.7 | 109002.7/108977.7/109029.0 | 0.0 | 20.1 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | Native KV cache | 131072 | 3/3 | 205.4/205.4/205.4 | 638153.6/638092.0/638197.8 | 0.0 | 29.1 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | Affine4 KV cache | 131072 | 3/3 | 211.1/211.0/211.1 | 620965.9/620840.9/621172.9 | 0.0 | 21.9 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | Affine8 KV cache | 131072 | 3/3 | 210.9/210.9/211.0 | 621366.5/621257.4/621476.0 | 0.0 | 23.9 | - |
