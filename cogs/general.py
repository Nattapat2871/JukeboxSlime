import discord
from discord.ext import commands
from discord import app_commands # สำหรับ Slash Commands

class GeneralCog(commands.Cog, name="ทั่วไป"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="แสดงข้อมูลช่วยเหลือคำสั่งทั้งหมด")
    async def help_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) # <--- เพิ่ม defer ที่นี่
        """Slash command /help"""
        bot_name = self.bot.user.name
        embed = discord.Embed(
            title=f"ความช่วยเหลือคำสั่งสำหรับ {bot_name} 🦊",
            description="นี่คือรายการคำสั่งที่คุณสามารถใช้ได้:",
            color=discord.Color.orange()
        )
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        general_commands_text = (
            "`/help` - แสดงข้อความช่วยเหลือนี้\n"
            "`/ping` - ตรวจสอบความหน่วงของบอท"
        )
        embed.add_field(name="📜 คำสั่งทั่วไป", value=general_commands_text, inline=False)

        music_commands_text = (
            "**การควบคุมผ่าน Panel:**\n"
            f"พิมพ์ชื่อเพลงหรือวางลิงก์ในช่อง `#🎵jukebox-slime` (หากตั้งค่าแล้ว) เพื่อเล่นเพลง\n"
            "ใช้ปุ่มบน Panel เพื่อควบคุมการเล่น (Play/Pause, Skip, Stop, Loop, Mute, Volume, Queue)\n\n"
            "**คำสั่ง Prefix `s!`:**\n"
            "`s!play <ชื่อเพลง/URL>` หรือ `s!p <ชื่อเพลง/URL>` - เล่นเพลงหรือเพิ่มเข้าคิว\n"
            "`s!skip` หรือ `s!s` - ข้ามเพลงปัจจุบัน\n"
            "`s!stop` - หยุดเล่นเพลงและล้างคิว\n"
            "`s!pause` - หยุดเล่นเพลงชั่วคราว\n"
            "`s!resume` - เล่นเพลงต่อจากที่หยุดไว้\n"
            "`s!queue` หรือ `s!q` - แสดงรายการเพลงในคิว (แบบข้อความ)\n"
            "`s!nowplaying` หรือ `s!np` - แสดงเพลงที่กำลังเล่นอยู่\n"
            "`s!loop` หรือ `s!l` - เปลี่ยนโหมดการเล่นวน\n"
            "`s!clear` หรือ `s!clr` - ล้างคิวเพลงทั้งหมด\n"
            "`s!join` - ให้บอทเข้าร่วมช่องเสียง\n"
            "`s!leave` หรือ `s!dc` - ให้บอทออกจากช่องเสียง"
        )
        embed.add_field(name="🎶 คำสั่งเพลง", value=music_commands_text, inline=False)
        
        setup_commands_text = (
            "`/setup-music` - (สำหรับผู้ดูแล) สร้างช่องสั่งเพลงและ Music Control Panel"
        )
        embed.add_field(name="⚙️ คำสั่งตั้งค่า (ผู้ดูแล)", value=setup_commands_text, inline=False)

        embed.add_field(
            name="ผู้พัฒนา 💻",
            value=f"บอทนี้พัฒนาโดย [Nattapat2871](https://github.com/Nattapat2871)", # ส่วนนี้ของคุณ
            inline=False
        )





    @app_commands.command(name="ping", description="ตรวจสอบความหน่วง (latency) ของบอท")
    async def ping_slash(self, interaction: discord.Interaction):
        # ไม่จำเป็นต้อง defer ที่นี่ เพราะตอบกลับเร็วมาก
        latency_ms = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"ความหน่วงของบอท: ``{latency_ms}ms``",
            color=discord.Color.green() if latency_ms < 150 else (discord.Color.orange() if latency_ms < 300 else discord.Color.red())
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))