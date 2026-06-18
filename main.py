import os
import json
import io
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

GOOGLE_DRIVE_FOLDER_ID = os.environ['GOOGLE_DRIVE_FOLDER_ID']

def upload_to_drive(filename, content, mimetype):
    creds_json = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    creds = Credentials(
        token=creds_json['token'],
        refresh_token=creds_json['refresh_token'],
        token_uri='https://oauth2.googleapis.com/token',
        client_id=creds_json['client_id'],
        client_secret=creds_json['client_secret']
    )
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {
        'name': filename,
        'parents': [GOOGLE_DRIVE_FOLDER_ID]
    }
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mimetype)
    service.files().create(body=file_metadata, media_body=media).execute()

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
