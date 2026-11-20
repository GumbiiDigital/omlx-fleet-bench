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
| 4-bit prompt memory | gsm8k | 196 | 200 | 98.0% | 0 | - | 0 |
| 4-bit prompt memory | mmlu | 459 | 500 | 91.8% | 0 | - | 17 |
| 4-bit prompt memory | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |
| 8-bit prompt memory | gsm8k | 195 | 200 | 97.5% | 0 | - | 0 |
| 8-bit prompt memory | mmlu | 458 | 500 | 91.6% | 0 | - | 12 |
| 8-bit prompt memory | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |
| + Apple Neural Engine | gsm8k | 195 | 200 | 97.5% | 0 | - | 0 |
| + Apple Neural Engine | mmlu | 456 | 500 | 91.2% | 0 | - | 17 |
| + Apple Neural Engine | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |
| Mac alone | gsm8k | 195 | 200 | 97.5% | 0 | - | 0 |
| Mac alone | mmlu | 454 | 500 | 90.8% | 0 | - | 16 |
| Mac alone | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |
| + Spark helper | gsm8k | 195 | 200 | 97.5% | 0 | - | 0 |
| + Spark helper | mmlu | 459 | 500 | 91.8% | 0 | - | 12 |
| + Spark helper | passkey | 6 | 6 | 100.0% | 0 | 100-100% | 0 |

Rows: 3530. Rows with empty answer text: 74.
