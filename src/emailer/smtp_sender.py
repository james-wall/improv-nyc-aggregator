import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send_email(to, subject, body, from_name="Improv NYC Digest", html=None):
    address = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    message = EmailMessage()
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    message["To"] = to
    message["From"] = f"{from_name} <{address}>"
    message["Subject"] = subject

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(address, password)
        smtp.send_message(message)

    print(f"📬 Email sent to {to}")
