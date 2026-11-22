# Mac B (Flash-Next): many users, every group

One line per group, in cell order. A group is its user count of requests sent at the same
moment. A request a flag marks not valid stays in its group's count and out of its means.

What each column means:

- **Setup**: what the group of requests ran on: the Mac alone, or the Mac with its helper.
- **Prompt size**: how long every prompt of the group was (4K = 4,096 tokens).
- **Users**: how many requests the group holds, all sent at the same moment.
- **Round**: which repeat of the same group this is.
- **Requests**: requests in the group.
- **Valid**: requests that passed every check.
- **Wait for the first word (s)**: mean over the valid requests, with the smallest and largest.
- **Whole-group time (s)**: from the moment the group was sent to its last reply.
- **Prompt tokens/s**: every user's prompt tokens together, over the whole-group time.

| Setup | Prompt size | Users | Round | Requests | Valid | Wait for the first word (s) | Whole-group time (s) | Prompt tokens/s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mac alone | 4K | 1 | 0 | 1 | 1 | 5.03 | 7.94 | 522 |
| Mac alone | 4K | 1 | 1 | 1 | 1 | 4.99 | 7.76 | 534 |
| Mac alone | 4K | 1 | 2 | 1 | 1 | 4.91 | 7.89 | 525 |
| Mac + Spark | 4K | 1 | 0 | 1 | 1 | 4.30 | 7.33 | 565 |
| Mac + Spark | 4K | 1 | 1 | 1 | 1 | 4.17 | 7.26 | 570 |
| Mac + Spark | 4K | 1 | 2 | 1 | 1 | 4.05 | 6.92 | 599 |
| Mac alone | 4K | 2 | 0 | 2 | 2 | 10.97 | 20.07 | 413 |
| Mac alone | 4K | 2 | 1 | 2 | 2 | 10.18 | 18.42 | 450 |
| Mac alone | 4K | 2 | 2 | 2 | 2 | 9.79 | 18.97 | 437 |
| Mac + Spark | 4K | 2 | 0 | 2 | 2 | 6.59 | 13.69 | 605 |
| Mac + Spark | 4K | 2 | 1 | 2 | 2 | 6.70 | 15.19 | 545 |
| Mac + Spark | 4K | 2 | 2 | 2 | 2 | 6.71 | 13.83 | 599 |
| Mac alone | 4K | 4 | 0 | 4 | 4 | 19.28 | 34.14 | 485 |
| Mac alone | 4K | 4 | 1 | 4 | 4 | 19.04 | 32.01 | 518 |
| Mac alone | 4K | 4 | 2 | 4 | 4 | 19.37 | 33.56 | 494 |
| Mac + Spark | 4K | 4 | 0 | 4 | 4 | 10.78 | 22.68 | 730 |
| Mac + Spark | 4K | 4 | 1 | 4 | 4 | 10.99 | 22.90 | 724 |
| Mac + Spark | 4K | 4 | 2 | 4 | 4 | 11.02 | 23.68 | 700 |
| Mac alone | 4K | 8 | 0 | 8 | 8 | 37.42 | 58.41 | 567 |
| Mac alone | 4K | 8 | 1 | 8 | 8 | 40.26 | 81.45 | 407 |
| Mac alone | 4K | 8 | 2 | 8 | 8 | 37.62 | 56.70 | 584 |
| Mac + Spark | 4K | 8 | 0 | 8 | 8 | 18.97 | 41.70 | 795 |
| Mac + Spark | 4K | 8 | 1 | 8 | 8 | 19.13 | 41.34 | 801 |
| Mac + Spark | 4K | 8 | 2 | 8 | 8 | 19.54 | 43.03 | 770 |
| Mac alone | 32K | 1 | 0 | 1 | 1 | 33.77 | 38.16 | 857 |
| Mac alone | 32K | 1 | 1 | 1 | 1 | 34.65 | 38.65 | 846 |
| Mac alone | 32K | 1 | 2 | 1 | 1 | 34.65 | 39.20 | 834 |
| Mac + Spark | 32K | 1 | 0 | 1 | 1 | 16.29 | 19.60 | 1,668 |
| Mac + Spark | 32K | 1 | 1 | 1 | 1 | 16.96 | 21.06 | 1,553 |
| Mac + Spark | 32K | 1 | 2 | 1 | 1 | 17.05 | 20.53 | 1,593 |
| Mac alone | 32K | 2 | 0 | 2 | 2 | 55.02 | 79.37 | 824 |
| Mac alone | 32K | 2 | 1 | 2 | 2 | 54.71 | 78.49 | 833 |
| Mac alone | 32K | 2 | 2 | 2 | 2 | 55.31 | 79.72 | 820 |
| Mac + Spark | 32K | 2 | 0 | 2 | 2 | 26.75 | 38.53 | 1,697 |
| Mac + Spark | 32K | 2 | 1 | 2 | 2 | 26.09 | 37.65 | 1,737 |
| Mac + Spark | 32K | 2 | 2 | 2 | 2 | 27.76 | 39.81 | 1,643 |
| Mac alone | 32K | 4 | 0 | 4 | 4 | 115.58 | 161.38 | 811 |
| Mac alone | 32K | 4 | 1 | 4 | 4 | 114.67 | 159.76 | 819 |
| Mac alone | 32K | 4 | 2 | 4 | 4 | 116.20 | 162.77 | 804 |
| Mac + Spark | 32K | 4 | 0 | 4 | 4 | 46.67 | 76.43 | 1,712 |
| Mac + Spark | 32K | 4 | 1 | 4 | 4 | 45.56 | 75.07 | 1,743 |
| Mac + Spark | 32K | 4 | 2 | 4 | 4 | 45.49 | 75.26 | 1,738 |
| Mac alone | 32K | 8 | 0 | 8 | 8 | 246.88 | 327.54 | 799 |
| Mac alone | 32K | 8 | 1 | 8 | 8 | 245.03 | 323.20 | 809 |
| Mac alone | 32K | 8 | 2 | 8 | 8 | 244.53 | 323.44 | 809 |
| Mac + Spark | 32K | 8 | 0 | 8 | 8 | 82.91 | 146.43 | 1,787 |
| Mac + Spark | 32K | 8 | 1 | 8 | 8 | 84.88 | 150.63 | 1,737 |
| Mac + Spark | 32K | 8 | 2 | 8 | 8 | 85.69 | 151.31 | 1,729 |
