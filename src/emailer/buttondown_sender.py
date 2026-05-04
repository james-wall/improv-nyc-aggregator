import os

import requests
from dotenv import load_dotenv

load_dotenv()

BUTTONDOWN_API_URL = "https://api.buttondown.com/v1/emails"


def send_newsletter(subject: str, body: str, html: str, draft: bool = False):
    """Send a newsletter to all Buttondown subscribers, or save as draft."""
    api_key = os.environ["BUTTONDOWN_API_KEY"]
    status = "draft" if draft else "about_to_send"

    response = requests.post(
        BUTTONDOWN_API_URL,
        headers={
            "Authorization": f"Token {api_key}",
            "X-Buttondown-Live-Dangerously": "true",
        },
        json={
            "subject": subject,
            "body": html,
            "status": status,
        },
    )

    if response.ok:
        if draft:
            print("📝 Newsletter saved as draft in Buttondown — review it in your dashboard")
        else:
            print("📬 Newsletter sent via Buttondown")
    else:
        raise RuntimeError(
            f"Buttondown API error {response.status_code}: {response.text}"
        )
