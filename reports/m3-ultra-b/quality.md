# Answer quality summary

What each column means:

- **Setting**: the server setting these answers were given under.
- **Question set**: GSM8K, MMLU or Passkey.
- **Right**: answers that passed their check.
- **Scored**: answers that could be scored.
- **Right (%)**: Right / Scored, in percent.
- **Errors**: requests the server answered with an error.
- **Prompt size against target**: the real prompt size as a share of the size asked for (passkey rows only).
- **Cut off at the cap**: answers that ran out of tokens while the model was still thinking.

| Setting | Question set | Right | Scored | Right (%) | Errors | Prompt size against target | Cut off at the cap |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| 4-bit prompt memory | gsm8k | 194 | 200 | 97.0% | 0 | - | 3 |
| 4-bit prompt memory | mmlu | 433 | 500 | 86.6% | 0 | - | 54 |
| 4-bit prompt memory | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |
| 8-bit prompt memory | gsm8k | 194 | 200 | 97.0% | 0 | - | 3 |
| 8-bit prompt memory | mmlu | 433 | 500 | 86.6% | 0 | - | 54 |
| 8-bit prompt memory | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |
| Mac alone | gsm8k | 194 | 200 | 97.0% | 0 | - | 3 |
| Mac alone | mmlu | 433 | 500 | 86.6% | 0 | - | 54 |
| Mac alone | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |
| + Spark helper | gsm8k | 194 | 200 | 97.0% | 0 | - | 3 |
| + Spark helper | mmlu | 433 | 500 | 86.6% | 0 | - | 54 |
| + Spark helper | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |

Rows: 2824. Rows with empty answer text: 228.
