# Helper-ready replay: every request

One line per request, in the order the rows were written. Time to first token is the
server's own figure. A request whose row failed a check stays in the list and names it.

| Path | Arm | Prompt | Setting | Helper | State at start | Waited s | Time to first token s | Layers | Cached tokens | Answer correct | Failed checks |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.67 | none | 0 | yes | - |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.70 | 49 | 0 | yes | - |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.74 | 49 | 0 | yes | - |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.15 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.75 | 49 | 0 | yes | - |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.74 | 49 | 0 | yes | - |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.13 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.73 | 49 | 0 | yes | - |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.76 | 49 | 0 | yes | - |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.2 | 29.31 | 49 | 0 | yes | - |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.1 | 29.93 | 49 | 0 | yes | - |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.13 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.1 | 29.81 | 49 | 0 | yes | - |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.2 | 29.62 | 49 | 0 | yes | - |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.13 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.1 | 29.65 | 49 | 0 | yes | - |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.1 | 29.73 | 49 | 0 | yes | - |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.52 | none | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.89 | none | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.67 | none | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.23 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.98 | none | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.23 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 30.04 | none | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.17 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.71 | none | 0 | - | helper_ready_at_start |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 16.1 | 30.14 | none | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 18.1 | 30.17 | none | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 18.1 | 29.89 | none | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 16.1 | 29.88 | none | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 18.1 | 29.97 | none | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.23 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 18.1 | 29.87 | none | 0 | - | - |
