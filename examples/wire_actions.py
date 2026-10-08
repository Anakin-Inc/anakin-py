"""
Wire end to end: discover -> inspect -> (log in) -> run.

Wire turns supported sites (Amazon, Walmart, LinkedIn, Airbnb, Zillow, ...)
into API actions that return structured JSON, so you don't maintain scrapers.

Run:
    ANAKIN_API_KEY=ak-... python examples/wire_actions.py
"""

from __future__ import annotations

import json

from anakin import Anakin, WireAuthExpiredError, WireAuthRequiredError


def main() -> None:
    with Anakin() as client:
        # 1. Find actions by intent.
        matches = client.wire.discover("search products on walmart", limit=5)
        for m in matches:
            print(f"{m.action_id:<32} {m.catalog_slug:<12} credits={m.credits}")
        if not matches:
            return
        action = matches[0]

        # 2. Inspect the site's full action list and parameter schemas.
        if action.catalog_slug:
            detail = client.wire.catalog(action.catalog_slug)
            for a in detail.actions:
                print(f"  [{a.type}] {a.action_id}  auth={a.auth_mode}  params={a.parameters}")

        # 3. Run it. Auth-required actions need a credential_id from
        #    client.wire.identities() or client.wire.login(...).
        try:
            result = client.wire.run(action.action_id, {"query": "wireless earbuds"})
        except WireAuthRequiredError as err:
            print(f"Connect your account first: {err.connect_url}")
            return
        except WireAuthExpiredError:
            print("Saved login expired; run client.wire.login(...) again.")
            return

        print(f"\ncredits_used={result.credits_used} execution_ms={result.execution_ms}")
        print(json.dumps(result.data, indent=2)[:1500])

        # 4. Site not covered? Ask Wire to build it (charges credits, refunded on failure):
        # build = client.wire.build("https://example.com", "Extract product name and price")
        # print(client.wire.get_build(build.id).status)


if __name__ == "__main__":
    main()
