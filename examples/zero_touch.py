"""
Anakin with no API key ("Zero Touch").

Scraping and read-only Wire actions work without an account, metered by a
free per-IP allowance. When it runs out the SDK raises
InsufficientCreditsError with a signup link. Add a key later and the same
code keeps working.

Run:
    python examples/zero_touch.py
"""

from __future__ import annotations

from anakin import Anakin, InsufficientCreditsError


def main() -> None:
    client = Anakin()  # no key: keyless mode
    try:
        doc = client.scrape("https://example.com")
        print(doc.markdown)
        if doc.trial:
            print(f"\nFree credits left: {doc.trial.remaining_credits}")

        # Discovery is always free.
        for match in client.wire.discover("hacker news top stories", limit=3):
            print(f"{match.action_id}: {match.credits} credit(s)")

        result = client.wire.zero_touch("hn_stories", {"limit": 3})
        print(result.data)
    except InsufficientCreditsError as err:
        print(f"Free allowance unavailable: {err.message}")
        print(f"Get 300 free credits and your own key: {err.signup_url}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
