# Many users: every wave

One line per wave, in cell order. A wave is its user count of requests released together.
`Wave wall` is the time from the moment the wave opened to its last reply, and `Prompt
tok/s` is every user's prompt tokens together over that time. A request a flag marks not
valid stays in its wave's count and out of its means.

| Arm | Prompt | Users | Wave | Requests | Valid | Time to first token s | Wave wall s | Prompt tok/s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mac alone | 4K | 1 | 0 | 1 | 1 | 5.03 | 7.94 | 522 |
| Mac alone | 4K | 1 | 1 | 1 | 1 | 4.99 | 7.76 | 534 |
| Mac alone | 4K | 1 | 2 | 1 | 1 | 4.91 | 7.89 | 525 |
| With helper | 4K | 1 | 0 | 1 | 1 | 4.30 | 7.33 | 565 |
| With helper | 4K | 1 | 1 | 1 | 1 | 4.17 | 7.26 | 570 |
| With helper | 4K | 1 | 2 | 1 | 1 | 4.05 | 6.92 | 599 |
| Mac alone | 4K | 2 | 0 | 2 | 2 | 10.97 | 20.07 | 413 |
| Mac alone | 4K | 2 | 1 | 2 | 2 | 10.18 | 18.42 | 450 |
| Mac alone | 4K | 2 | 2 | 2 | 2 | 9.79 | 18.97 | 437 |
| With helper | 4K | 2 | 0 | 2 | 2 | 6.59 | 13.69 | 605 |
| With helper | 4K | 2 | 1 | 2 | 2 | 6.70 | 15.19 | 545 |
| With helper | 4K | 2 | 2 | 2 | 2 | 6.71 | 13.83 | 599 |
| Mac alone | 4K | 4 | 0 | 4 | 4 | 19.28 | 34.14 | 485 |
| Mac alone | 4K | 4 | 1 | 4 | 4 | 19.04 | 32.01 | 518 |
| Mac alone | 4K | 4 | 2 | 4 | 4 | 19.37 | 33.56 | 494 |
| With helper | 4K | 4 | 0 | 4 | 4 | 10.78 | 22.68 | 730 |
| With helper | 4K | 4 | 1 | 4 | 4 | 10.99 | 22.90 | 724 |
| With helper | 4K | 4 | 2 | 4 | 4 | 11.02 | 23.68 | 700 |
| Mac alone | 4K | 8 | 0 | 8 | 8 | 37.42 | 58.41 | 567 |
| Mac alone | 4K | 8 | 1 | 8 | 8 | 40.26 | 81.45 | 407 |
| Mac alone | 4K | 8 | 2 | 8 | 8 | 37.62 | 56.70 | 584 |
| With helper | 4K | 8 | 0 | 8 | 8 | 18.97 | 41.70 | 795 |
| With helper | 4K | 8 | 1 | 8 | 8 | 19.13 | 41.34 | 801 |
| With helper | 4K | 8 | 2 | 8 | 8 | 19.54 | 43.03 | 770 |
| Mac alone | 32K | 1 | 0 | 1 | 1 | 33.77 | 38.16 | 857 |
| Mac alone | 32K | 1 | 1 | 1 | 1 | 34.65 | 38.65 | 846 |
| Mac alone | 32K | 1 | 2 | 1 | 1 | 34.65 | 39.20 | 834 |
| With helper | 32K | 1 | 0 | 1 | 1 | 16.29 | 19.60 | 1,668 |
| With helper | 32K | 1 | 1 | 1 | 1 | 16.96 | 21.06 | 1,553 |
| With helper | 32K | 1 | 2 | 1 | 1 | 17.05 | 20.53 | 1,593 |
| Mac alone | 32K | 2 | 0 | 2 | 2 | 55.02 | 79.37 | 824 |
| Mac alone | 32K | 2 | 1 | 2 | 2 | 54.71 | 78.49 | 833 |
| Mac alone | 32K | 2 | 2 | 2 | 2 | 55.31 | 79.72 | 820 |
| With helper | 32K | 2 | 0 | 2 | 2 | 26.75 | 38.53 | 1,697 |
| With helper | 32K | 2 | 1 | 2 | 2 | 26.09 | 37.65 | 1,737 |
| With helper | 32K | 2 | 2 | 2 | 2 | 27.76 | 39.81 | 1,643 |
| Mac alone | 32K | 4 | 0 | 4 | 4 | 115.58 | 161.38 | 811 |
| Mac alone | 32K | 4 | 1 | 4 | 4 | 114.67 | 159.76 | 819 |
| Mac alone | 32K | 4 | 2 | 4 | 4 | 116.20 | 162.77 | 804 |
| With helper | 32K | 4 | 0 | 4 | 4 | 46.67 | 76.43 | 1,712 |
| With helper | 32K | 4 | 1 | 4 | 4 | 45.56 | 75.07 | 1,743 |
| With helper | 32K | 4 | 2 | 4 | 4 | 45.49 | 75.26 | 1,738 |
| Mac alone | 32K | 8 | 0 | 8 | 8 | 246.88 | 327.54 | 799 |
| Mac alone | 32K | 8 | 1 | 8 | 8 | 245.03 | 323.20 | 809 |
| Mac alone | 32K | 8 | 2 | 8 | 8 | 244.53 | 323.44 | 809 |
| With helper | 32K | 8 | 0 | 8 | 8 | 82.91 | 146.43 | 1,787 |
| With helper | 32K | 8 | 1 | 8 | 8 | 84.88 | 150.63 | 1,737 |
| With helper | 32K | 8 | 2 | 8 | 8 | 85.69 | 151.31 | 1,729 |
