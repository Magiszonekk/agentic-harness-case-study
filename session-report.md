# Per-session cost report (since 2026-09-25)

Snapshot of 2026-10-20, the data behind section 4 of the case study. Generated with
`python3 tools/session_report.py --since 2026-09-25`; session titles translated from Polish.

- sessions that used a model: 803, tokens: 4.43B, fresh (not read from cache): 4.1%
- median tokens per call: 53k
- top 5 sessions: 23% of all tokens
- sessions averaging >200k tokens per call: 31, 55% of all tokens

| profile | source | tokens | calls | k tokens / call | lifetime | user messages | repeated identical tool calls | title |
|---|---|---|---|---|---|---|---|---|
| factorio | cli | 294M | 760 | 386 | 105 h | 12 | 13 | stages 0-3 |
| default | discord | 253M | 1087 | 233 | 260 h | 101 | 4 | Agent wake e2e test failed exit 1 |
| default | cli | 206M | 576 | 358 | 188 h | 117 | 0 | discordrive-next project analysis and context building |
| scraper | cli | 159M | 492 | 323 | 18 h | 30 | 13 | Shinden episode scraping errors |
| discordrivenext | cli | 106M | 243 | 438 | 21 h | 2 | 0 | brief 2026-10-13 webhooks |
