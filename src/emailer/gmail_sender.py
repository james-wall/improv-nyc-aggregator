import os
import base64
from email.message import EmailMessage
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def authenticate_gmail():
    creds = None
    token_file = "token.json"
    creds_file = "credentials.json"

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_file, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

def send_email(to, subject, body, from_name="Improv NYC Digest"):
    service = authenticate_gmail()

    message = EmailMessage()
    message.set_content(body)
    message["To"] = to
    message["From"] = f"{from_name} <me>"
    message["Subject"] = subject

    encoded_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()

    send_result = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": encoded_msg})
        .execute()
    )

    print(f"📬 Email sent! ID: {send_result['id']}")
