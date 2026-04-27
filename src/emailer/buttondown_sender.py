import os

import requests
from dotenv import load_dotenv

load_dotenv()

BUTTONDOWN_API_URL = "https://api.buttondown.com/v1/emails"


def send_newsletter(subject: str, body: str, html: str):
    """Send a newsletter to all Buttondown subscribers."""
    api_key = os.environ["BUTTONDOWN_API_KEY"]

    response = requests.post(
        BUTTONDOWN_API_URL,
        headers={
            "Authorization": f"Token {api_key}",
            # One-time confirmation Buttondown requires per API key before
            # the first real send — harmless to keep on subsequent calls.
            "X-Buttondown-Live-Dangerously": "true",
        },
        json={
            "subject": subject,
            "body": html,
            "status": "about_to_send",
        },
    )

    if response.ok:
        print(f"📬 Newsletter sent via Buttondown")
    else:
        raise RuntimeError(
            f"Buttondown API error {response.status_code}: {response.text}"
        )
