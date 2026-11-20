# Mac B (Flash-Next): every speed row

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
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Mac alone | 8192 | 3/3 | 966.1/949.6/976.4 | 8481.6/8391.1/8628.3 | 2.8 | 104.3 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | + Spark helper | 8192 | 3/3 | 1353.0/1338.7/1377.4 | 6056.4/5948.3/6120.1 | 2.9 | 104.2 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Mac alone | 32768 | 3/3 | 983.4/982.2/985.2 | 33323.9/33262.8/33364.4 | 0.3 | 105.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | + Spark helper | 32768 | 3/3 | 2029.7/1980.1/2062.6 | 16149.7/15887.2/16549.0 | 4.1 | 105.0 | noisy |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Mac alone | 65536 | 3/3 | 963.5/961.6/965.4 | 68021.8/67887.8/68151.4 | 0.4 | 106.2 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | + Spark helper | 65536 | 3/3 | 2185.5/2164.5/2200.8 | 29989.2/29778.5/30278.5 | 1.7 | 106.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | Mac alone | 131072 | 3/3 | 955.4/954.5/956.3 | 137193.8/137062.5/137328.1 | 0.2 | 108.5 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | + Spark helper | 131072 | 3/3 | 2230.5/2222.3/2235.5 | 58765.1/58631.8/58980.0 | 0.6 | 108.4 | - |
