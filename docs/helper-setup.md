# Helper start-up and how many layers it holds

TODO(stage B): page text

<!-- BEGIN GENERATED: helper-ready m3-ultra-a -->
### Mac A (Qwen 27B)

The wait for the first word of a request at 32K with the helper on, sent straight after a switch from helper off to helper on. One line per path and per way of starting.

| Path | Round | Waited for the helper (s) | Wait for the first word (s) | Ran at helper speed |
|---|---:|---:|---:|---:|
| chat | Started at once | 0.0 | 109.70 to 109.76 s | 0 of 6 |
| chat | Waited for the helper | 20.1 | 29.31 to 29.93 s | 6 of 6 |
| speed test | Started at once | 0.0 | 29.52 to 30.04 s | 6 of 6 |
| speed test | Waited for the helper | 17.5 | 29.87 to 30.17 s | 6 of 6 |

- 6 requests in every line of the table. Each round is one request with the helper off and then one at 32K with the helper on, so every helper request starts straight after a switch.
- The helper state at the start of the request: chat, Started at once: connecting (6 of 6); chat, Waited for the helper: ready (6 of 6); speed test, Started at once: starting (6 of 6); speed test, Waited for the helper: ready (6 of 6).
- 6 requests in speed test / Started at once are marked not valid by `helper_ready_at_start`: they began at helper state starting (6 of 6) and ran at helper speed (29.52 to 30.04 s).
- Every request read its prompt cold; 12 of 12 answers were correct.
<!-- END GENERATED: helper-ready m3-ultra-a -->

<!-- BEGIN GENERATED: helper-layers m3-ultra-a -->
### Mac A (Qwen 27B)

The wait for the first word per helper layer count, and how many times faster than the Mac alone at 32K. A layer is a slice of the model the helper holds.

| Setting | 32K wait for the first word | 128K wait for the first word | Layers on the helper | Faster than the Mac alone at 32K |
|---|---:|---:|---:|---:|
| Mac alone | 109.7 s, 109.69 to 109.72 s | not run | none | baseline |
| Automatic | 32.1 s, 29.42 to 33.62 s | 178.7 s (3.0 min), 177.96 to 179.42 s | 32K: 49; 128K: 50, 49, 49 | 3.4× |
| 32 layers | 56.8 s, 56.77 to 56.91 s | 321.6 s (5.4 min), 321.54 to 321.69 s | 32 | 1.9× |
| 49 layers | 29.8 s, 29.50 to 29.91 s | 166.0 s (2.8 min), 165.71 to 166.40 s | 49 | 3.7× |
| 63 layers | 35.9 s, 35.43 to 36.23 s | 208.2 s (3.5 min), 207.43 to 209.25 s | 63 | 3.1× |

- Each figure is the mean of 3 requests, with the smallest and largest after it.
- All 27 requests read their prompt cold and got a correct answer.
<!-- END GENERATED: helper-layers m3-ultra-a -->
