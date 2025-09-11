import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.emailer.gmail_sender import send_email

# Example values
to = os.getenv("TEST_EMAIL")
subject = "This Week in NYC Improv 🎭"
body = open("last_summary.txt", "r").read()

send_email(to=to, subject=subject, body=body)
