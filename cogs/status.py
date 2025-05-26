# cogs/status_cog.py
import discord
from discord.ext import commands, tasks
import logging
import traceback # สำหรับ traceback.print_exc()

# ใช้ logger ที่ตั้งค่าไว้ใน main.py
# Cog นี้จะใช้ logger ชื่อ 'cogs.status_cog' ถ้า __name__ ถูกใช้
# หรือจะ get root_logger โดยตรงก็ได้ แต่การใช้ __name__ เป็น convention ที่ดี
logger = logging.getLogger(__name__)

class StatusCog(commands.Cog, name="StatusUpdater"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.status_message = "/help | jukebox slime musicbot" # ข้อความสถานะตามที่คุณต้องการ
        # ถ้าต้องการให้สถานะอัปเดตเป็นระยะ (เช่น แสดงจำนวนเซิร์ฟเวอร์) สามารถใช้ @tasks.loop ได้
        # self.change_status_task.start() # ตัวอย่างการเริ่ม task loop

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Event นี้จะถูกเรียกทุกครั้งที่บอทเชื่อมต่อหรือ επανασυνδέεται สำเร็จ
        การตั้งค่าสถานะที่นี่จะช่วยให้มั่นใจว่าสถานะถูกตั้งค่าเสมอ
        """
        logger.info(f"StatusCog: Bot is ready ({self.bot.user.name}). Setting presence...")
        await self.set_initial_presence()

    async def set_initial_presence(self):
        """ตั้งค่าสถานะเริ่มต้นของบอท"""
        activity = discord.Activity(
            name=self.status_message,
            type=discord.ActivityType.listening  # ประเภทกิจกรรมเป็น "Listening to"
        )
        try:
            await self.bot.change_presence(activity=activity, status=discord.Status.online)
            logger.info(f"Bot presence set to: Listening to \"{self.status_message}\"")
        except Exception as e:
            logger.error(f"Failed to set bot presence: {e}")
            traceback.print_exc()

    # --- ตัวอย่าง Task Loop (ถ้าต้องการสถานะที่เปลี่ยนแปลงตลอดเวลา) ---
    # @tasks.loop(minutes=15)  # อัปเดตทุก 15 นาที
    # async def change_status_task(self):
    #     # ตัวอย่างการเปลี่ยนสถานะแบบสุ่ม หรือแสดงข้อมูลแบบไดนามิก
    #     # statuses = [
    #     #     discord.Activity(name=f"/help | {len(self.bot.guilds)} servers", type=discord.ActivityType.listening),
    #     #     discord.Activity(name="Music 🎵", type=discord.ActivityType.playing),
    #     # ]
    #     # new_activity = random.choice(statuses)
    #     # await self.bot.change_presence(activity=new_activity)
    #     # logger.info(f"Status updated to: {new_activity.type.name} {new_activity.name}")
    #     
    #     # สำหรับตอนนี้ ให้มันตั้งค่าสถานะเดิมซ้ำ เพื่อให้แน่ใจว่ายังคงอยู่
    #     await self.set_initial_presence()


    # @change_status_task.before_loop
    # async def before_change_status_task(self):
    #     await self.bot.wait_until_ready() # รอให้บอทพร้อมก่อนเริ่ม loop


    # ฟังก์ชันนี้จะถูกเรียกเมื่อ Cog ถูก unload (ถ้าคุณมีคำสั่ง unload cog)
    # def cog_unload(self):
    #     if hasattr(self, 'change_status_task') and self.change_status_task.is_running():
    #         self.change_status_task.cancel()
    #     logger.info("StatusCog unloaded and status task cancelled.")

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusCog(bot))