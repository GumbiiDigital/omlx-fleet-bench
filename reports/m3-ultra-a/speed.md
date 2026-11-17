# Speed: every cell

Valid runs only. Prefill speed and time to first token are mean/min/max; spread is
(max - min) / mean of prefill speed. Peak memory is MLX active memory for the run.

| Machine | Model | Variant | Prompt tokens | Valid runs | Prefill tok/s | Time to first token ms | Spread % | Peak memory GB | Flags |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | gpu | 8192 | 3/3 | 334.8/334.6/335.3 | 24470.4/24434.2/24489.3 | 0.2 | 19.6 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | ane | 8192 | 3/3 | 435.1/434.9/435.3 | 18831.8/18820.1/18839.4 | 0.1 | 19.5 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | spark | 8192 | 3/3 | 955.0/913.7/985.8 | 8587.4/8310.9/8966.4 | 7.5 | 18.4 | noisy |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | ane_spark | 8192 | 3/3 | 1051.8/1039.7/1060.4 | 7790.4/7726.3/7880.1 | 2.0 | 18.3 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | gpu | 32768 | 3/3 | 298.3/298.3/298.4 | 109848.3/109833.8/109859.1 | 0.0 | 21.5 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | ane | 32768 | 3/3 | 376.0/375.7/376.1 | 87164.4/87134.0/87224.9 | 0.1 | 21.4 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | spark | 32768 | 3/3 | 933.4/919.7/960.3 | 35121.8/34123.6/35631.7 | 4.3 | 20.3 | noisy |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | ane_spark | 32768 | 3/3 | 1106.1/1098.3/1111.8 | 29625.5/29474.2/29835.4 | 1.2 | 20.2 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | gpu | 65536 | 3/3 | 259.3/259.2/259.3 | 252753.5/252706.4/252822.9 | 0.0 | 24.0 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | ane | 65536 | 3/3 | 315.8/315.6/316.0 | 207533.0/207414.4/207657.2 | 0.1 | 23.9 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | spark | 65536 | 3/3 | 852.0/851.6/852.4 | 76925.2/76884.4/76958.3 | 0.1 | 22.7 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | ane_spark | 65536 | 3/3 | 987.3/982.8/991.8 | 66380.7/66081.3/66684.1 | 0.9 | 22.6 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | gpu | 131072 | 3/3 | 205.4/205.4/205.4 | 638117.9/638087.0/638174.8 | 0.0 | 29.1 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | ane | 131072 | 3/3 | 239.0/239.0/239.1 | 548347.3/548158.7/548492.8 | 0.0 | 28.8 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | spark | 131072 | 3/3 | 690.8/677.5/697.6 | 189778.5/187888.7/193468.1 | 2.9 | 27.6 | - |
| m3-ultra-a | Qwen3.8-27B-oQ4e-mtp | ane_spark | 131072 | 3/3 | 789.2/784.3/797.9 | 166093.2/164277.3/167114.1 | 1.7 | 27.5 | - |
