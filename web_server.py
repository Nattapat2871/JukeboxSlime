# web_server.py
from flask import Flask, render_template, jsonify
import logging
from collections import deque
import os # เพิ่ม os เข้ามาเพื่อใช้กับ port

flask_app = Flask(__name__)

MAX_LOG_LINES = 200
console_logs = deque(maxlen=MAX_LOG_LINES)

class WebLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        console_logs.append(log_entry)

web_log_handler = WebLogHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
web_log_handler.setFormatter(formatter)

@flask_app.route('/')
def home():
    return "Discord Bot is running. Go to <a href='/logs'>/logs</a> to see console output."

@flask_app.route('/logs')
def display_logs():
    return render_template('logs.html', logs=list(console_logs))

@flask_app.route('/logs/json')
def get_logs_json():
    return jsonify(list(console_logs))

# ฟังก์ชันสำหรับรัน Flask app (จะถูกเรียกจาก main.py ใน thread แยก)
def run_flask_app_in_thread():
    port = int(os.environ.get("FLASK_PORT", 8080)) # ใช้ FLASK_PORT หรือ default 8080
    try:
        print(f"Starting Flask server for logs on http://0.0.0.0:{port}")
        # use_reloader=False สำคัญมากเมื่อรันใน thread และเพื่อไม่ให้ Flask รีสตาร์ทตัวเอง
        flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        # ใช้ app_logger ถ้าถูกส่งเข้ามา หรือ print ถ้ายังไม่มี
        print(f"Failed to run Flask app in thread: {e}")
        # app_logger.error(f"Failed to run Flask app in thread: {e}") # ถ้ามี app_logger