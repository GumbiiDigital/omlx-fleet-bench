# Many people sending prompts at the same time

TODO(stage B): page text

<!-- BEGIN GENERATED: many-users m3-ultra-b -->
### Mac B (Flash-Next)

Time for a whole group of requests to finish, at each prompt size and user count. A group is its user count of requests sent at the same moment. Lower is better.

| Prompt size | Users | Mac alone | Mac + Spark | Faster by |
|---|---:|---:|---:|---:|
| 4K | 1 | 7.9 s | 7.2 s | 1.10× |
| 4K | 2 | 19.2 s | 14.2 s | 1.35× |
| 4K | 4 | 33.2 s | 23.1 s | 1.44× |
| 4K | 8 | 65.5 s | 42.0 s | 1.56× |
| 32K | 1 | 38.7 s | 20.4 s | 1.90× |
| 32K | 2 | 79.2 s | 38.7 s | 2.05× |
| 32K | 4 | 161.3 s (2.7 min) | 75.6 s | 2.13× |
| 32K | 8 | 324.7 s (5.4 min) | 149.5 s (2.5 min) | 2.17× |

- Mean of 3 groups per case, at 1, 2, 4 and 8 users per group.
- A group with a request a check marks not valid is left out of the group means as a whole: its own time and prompt tokens are not used in any mean.
- All 180 requests read their prompt cold and got a correct answer.
<!-- END GENERATED: many-users m3-ultra-b -->
