"""
Receive Anakin webhooks instead of polling (Flask).

Submit jobs with `webhook_url=...` and `wait=False`, then handle the signed
`job.completed` / `wire.job.completed` / `monitor.change` events here.

Run:
    pip install flask
    ANAKIN_API_KEY=ak-... ANAKIN_WEBHOOK_SECRET=whsec_... flask --app examples/webhook_receiver run

Get the secret with `Anakin().webhooks.signing_secret()` (per-request
webhook_url deliveries) or from `client.webhooks.create(...)`.
"""

from __future__ import annotations

import os

from flask import Flask, abort, request  # type: ignore[import-not-found]

from anakin import Anakin, verify_webhook_signature

app = Flask(__name__)
client = Anakin()
seen: set[str] = set()


@app.post("/anakin-webhook")
def webhook() -> tuple[str, int]:
    if not verify_webhook_signature(
        request.get_data(),  # raw bytes: never re-serialised JSON
        request.headers.get("X-Anakin-Signature"),
        os.environ["ANAKIN_WEBHOOK_SECRET"],
        timestamp=request.headers.get("X-Anakin-Timestamp"),
        tolerance=300,
    ):
        abort(401)

    delivery_id = request.headers.get("X-Anakin-Delivery-Id", "")
    if delivery_id in seen:  # deliveries are at-least-once
        return "", 200
    seen.add(delivery_id)

    event = request.get_json()
    if event.get("type") == "job.completed":
        job_id = event["data"].get("jobId") or event["data"].get("id")
        # Small results are inlined as data.result; fetch the full one by ID.
        print("job done:", job_id)
    elif event.get("type") == "monitor.change":
        print("monitor changed:", event.get("summary"))
    return "", 200


def submit_example() -> None:
    """Fire-and-forget: returns immediately, the webhook fires when done."""
    job = client.crawl(
        "https://example.com",
        max_pages=20,
        webhook_url="https://your-app.com/anakin-webhook",
        wait=False,
    )
    print("submitted", job.id, job.status)
