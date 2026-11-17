# Prompt-size sweep: every cell

Valid runs only. Prefill speed and time to first token are mean/min/max; spread is
(max - min) / mean of prefill speed. Peak memory is MLX active memory for the run.

| Machine | Model | Variant | Prompt tokens | Valid runs | Prefill tok/s | Time to first token ms | Spread % | Peak memory GB | Flags |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | gpu | 1024 | 2/2 | 624.8/557.6/691.9 | 1659.9/1481.5/1838.3 | 21.5 | 103.1 | noisy |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | spark | 1024 | 2/2 | 672.0/632.0/711.9 | 1530.9/1439.9/1621.9 | 11.9 | 103.1 | noisy |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | gpu | 4096 | 2/2 | 759.2/548.4/970.1 | 5847.0/4223.3/7470.7 | 55.5 | 103.8 | noisy |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | spark | 4096 | 2/2 | 983.9/962.6/1005.2 | 4166.0/4075.9/4256.1 | 4.3 | 103.5 | noisy |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | gpu | 8192 | 2/2 | 937.5/919.4/955.7 | 8742.0/8572.9/8911.0 | 3.9 | 104.3 | noisy |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | spark | 8192 | 2/2 | 1367.3/1365.8/1368.8 | 5992.0/5985.5/5998.5 | 0.2 | 104.2 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | gpu | 16384 | 2/2 | 984.8/983.6/986.0 | 16637.8/16618.2/16657.5 | 0.2 | 104.5 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | spark | 16384 | 2/2 | 1733.7/1722.9/1744.4 | 9451.7/9393.1/9510.3 | 1.2 | 104.5 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | gpu | 32768 | 2/2 | 980.5/977.0/984.1 | 33419.9/33297.9/33541.8 | 0.7 | 105.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | spark | 32768 | 2/2 | 2064.7/2060.0/2069.3 | 15871.5/15835.9/15907.1 | 0.5 | 105.0 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | gpu | 65536 | 2/2 | 967.0/964.7/969.2 | 67779.3/67622.1/67936.5 | 0.5 | 106.2 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | spark | 65536 | 2/2 | 2149.6/2134.0/2165.1 | 30490.4/30269.3/30711.6 | 1.4 | 106.1 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | gpu | 131072 | 2/2 | 956.4/955.8/957.0 | 137051.3/136966.8/137135.9 | 0.1 | 108.5 | - |
| m3-ultra-b | Qwen3.8-Flash-Next-oQ4e-mtp | spark | 131072 | 2/2 | 2244.8/2241.8/2247.8 | 58390.1/58312.6/58467.7 | 0.3 | 108.4 | - |
