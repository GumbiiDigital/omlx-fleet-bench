# Mac A (Qwen 27B): helper start, every request

One line per request, in the order the rows were written. A request whose row failed a
check stays in the list and names it.

What each column means:

- **Path**: how the request was sent: `chat` is the chat API, `speed test` the server's own test call.
- **Round**: the name of the round this request belongs to, as the study file names it.
- **Prompt size**: how long the prompt was (32K = 32,768 tokens).
- **Setting**: which helper layer setting the request ran under.
- **Helper**: whether the DGX Spark helper was on for this request.
- **State at start**: the helper state the request found when it was sent.
- **Waited for the helper (s)**: seconds the run waited for the helper to be ready first.
- **Wait for the first word (s)**: the server's own figure for this request.
- **Layers on the helper**: how many model layers the helper held for this request.
- **Cached tokens**: prompt tokens the server already had in memory (0 means it read the whole prompt).
- **Answer correct**: whether the answer passed its check; `-` when the row records no answer.
- **Failed checks**: the checks this row failed, or `-` when it passed every one.

A speed row carries a validity block; a chat row carries none, so its cold-cache and
answer checks are read from its own fields, and a chat row with nothing to report says
`no validity marks`.

| Path | Round | Prompt size | Setting | Helper | State at start | Waited for the helper (s) | Wait for the first word (s) | Layers on the helper | Cached tokens | Answer correct | Failed checks |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.67 | none | 0 | yes | no validity marks |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.70 | 49 | 0 | yes | no validity marks |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.74 | 49 | 0 | yes | no validity marks |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.15 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.75 | 49 | 0 | yes | no validity marks |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.74 | 49 | 0 | yes | no validity marks |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.13 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.73 | 49 | 0 | yes | no validity marks |
| chat | no wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.76 | 49 | 0 | yes | no validity marks |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.2 | 29.31 | 49 | 0 | yes | no validity marks |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.1 | 29.93 | 49 | 0 | yes | no validity marks |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.13 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.1 | 29.81 | 49 | 0 | yes | no validity marks |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.2 | 29.62 | 49 | 0 | yes | no validity marks |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.13 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.1 | 29.65 | 49 | 0 | yes | no validity marks |
| chat | wait | 145 | Mac alone | off | none | 0.0 | 0.14 | none | 140 | yes | cached_tokens_zero |
| chat | wait | 32K | Automatic | on | ready | 20.1 | 29.73 | 49 | 0 | yes | no validity marks |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.52 | not recorded | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.89 | not recorded | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.67 | not recorded | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.23 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.98 | not recorded | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.23 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 30.04 | not recorded | 0 | - | helper_ready_at_start |
| speed test | no wait | 1K | Mac alone | off | none | 0.0 | 3.17 | none | 0 | - | - |
| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 29.71 | not recorded | 0 | - | helper_ready_at_start |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 16.1 | 30.14 | not recorded | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 18.1 | 30.17 | not recorded | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 18.1 | 29.89 | not recorded | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 16.1 | 29.88 | not recorded | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.22 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 18.1 | 29.97 | not recorded | 0 | - | - |
| speed test | wait | 1K | Mac alone | off | none | 0.0 | 3.23 | none | 0 | - | - |
| speed test | wait | 32K | Automatic | on | ready | 18.1 | 29.87 | not recorded | 0 | - | - |
