# Daily RSI(2)/ADX(2) book on XAUUSD: every daily close

Rebuilt from OANDA hourly mid candles with the book's own code. **Entry needs all three:** close above the 50-day SMA, close above the 7-day EMA, RSI(2) above ADX(2). Long only. Exit: RSI(2) below ADX(2). "Bot window" = daily candles the bot's 120-day hourly history gives (it needs 60).

| daily close (NY) | close | SMA50 | EMA7 | RSI2 | ADX2 | > SMA50 | > EMA7 | RSI2 > ADX2 | **entry** | bot window |
|---|---|---|---|---|---|---|---|---|---|---|
| Tue 20 Oct | 4,125.47 | 4,321.51 | 4,146.31 | 21.0 | 47.8 | ❌ | ❌ | ❌ | **❌** | 86 |
| Wed 21 Oct | 4,141.02 | 4,316.15 | 4,144.99 | 54.5 | 61.4 | ❌ | ❌ | ❌ | **❌** | 86 |
| Thu 22 Oct | 4,024.51 | 4,309.62 | 4,114.87 | 7.4 | 78.9 | ❌ | ❌ | ❌ | **❌** | 86 |
| Fri 23 Oct | 3,995.81 | 4,302.00 | 4,085.10 | 5.2 | 88.5 | ❌ | ❌ | ❌ | **❌** | 86 |
| Mon 26 Oct | 4,017.19 | 4,294.01 | 4,068.12 | 34.4 | 93.4 | ❌ | ❌ | ❌ | **❌** | 86 |
| Tue 27 Oct | 4,060.33 | 4,288.52 | 4,066.18 | 70.7 | 57.2 | ❌ | ❌ | ✅ | **❌** | 86 |
| Wed 28 Oct | 4,067.29 | 4,279.41 | 4,066.45 | 75.2 | 53.6 | ❌ | ✅ | ✅ | **❌** | 86 |
| Thu 29 Oct | 4,020.57 | 4,269.44 | 4,054.98 | 24.8 | 35.7 | ❌ | ❌ | ❌ | **❌** | 86 |
| Fri 30 Oct | 3,875.64 | 4,254.90 | 4,010.15 | 4.8 | 62.3 | ❌ | ❌ | ❌ | **❌** | 86 |
| Mon 02 Nov | 3,946.74 | 4,240.81 | 3,994.30 | 46.8 | 75.5 | ❌ | ❌ | ❌ | **❌** | 86 |
| Tue 03 Nov | 3,930.32 | 4,226.23 | 3,978.30 | 38.9 | 79.7 | ❌ | ❌ | ❌ | **❌** | 86 |
| Wed 04 Nov | 4,060.36 | 4,215.55 | 3,998.82 | 83.4 | 74.4 | ❌ | ✅ | ✅ | **❌** | 86 |
| Thu 05 Nov | 4,088.22 | 4,205.27 | 4,021.17 | 87.4 | 80.4 | ❌ | ✅ | ✅ | **❌** | 86 |
| Fri 06 Nov | 4,070.59 | 4,197.58 | 4,033.52 | 67.1 | 56.2 | ❌ | ✅ | ✅ | **❌** | 86 |

**0 entry signal(s) in 14 daily closes.** Conditions held on: above SMA50 0, above EMA7 4, RSI2 > ADX2 5. Bot's history short on 0 of them.
