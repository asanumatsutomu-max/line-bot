import os
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

GOOGLE_DRIVE_FOLDER_ID = os.environ['GOOGLE_DRIVE_FOLDER_ID']

def upload_to_drive(filename, content, mimetype):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    import io
    import json

    creds_json = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    creds = service_account.Credentials.from_service_account_info(
        creds_json,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {
        'name': filename,
        'parents': [GOOGLE_DRIVE_FOLDER_ID],
        'driveId': GOOGLE_DRIVE_FOLDER_ID,
    }
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mimetype)
    service.files().create(
        body=file_metadata,
        media_body=media,
        supportsAllDrives=True
    ).execute()

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    content = b''.join(chunk for chunk in message_content.iter_content())
    upload_to_drive('image.jpg', content, 'image/jpeg')

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    content = b''.join(chunk for chunk in message_content.iter_content())
    filename = event.message.file_name
    upload_to_drive(filename, content, 'application/octet-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
