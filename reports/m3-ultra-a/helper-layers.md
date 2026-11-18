# Helper layer count: every request

One line per request, in the order the rows were written. Time to first token is the
server's own figure. A request whose row failed a check stays in the list and names it.

| Path | Arm | Prompt | Setting | Helper | State at start | Waited s | Time to first token s | Layers | Cached tokens | Answer correct | Failed checks |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| chat | wait | 32K | Mac alone | off | none | 0.0 | 109.71 | none | 0 | yes | - |
| chat | wait | 32K | Automatic | on | ready | 18.1 | 29.42 | 49 | 0 | yes | - |
| chat | wait | 32K | 32 layers | on | ready | 14.1 | 56.80 | 32 | 0 | yes | - |
| chat | wait | 32K | 49 layers | on | ready | 30.2 | 29.91 | 49 | 0 | yes | - |
| chat | wait | 32K | 63 layers | on | ready | 34.3 | 35.43 | 63 | 0 | yes | - |
| chat | wait | 128K | Automatic | on | ready | 20.2 | 177.96 | 50 | 0 | yes | - |
| chat | wait | 128K | 32 layers | on | ready | 12.1 | 321.54 | 32 | 0 | yes | - |
| chat | wait | 128K | 49 layers | on | ready | 32.2 | 166.40 | 49 | 0 | yes | - |
| chat | wait | 128K | 63 layers | on | ready | 34.3 | 209.25 | 63 | 0 | yes | - |
| chat | wait | 32K | Mac alone | off | none | 0.0 | 109.69 | none | 0 | yes | - |
| chat | wait | 32K | Automatic | on | ready | 18.1 | 33.62 | 49 | 0 | yes | - |
| chat | wait | 32K | 32 layers | on | ready | 14.1 | 56.77 | 32 | 0 | yes | - |
| chat | wait | 32K | 49 layers | on | ready | 28.3 | 29.84 | 49 | 0 | yes | - |
| chat | wait | 32K | 63 layers | on | ready | 32.3 | 36.23 | 63 | 0 | yes | - |
| chat | wait | 128K | Automatic | on | ready | 20.2 | 178.61 | 49 | 0 | yes | - |
| chat | wait | 128K | 32 layers | on | ready | 12.1 | 321.68 | 32 | 0 | yes | - |
| chat | wait | 128K | 49 layers | on | ready | 32.2 | 165.71 | 49 | 0 | yes | - |
| chat | wait | 128K | 63 layers | on | ready | 30.2 | 207.43 | 63 | 0 | yes | - |
| chat | wait | 32K | Mac alone | off | none | 0.0 | 109.72 | none | 0 | yes | - |
| chat | wait | 32K | Automatic | on | ready | 20.2 | 33.24 | 49 | 0 | yes | - |
| chat | wait | 32K | 32 layers | on | ready | 14.1 | 56.91 | 32 | 0 | yes | - |
| chat | wait | 32K | 49 layers | on | ready | 30.2 | 29.50 | 49 | 0 | yes | - |
| chat | wait | 32K | 63 layers | on | ready | 34.3 | 36.16 | 63 | 0 | yes | - |
| chat | wait | 128K | Automatic | on | ready | 18.1 | 179.42 | 49 | 0 | yes | - |
| chat | wait | 128K | 32 layers | on | ready | 14.1 | 321.69 | 32 | 0 | yes | - |
| chat | wait | 128K | 49 layers | on | ready | 30.2 | 165.98 | 49 | 0 | yes | - |
| chat | wait | 128K | 63 layers | on | ready | 36.3 | 207.98 | 63 | 0 | yes | - |
