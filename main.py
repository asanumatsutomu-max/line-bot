import os
import json
import base64
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

GAS_URL = 'https://script.google.com/macros/s/AKfycbyge7LrGj8xwz3FMG5maMYxHKWQjA14E27hLVHfaCci2SMFGsO8rLN_TXPIZPFbFM4chA/exec'

def upload_to_drive(filename, content, mimetype):
    payload = {
        'fileName': filename,
        'fileContent': base64.b64encode(content).decode('utf-8'),
        'mimeType': mimetype
    }
    requests.post(GAS_URL, json=payload)

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
