import os
import json
import base64
import glob
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta

import requests
import imageio_ffmpeg
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, FileMessage, VideoMessage

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

GAS_URL = 'https://script.google.com/macros/s/AKfycbyge7LrGj8xwz3FMG5maMYxHKWQjA14E27hLVHfaCci2SMFGsO8rLN_TXPIZPFbFM4chA/exec'

JST = timezone(timedelta(hours=9))

# 動画から切り出すコマの間隔（秒）と、1枚の一覧画像に並べる数（横×縦）
FRAME_INTERVAL_SEC = 2
SHEET_COLS = 4
SHEET_ROWS = 4
FRAME_WIDTH = 480


def upload_to_drive(filename, content, mimetype):
    payload = {
        'fileName': filename,
        'fileContent': base64.b64encode(content).decode('utf-8'),
        'mimeType': mimetype
    }
    requests.post(GAS_URL, json=payload)


def get_content(message_id):
    message_content = line_bot_api.get_message_content(message_id)
    return b''.join(chunk for chunk in message_content.iter_content())


def file_prefix(event):
    """受信時刻と送信者名から、ファイル名の頭を作る（例: 20261124_145318_朝沼　勉）"""
    ts = datetime.fromtimestamp(event.timestamp / 1000, JST).strftime('%Y%m%d_%H%M%S')
    name = ''
    try:
        name = line_bot_api.get_profile(event.source.user_id).display_name
    except Exception:
        pass
    return f'{ts}_{name}' if name else ts


def make_contact_sheets(video_path, out_dir):
    """動画からFRAME_INTERVAL_SEC秒ごとにコマを切り出し、
    SHEET_COLS×SHEET_ROWS枚ずつ1枚の一覧画像（JPEG）にまとめる。
    数百KB程度になるので、10MBの上限に引っかからずに読める。"""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    pattern = os.path.join(out_dir, 'sheet_%02d.jpg')
    vf = (
        f'fps=1/{FRAME_INTERVAL_SEC},'
        f'scale={FRAME_WIDTH}:-2,'
        "drawtext=text='%{pts\\:hms}':x=8:y=8:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6,"
        f'tile={SHEET_COLS}x{SHEET_ROWS}:padding=4:color=white'
    )
    cmd = [ffmpeg, '-y', '-loglevel', 'error', '-i', video_path,
           '-vf', vf, '-q:v', '4', pattern]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # drawtext（フォント）が使えない環境では時刻なしで作り直す
        vf_plain = (
            f'fps=1/{FRAME_INTERVAL_SEC},'
            f'scale={FRAME_WIDTH}:-2,'
            f'tile={SHEET_COLS}x{SHEET_ROWS}:padding=4:color=white'
        )
        cmd = [ffmpeg, '-y', '-loglevel', 'error', '-i', video_path,
               '-vf', vf_plain, '-q:v', '4', pattern]
        subprocess.run(cmd, check=True, capture_output=True)
    return sorted(glob.glob(os.path.join(out_dir, 'sheet_*.jpg')))


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
    content = get_content(event.message.id)
    upload_to_drive('image.jpg', content, 'image/jpeg')


@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    content = get_content(event.message.id)
    filename = event.message.file_name
    upload_to_drive(filename, content, 'application/octet-stream')


@handler.add(MessageEvent, message=VideoMessage)
def handle_video(event):
    content = get_content(event.message.id)
    prefix = file_prefix(event)
    upload_to_drive(f'{prefix}.mp4', content, 'video/mp4')

    # 動画そのものは大きくて読めないことがあるので、コマ割りの一覧画像も保存する
    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, 'video.mp4')
        with open(video_path, 'wb') as f:
            f.write(content)
        try:
            sheets = make_contact_sheets(video_path, tmp)
        except Exception as e:
            app.logger.error('コマ割りの作成に失敗: %s', e)
            return
        total = len(sheets)
        for i, path in enumerate(sheets, start=1):
            with open(path, 'rb') as f:
                upload_to_drive(f'{prefix}_動画コマ{i}of{total}.jpg', f.read(), 'image/jpeg')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
