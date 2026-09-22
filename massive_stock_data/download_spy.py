import csv
from datetime import datetime, timezone
from pathlib import Path
from massive import RESTClient

client = RESTClient(api_key="TVzvxYwgTFQTebppfnaZnrp2H8j27ye8")

ticker = "SPY"
multiplier = 5
timespan = "minute"
from_date = "2026-01-01"
to_date = "2026-08-31"

print(f"Downloading {ticker} {multiplier}-{timespan} bars from {from_date} to {to_date}...")

# List Aggregates (Bars)
aggs = []
for a in client.list_aggs(
    ticker=ticker,
    multiplier=multiplier,
    timespan=timespan,
    from_=from_date,
    to=to_date,
    limit=50000,
):
    aggs.append(a)

output_file = Path(__file__).parent / f"{ticker.lower()}_{multiplier}min_{from_date}_to_{to_date}.csv"

fieldnames = [
    "timestamp",
    "datetime_utc",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "transactions",
    "otc",
]

with open(output_file, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for a in aggs:
        ts_ms = getattr(a, "timestamp", None)
        dt_str = (
            datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
            if ts_ms is not None
            else ""
        )
        writer.writerow(
            {
                "timestamp": ts_ms,
                "datetime_utc": dt_str,
                "open": getattr(a, "open", None),
                "high": getattr(a, "high", None),
                "low": getattr(a, "low", None),
                "close": getattr(a, "close", None),
                "volume": getattr(a, "volume", None),
                "vwap": getattr(a, "vwap", None),
                "transactions": getattr(a, "transactions", None),
                "otc": getattr(a, "otc", None),
            }
        )

print(f"Saved {len(aggs)} bars to {output_file}")
