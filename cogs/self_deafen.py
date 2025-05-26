import discord
from discord.ext import commands

class BotSelfDeafen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # แฟล็กเพื่อติดตามว่าการตรวจสอบสถานะเมื่อบอทพร้อมทำงานครั้งแรกได้ทำไปแล้วหรือยัง
        # สำหรับ instance ของ cog นี้ เพื่อป้องกันการทำงานซ้ำซ้อนหาก on_ready ถูกเรียกหลายครั้ง
        self._initial_deafen_check_done = False
        print(f"Cog '{self.__class__.__name__}' initialized.")

    @commands.Cog.listener()
    async def on_ready(self):
        """
        เมื่อบอทพร้อมทำงาน จะตรวจสอบว่าบอทอยู่ในช่องเสียงใดๆ หรือไม่
        และทำการปิดการได้ยินของตัวเองหากยังไม่ได้ทำ
        """
        if not self._initial_deafen_check_done:
            print(f"Bot '{self.bot.user}' is ready. Cog '{self.__class__.__name__}' performing initial self-deafen check.")
            for guild in self.bot.guilds:
                # guild.me คือ Member object ของบอทเองในเซิร์ฟเวอร์นั้น
                if guild.me and guild.me.voice and guild.me.voice.channel:
                    # ตรวจสอบว่าบอทอยู่ในช่องเสียงและยังไม่ได้ปิดการได้ยินตัวเอง
                    if not guild.me.voice.self_deaf:
                        try:
                            await guild.me.edit(deafen=True)
                            print(f"Bot auto-deafened itself in '{guild.name}' / '{guild.me.voice.channel.name}' (on ready).")
                        except discord.Forbidden:
                            print(f"Bot lacks permission to self-deafen in '{guild.name}' / '{guild.me.voice.channel.name}'.")
                        except Exception as e:
                            print(f"Error auto-deafening bot in '{guild.name}' on ready: {e}")
                    else:
                        print(f"Bot was already self-deafened in '{guild.name}' / '{guild.me.voice.channel.name}' (on ready).")
            self._initial_deafen_check_done = True
        else:
            print(f"Cog '{self.__class__.__name__}' on_ready: Initial check previously completed.")


    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        เมื่อสถานะเสียงของสมาชิกมีการเปลี่ยนแปลง จะตรวจสอบหากเป็นบอทเอง
        และบอทเพิ่งเข้าร่วมช่องเสียงใหม่ จะทำการปิดการได้ยินตัวเอง
        """
        # ตรวจสอบว่าเป็นบอทตัวเองหรือไม่
        if member.id == self.bot.user.id:
            # ตรวจสอบว่าบอทเพิ่งเข้าร่วมช่องเสียง (ก่อนหน้านี้ไม่ได้อยู่ในช่องเสียง แต่ตอนนี้อยู่)
            if before.channel is None and after.channel is not None:
                print(f"Bot '{member.name}' joined voice channel '{after.channel.name}' in guild '{member.guild.name}'.")
                # ตรวจสอบว่าบอทในสถานะใหม่ยังไม่ได้ปิดการได้ยินตัวเอง
                if after.channel and member.voice and not member.voice.self_deaf: # member.voice.self_deaf หรือ after.self_deaf ก็ได้
                    try:
                        await member.edit(deafen=True)
                        print(f"Bot auto-deafened itself upon joining '{after.channel.name}' in '{member.guild.name}'.")
                    except discord.Forbidden:
                        print(f"Bot lacks permission to self-deafen upon joining '{after.channel.name}' in '{member.guild.name}'.")
                    except Exception as e:
                        print(f"Error auto-deafening bot upon joining '{after.channel.name}': {e}")
                elif member.voice and member.voice.self_deaf:
                    print(f"Bot joined '{after.channel.name}' and was already self-deafened.")

async def setup(bot: commands.Bot):
    """ฟังก์ชันมาตรฐานสำหรับโหลด Cog"""
    await bot.add_cog(BotSelfDeafen(bot))
    print("Cog 'BotSelfDeafen' has been loaded.")