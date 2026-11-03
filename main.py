import os
import base64
import logging
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage, TextSendMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

GAS_URL = os.environ.get(
    'GAS_URL',
    'https://script.google.com/macros/s/AKfycbyge7LrGj8xwz3FMG5maMYxHKWQjA14E27hLVHfaCci2SMFGsO8rLN_TXPIZPFbFM4chA/exec',
)
JST = timezone(timedelta(hours=9))


class UploadError(Exception):
    pass


def upload_to_drive(filename, content, mimetype):
    payload = {
        'fileName': filename,
        'fileContent': base64.b64encode(content).decode('utf-8'),
        'mimeType': mimetype,
    }
    try:
        res = requests.post(GAS_URL, json=payload, timeout=60)
    except requests.RequestException as e:
        raise UploadError(f'GASに接続できません: {e}') from e

    body = res.text[:500]
    logger.info('GAS response: status=%s url=%s body=%s', res.status_code, res.url, body)

    if 'accounts.google.com' in res.url or 'ServiceLogin' in body:
        raise UploadError('GASがログインを要求しています。デプロイの「アクセスできるユーザー」を「全員」にしてください')
    if res.status_code != 200:
        raise UploadError(f'GASがエラーを返しました (HTTP {res.status_code}): {body[:200]}')
    if 'error' in body.lower() and '<html' in body.lower():
        raise UploadError(f'GASの実行でエラー: {body[:200]}')
    return body


def get_content(message_id):
    message_content = line_bot_api.get_message_content(message_id)
    return b''.join(message_content.iter_content(chunk_size=1024 * 1024))


def reply(event, text):
    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text))
    except Exception:
        logger.exception('LINEへの返信に失敗しました')


def process(event, filename, mimetype):
    try:
        content = get_content(event.message.id)
        logger.info('Received %s (%d bytes)', filename, len(content))
        upload_to_drive(filename, content, mimetype)
        reply(event, f'Googleドライブに保存しました: {filename}')
    except UploadError as e:
        logger.error('Upload failed: %s', e)
        reply(event, f'保存に失敗しました: {e}')
    except Exception as e:
        logger.exception('Unexpected error')
        reply(event, f'保存に失敗しました: {type(e).__name__}: {e}')


@app.route('/', methods=['GET'])
def health():
    return 'OK'


@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning('Invalid signature (LINE_CHANNEL_SECRET を確認してください)')
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    filename = datetime.now(JST).strftime('image_%Y%m%d_%H%M%S') + f'_{event.message.id}.jpg'
    process(event, filename, 'image/jpeg')


@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    process(event, event.message.file_name, 'application/octet-stream')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
