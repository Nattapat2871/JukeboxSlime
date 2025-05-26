# main.py
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import logging
import threading
import traceback

# Import จาก web_server.py
from web_server import flask_app, web_log_handler, console_logs, MAX_LOG_LINES

# --- โหลด Environment Variables ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
FLASK_PORT = int(os.getenv("FLASK_PORT", 8080))

# --- ตั้งค่า Logging ---
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
if root_logger.hasHandlers():
    root_logger.handlers.clear()
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)
root_logger.addHandler(web_log_handler)
root_logger.info("Logging system initialized. Logs will appear here and on the web panel.")

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="s!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    root_logger.info(f'{bot.user.name} ได้เชื่อมต่อกับ Discord แล้ว!')
    root_logger.info(f'ID ของบอท: {bot.user.id}')
    try:
        synced = await bot.tree.sync()
        root_logger.info(f"ซิงค์ {len(synced)} slash command(s) เรียบร้อยแล้ว")
    except Exception as e:
        root_logger.error(f"เกิดข้อผิดพลาดในการซิงค์ slash command: {e}")
        traceback.print_exc()
    music_panel_cog = bot.get_cog("MusicPanelCog")
    if music_panel_cog and hasattr(music_panel_cog, "initial_panel_updates"):
        bot.loop.create_task(music_panel_cog.initial_panel_updates())

# *** แก้ไขฟังก์ชัน load_cogs() ***
async def load_cogs():
    """โหลด Cogs ทั้งหมดจากโฟลเดอร์ cogs โดยอัตโนมัติ"""
    cogs_dir = "cogs" # ชื่อโฟลเดอร์ที่เก็บ Cogs
    if not os.path.exists(cogs_dir):
        root_logger.warning(f"โฟลเดอร์ '{cogs_dir}' ไม่พบ, จะไม่มีการโหลด Cogs ใดๆ")
        return

    for filename in os.listdir(f'./{cogs_dir}'):
        # ตรวจสอบว่าเป็นไฟล์ .py และไม่ใช่ไฟล์ __init__.py
        if filename.endswith('.py') and filename != '__init__.py':
            cog_name = filename[:-3] # ตัดนามสกุล .py ออก
            cog_path = f'{cogs_dir}.{cog_name}' # สร้าง path สำหรับ load_extension
            try:
                await bot.load_extension(cog_path)
                root_logger.info(f'โหลด Cog: {cog_name} (จาก {cog_path}) สำเร็จ')
            except commands.ExtensionAlreadyLoaded:
                root_logger.warning(f'Cog: {cog_name} ถูกโหลดไปแล้ว')
            except commands.ExtensionNotFound:
                root_logger.error(f'ไม่พบ Cog: {cog_name} ที่ path {cog_path}')
            except commands.NoEntryPointError:
                root_logger.error(f'Cog: {cog_name} ไม่มีฟังก์ชัน setup() ที่ path {cog_path}')
            except Exception as e:
                root_logger.error(f'เกิดข้อผิดพลาดในการโหลด Cog {cog_name} (จาก {cog_path}): {e}')
                traceback.print_exc()
# *******************************

def run_flask_locally(): # ... (เหมือนเดิม จาก request_32)
    try:
        root_logger.info(f"Starting Flask server for logs on http://127.0.0.1:{FLASK_PORT}")
        @flask_app.context_processor
        def inject_constants(): return dict(costante={'MAX_LOG_LINES': MAX_LOG_LINES})
        flask_app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False)
    except Exception as e:
        root_logger.critical(f"ไม่สามารถเริ่ม Flask server ได้: {e}"); traceback.print_exc()

async def main_async():
    async with bot:
        await load_cogs() # <--- เรียกใช้ฟังก์ชันที่แก้ไขแล้ว
        await bot.start(TOKEN)

if __name__ == "__main__":
    if not TOKEN:
        root_logger.critical("DISCORD_TOKEN ไม่ได้ถูกตั้งค่าใน .env หรือ environment variables!")
    else:
        flask_thread = threading.Thread(target=run_flask_locally, daemon=True)
        flask_thread.start()
        root_logger.info("Flask app thread for log viewing has been started.")
        try:
            asyncio.run(main_async())
        except KeyboardInterrupt: root_logger.info("Bot ถูกปิดโดยผู้ใช้ (KeyboardInterrupt)")
        except Exception as e: root_logger.critical(f"เกิดข้อผิดพลาดร้ายแรงในการรันบอท: {e}"); traceback.print_exc()
        finally: root_logger.info("Bot process finished.")