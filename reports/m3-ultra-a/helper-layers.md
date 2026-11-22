# Mac A (Qwen 27B): helper layer count, every request

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

These rows carry no validity block: their cold-cache and answer checks are read from their
own fields, and a row with nothing to report says `no validity marks`.

| Path | Round | Prompt size | Setting | Helper | State at start | Waited for the helper (s) | Wait for the first word (s) | Layers on the helper | Cached tokens | Answer correct | Failed checks |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| chat | wait | 32K | Mac alone | off | none | 0.0 | 109.71 | none | 0 | yes | no validity marks |
| chat | wait | 32K | Automatic | on | ready | 18.1 | 29.42 | 49 | 0 | yes | no validity marks |
| chat | wait | 32K | 32 layers | on | ready | 14.1 | 56.80 | 32 | 0 | yes | no validity marks |
| chat | wait | 32K | 49 layers | on | ready | 30.2 | 29.91 | 49 | 0 | yes | no validity marks |
| chat | wait | 32K | 63 layers | on | ready | 34.3 | 35.43 | 63 | 0 | yes | no validity marks |
| chat | wait | 128K | Automatic | on | ready | 20.2 | 177.96 | 50 | 0 | yes | no validity marks |
| chat | wait | 128K | 32 layers | on | ready | 12.1 | 321.54 | 32 | 0 | yes | no validity marks |
| chat | wait | 128K | 49 layers | on | ready | 32.2 | 166.40 | 49 | 0 | yes | no validity marks |
| chat | wait | 128K | 63 layers | on | ready | 34.3 | 209.25 | 63 | 0 | yes | no validity marks |
| chat | wait | 32K | Mac alone | off | none | 0.0 | 109.69 | none | 0 | yes | no validity marks |
| chat | wait | 32K | Automatic | on | ready | 18.1 | 33.62 | 49 | 0 | yes | no validity marks |
| chat | wait | 32K | 32 layers | on | ready | 14.1 | 56.77 | 32 | 0 | yes | no validity marks |
| chat | wait | 32K | 49 layers | on | ready | 28.3 | 29.84 | 49 | 0 | yes | no validity marks |
| chat | wait | 32K | 63 layers | on | ready | 32.3 | 36.23 | 63 | 0 | yes | no validity marks |
| chat | wait | 128K | Automatic | on | ready | 20.2 | 178.61 | 49 | 0 | yes | no validity marks |
| chat | wait | 128K | 32 layers | on | ready | 12.1 | 321.68 | 32 | 0 | yes | no validity marks |
| chat | wait | 128K | 49 layers | on | ready | 32.2 | 165.71 | 49 | 0 | yes | no validity marks |
| chat | wait | 128K | 63 layers | on | ready | 30.2 | 207.43 | 63 | 0 | yes | no validity marks |
| chat | wait | 32K | Mac alone | off | none | 0.0 | 109.72 | none | 0 | yes | no validity marks |
| chat | wait | 32K | Automatic | on | ready | 20.2 | 33.24 | 49 | 0 | yes | no validity marks |
| chat | wait | 32K | 32 layers | on | ready | 14.1 | 56.91 | 32 | 0 | yes | no validity marks |
| chat | wait | 32K | 49 layers | on | ready | 30.2 | 29.50 | 49 | 0 | yes | no validity marks |
| chat | wait | 32K | 63 layers | on | ready | 34.3 | 36.16 | 63 | 0 | yes | no validity marks |
| chat | wait | 128K | Automatic | on | ready | 18.1 | 179.42 | 49 | 0 | yes | no validity marks |
| chat | wait | 128K | 32 layers | on | ready | 14.1 | 321.69 | 32 | 0 | yes | no validity marks |
| chat | wait | 128K | 49 layers | on | ready | 30.2 | 165.98 | 49 | 0 | yes | no validity marks |
| chat | wait | 128K | 63 layers | on | ready | 36.3 | 207.98 | 63 | 0 | yes | no validity marks |
