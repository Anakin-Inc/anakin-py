"""
Watch a product page and get alerted when the price or stock changes.

`specific_data` mode extracts only the fields in your JSON Schema, and
`ai_mode` filters out noise (3 + 1 credits per check).

Run:
    ANAKIN_API_KEY=ak-... python examples/price_monitor.py https://example.com/product
"""

from __future__ import annotations

import sys

from anakin import Anakin

SCHEMA = {
    "type": "object",
    "properties": {"price": {"type": "number"}, "in_stock": {"type": "boolean"}},
    "required": ["price"],
}


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    with Anakin() as client:
        monitor = client.monitors.create(
            url,
            interval_minutes=60,
            watch_mode="specific_data",
            output_schema=SCHEMA,
            ai_mode=True,
            ai_goal="only when the price drops or it goes out of stock",
            # alert_webhook_url="https://your-app.com/hooks/anakin",
        )
        print(f"monitor {monitor.id}: {monitor.credit_cost_per_run} credits/check")
        if monitor.alert_webhook_secret:
            print(f"store this webhook secret now: {monitor.alert_webhook_secret}")

        client.monitors.run_now(monitor.id)  # don't wait for the first scheduled check
        for change in client.monitors.changes(monitor.id):
            print(change.changed_at, change.summary)


if __name__ == "__main__":
    main()
