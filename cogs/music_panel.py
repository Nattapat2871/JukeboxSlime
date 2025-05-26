import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import datetime
import traceback
import math
import asyncio

# Import LoopMode จาก music_cog.py
try:
    from .music import LoopMode # ใช้ . ถ้าอยู่ใน package เดียวกัน
except ImportError:
    print("WARNING: cogs.music_panel_cog - Could not import LoopMode from .music_cog. Using placeholder.")
    class LoopMode: # Placeholder
        NONE = 0; SONG = 1; QUEUE = 2
        TEXT = {NONE: "ปิด", SONG: "เพลงเดียว", QUEUE: "ทั้งคิว"}

# --- Settings for Data Persistence ---
SETTINGS_DIR = "data"
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "music_panel_settings.json")

# --- ตั้งค่า URL รูปภาพเริ่มต้นโดยตรงในโค้ด ---
DEFAULT_PANEL_IMAGE_URL = "https://cdn.discordapp.com/attachments/1140325634200064050/1143267146097492049/rimuru-tempest.gif?ex=6834c280&is=68337100&hm=99b5a92745ee04b7944e2424696c61b1ef40cf029e62411e52c0c28601e37d9e&"

def load_guild_settings():
    # ... (โค้ด load_guild_settings เหมือนเดิม จาก request_22) ...
    if not os.path.exists(SETTINGS_DIR):
        try: os.makedirs(SETTINGS_DIR); print(f"[Settings] Created directory '{SETTINGS_DIR}'.")
        except OSError as e: print(f"[Settings] Error creating directory '{SETTINGS_DIR}': {e}. Returning empty settings."); return {}
    if not os.path.exists(SETTINGS_FILE): print(f"[Settings] File '{SETTINGS_FILE}' not found. Returning empty settings."); return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f: content = f.read()
        if not content.strip(): print(f"[Settings] File '{SETTINGS_FILE}' is empty. Returning empty settings."); return {}
        loaded_settings = json.loads(content)
        if not isinstance(loaded_settings, dict): print(f"[Settings] Content of '{SETTINGS_FILE}' is not a dict. Returning empty."); return {}
        return loaded_settings
    except json.JSONDecodeError: print(f"[Settings] Error decoding JSON from '{SETTINGS_FILE}'. Returning empty."); return {}
    except FileNotFoundError: print(f"[Settings] FileNotFoundError for '{SETTINGS_FILE}'. Returning empty."); return {}
    except Exception as e: print(f"[Settings] Unexpected error loading '{SETTINGS_FILE}': {e}. Returning empty."); traceback.print_exc(); return {}

def save_guild_settings(settings):
    # ... (โค้ด save_guild_settings เหมือนเดิม จาก request_22) ...
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f: json.dump(settings, f, indent=4)
    except Exception as e: print(f"[Settings] CRITICAL: Failed to save settings to '{SETTINGS_FILE}': {e}"); traceback.print_exc()


class MusicControllerView(discord.ui.View):
    # ... (โค้ด MusicControllerView ทั้งหมดเหมือนเดิม จาก request_24) ...
    def __init__(self, music_cog_instance, panel_cog_instance, guild_id: int):
        super().__init__(timeout=None)
        self.music_cog = music_cog_instance
        self.panel_cog = panel_cog_instance
        self.guild_id = guild_id
        self.message_id = None
        # Row 1
        self.play_pause_btn = discord.ui.Button(emoji="⏯️", style=discord.ButtonStyle.secondary, custom_id=f"musicpanel_play_pause:{guild_id}", row=0)
        self.skip_btn = discord.ui.Button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id=f"musicpanel_skip:{guild_id}", row=0)
        self.stop_btn = discord.ui.Button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id=f"musicpanel_stop:{guild_id}", row=0)
        self.loop_btn = discord.ui.Button(emoji="🔁", label="Loop", style=discord.ButtonStyle.secondary, custom_id=f"musicpanel_loop:{guild_id}", row=0)
        self.mute_btn = discord.ui.Button(emoji="🔇", label="Mute", style=discord.ButtonStyle.secondary, custom_id=f"musicpanel_mute:{guild_id}", row=0)
        # Row 2
        self.vol_up_btn = discord.ui.Button(label="🔊+", style=discord.ButtonStyle.secondary, custom_id=f"musicpanel_vol_up:{guild_id}", row=1)
        self.queue_btn = discord.ui.Button(emoji="📜", label="Queue", style=discord.ButtonStyle.secondary, custom_id=f"musicpanel_queue:{guild_id}", row=1)
        self.support_link_btn = discord.ui.Button(label="🔗 Support", style=discord.ButtonStyle.link, url="https://discord.gg/RbyUEseDYP", row=1) # <<--- แก้ไข URL นี้
        self.vol_down_btn = discord.ui.Button(label="🔉-", style=discord.ButtonStyle.secondary, custom_id=f"musicpanel_vol_down:{guild_id}", row=1)
        self.play_pause_btn.callback = self.play_pause_callback; self.skip_btn.callback = self.skip_callback; self.stop_btn.callback = self.stop_callback
        self.loop_btn.callback = self.loop_button_callback; self.mute_btn.callback = self.mute_button_callback
        self.vol_up_btn.callback = self.vol_up_button_callback; self.queue_btn.callback = self.queue_button_callback; self.vol_down_btn.callback = self.vol_down_button_callback
        self.add_item(self.play_pause_btn); self.add_item(self.skip_btn); self.add_item(self.stop_btn); self.add_item(self.loop_btn); self.add_item(self.mute_btn)
        self.add_item(self.vol_up_btn); self.add_item(self.queue_btn); self.add_item(self.support_link_btn); self.add_item(self.vol_down_btn)
        self.update_button_states()

    async def interaction_check(self, interaction: discord.Interaction) -> bool: # ... (เหมือนเดิม)
        if not self.music_cog: await interaction.response.send_message("ระบบเพลงกำลังเริ่มต้น...", ephemeral=True, delete_after=7); return False
        if not interaction.user.voice or not interaction.user.voice.channel: await interaction.response.send_message("คุณต้องอยู่ในช่องเสียง...", ephemeral=True, delete_after=7); return False
        vc = interaction.guild.voice_client
        if vc and vc.is_connected() and interaction.user.voice.channel != vc.channel: await interaction.response.send_message("คุณต้องอยู่ในช่องเสียงเดียวกับบอท...", ephemeral=True, delete_after=7); return False
        return True

    def update_button_states(self): # ... (เหมือนเดิม)
        if not self.music_cog: 
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.style != discord.ButtonStyle.link: item.disabled = True
            return
        guild_id = self.guild_id; vc = self.music_cog.voice_clients.get(guild_id)
        current_song = self.music_cog.current_song.get(guild_id); queue = self.music_cog._get_song_queue(guild_id)
        pending_summaries = self.music_cog.active_playlist_summaries.get(guild_id, {}).get('entries', [])
        is_playing = bool(vc and vc.is_connected() and vc.is_playing()); is_paused = bool(vc and vc.is_connected() and vc.is_paused())
        is_playing_or_paused = is_playing or is_paused; has_queue_or_current_or_pending = bool(current_song or queue or pending_summaries)
        can_interact_with_player = bool(vc and vc.is_connected())
        if is_playing: self.play_pause_btn.emoji = "⏸️"; self.play_pause_btn.disabled = not can_interact_with_player
        elif is_paused: self.play_pause_btn.emoji = "▶️"; self.play_pause_btn.disabled = not can_interact_with_player
        elif has_queue_or_current_or_pending : self.play_pause_btn.emoji = "▶️"; self.play_pause_btn.disabled = not can_interact_with_player
        else: self.play_pause_btn.emoji = "⏯️"; self.play_pause_btn.disabled = True
        self.skip_btn.disabled = not (is_playing_or_paused or (has_queue_or_current_or_pending and (len(queue) > 0 or len(pending_summaries) > 0) ))
        self.stop_btn.disabled = not is_playing_or_paused
        current_loop = self.music_cog.loop_mode.get(guild_id, LoopMode.NONE) 
        self.loop_btn.label = f"Loop: {LoopMode.TEXT[current_loop]}"; self.loop_btn.disabled = not can_interact_with_player
        is_muted = self.music_cog.is_guild_muted.get(guild_id, False)
        self.mute_btn.emoji = "🔇" if is_muted else "🔊"; self.mute_btn.label = "Unmute" if is_muted else "Mute"; self.mute_btn.disabled = not can_interact_with_player
        self.vol_up_btn.disabled = not can_interact_with_player or is_muted; self.vol_down_btn.disabled = not can_interact_with_player or is_muted
        self.queue_btn.disabled = False

    async def _handle_panel_action(self, interaction: discord.Interaction, music_cog_method, *args, default_ephemeral_message:str = "ดำเนินการแล้ว", **kwargs): # ... (เหมือนเดิม)
        if not self.music_cog:
            if not interaction.response.is_done(): await interaction.response.send_message("ระบบเพลงยังไม่พร้อม.", ephemeral=True, delete_after=7)
            return
        if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
        try:
            result = await music_cog_method(*args, **kwargs)
            final_message = default_ephemeral_message
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], str): final_message = result[1]
            elif isinstance(result, str): final_message = result
            await interaction.followup.send(final_message, ephemeral=True)
        except Exception as e:
            print(f"Error performing music action '{music_cog_method.__name__}' from panel: {e}"); traceback.print_exc()
            await interaction.followup.send(f"เกิดข้อผิดพลาด: {e}", ephemeral=True)

    async def play_pause_callback(self, interaction: discord.Interaction): # ... (เหมือนเดิม)
        if not self.music_cog: return await interaction.response.send_message("ระบบเพลงไม่พร้อม", ephemeral=True, delete_after=7)
        vc = interaction.guild.voice_client
        if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
        if vc and vc.is_playing(): await self._handle_panel_action(interaction, self.music_cog.player_pause, self.guild_id, default_ephemeral_message="⏸️ หยุดเพลงชั่วคราวแล้ว")
        else:
            if vc and vc.is_paused(): await self._handle_panel_action(interaction, self.music_cog.player_resume, self.guild_id, default_ephemeral_message="▶️ เล่นเพลงต่อแล้ว")
            elif self.music_cog._get_song_queue(self.guild_id) or self.music_cog.active_playlist_summaries.get(self.guild_id, {}).get('entries', []):
                 await interaction.followup.send("▶️ กำลังเริ่มเล่นเพลงจากคิว...", ephemeral=True)
                 await self.music_cog._play_next(self.guild_id, interaction.channel, silent_mode=True)
            else: await interaction.followup.send("ไม่มีเพลงในคิวแล้วค่ะ", ephemeral=True)
    
    async def skip_callback(self, interaction: discord.Interaction): await self._handle_panel_action(interaction, self.music_cog.player_skip, self.guild_id)
    async def stop_callback(self, interaction: discord.Interaction): await self._handle_panel_action(interaction, self.music_cog.player_stop, self.guild_id)
    async def loop_button_callback(self, interaction: discord.Interaction): await self._handle_panel_action(interaction, self.music_cog.player_toggle_loop, self.guild_id)
    async def mute_button_callback(self, interaction: discord.Interaction): await self._handle_panel_action(interaction, self.music_cog.player_toggle_mute, self.guild_id)
    async def vol_up_button_callback(self, interaction: discord.Interaction): await self._handle_panel_action(interaction, self.music_cog.player_adjust_volume, self.guild_id, 10)
    async def vol_down_button_callback(self, interaction: discord.Interaction): await self._handle_panel_action(interaction, self.music_cog.player_adjust_volume, self.guild_id, -10)
    
    async def queue_button_callback(self, interaction: discord.Interaction): # *** ใช้ EphemeralQueueView ***
        if not self.music_cog: return await interaction.response.send_message("ระบบเพลงไม่พร้อมใช้งาน", ephemeral=True, delete_after=7)
        await interaction.response.defer(ephemeral=True)
        eph_view = EphemeralQueueView(interaction, self.music_cog, self.guild_id, songs_per_page=10)
        await eph_view.send_initial_message() # EphemeralQueueView จะจัดการ followup.send

    async def on_timeout(self): # ... (เหมือนเดิม)
        if self.message:
            try:
                for item in self.children:
                    if isinstance(item, discord.ui.Button): item.disabled = True
                await self.message.edit(content="⏱️ Music Controller หมดเวลาแล้ว (กรุณา `/setup-music` ใหม่ถ้าต้องการ)", embed=None, view=self)
            except (discord.NotFound, discord.HTTPException): pass
        self.stop()

# --- Ephemeral Queue View (เหมือนเดิมจาก request_24) ---
class EphemeralQueueView(discord.ui.View):
    def __init__(self, original_interaction: discord.Interaction, music_cog_ref, guild_id: int, songs_per_page: int = 10):
        super().__init__(timeout=120.0)
        self.original_interaction = original_interaction; self.music_cog = music_cog_ref; self.guild_id = guild_id
        self.songs_per_page = songs_per_page; self.current_page_index = 0; self.all_display_entries = []; self.total_pages = 1
        self.message: discord.WebhookMessage = None
        self.first_page_eph_btn = discord.ui.Button(label="⏪", style=discord.ButtonStyle.secondary)
        self.prev_eph_btn = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.primary)
        self.page_eph_label = discord.ui.Button(label="หน้า 1/1", style=discord.ButtonStyle.secondary, disabled=True)
        self.next_eph_btn = discord.ui.Button(label="➡️", style=discord.ButtonStyle.primary)
        self.last_page_eph_btn = discord.ui.Button(label="⏩", style=discord.ButtonStyle.secondary)
        self.first_page_eph_btn.callback = self.go_to_first_page; self.prev_eph_btn.callback = self.go_to_previous_page
        self.next_eph_btn.callback = self.go_to_next_page; self.last_page_eph_btn.callback = self.go_to_last_page
        self.add_item(self.first_page_eph_btn); self.add_item(self.prev_eph_btn); self.add_item(self.page_eph_label)
        self.add_item(self.next_eph_btn); self.add_item(self.last_page_eph_btn)
    def _get_current_queue_data(self):
        processed_queue = self.music_cog._get_song_queue(self.guild_id); current_song = self.music_cog.current_song.get(self.guild_id)
        pending_summaries = self.music_cog.active_playlist_summaries.get(self.guild_id, {}).get('entries', []); display_entries = []
        idx = 1
        for song_info in processed_queue:
            title = song_info.get('title', 'N/A'); 
            if len(title) > 50: title = title[:47] + "..."
            webpage_url = song_info.get('webpage_url', '#')
            display_entries.append(f"`{idx}.` [{title}]({webpage_url})"); idx += 1
        for summary in pending_summaries:
            title = summary.get('title', 'เพลงกำลังโหลด...'); 
            if len(title) > 50: title = title[:47] + "..."
            pending_webpage_url = summary.get('url', summary.get('webpage_url','#'))
            display_entries.append(f"`{idx}.` [{title}]({pending_webpage_url}) `(กำลังโหลด...)`"); idx += 1
        self.all_display_entries = display_entries
        self.total_pages = math.ceil(len(self.all_display_entries) / self.songs_per_page) if self.all_display_entries else 1
        return current_song
    def _update_buttons_state(self):
        self.first_page_eph_btn.disabled = self.current_page_index == 0; self.prev_eph_btn.disabled = self.current_page_index == 0
        self.next_eph_btn.disabled = self.current_page_index >= self.total_pages - 1; self.last_page_eph_btn.disabled = self.current_page_index >= self.total_pages - 1
        self.page_eph_label.label = f"หน้า {self.current_page_index + 1}/{self.total_pages}"
    def _create_ephemeral_queue_embed(self):
        current_song = self._get_current_queue_data(); self._update_buttons_state()
        embed = discord.Embed(title="คิวเพลงปัจจุบัน 📜 (Ephemeral)", color=discord.Color.blue())
        if current_song: embed.add_field(name="🎶 กำลังเล่น", value=f"**``{current_song.get('title', 'N/A')}``**", inline=False)
        if not self.all_display_entries: embed.description = "คิวเพลงว่างเปล่า"
        else:
            start_index = self.current_page_index * self.songs_per_page; end_index = start_index + self.songs_per_page
            page_entries = self.all_display_entries[start_index:end_index]
            embed.description = "\n".join(page_entries) if page_entries else "หน้านี้ว่างเปล่า"
            footer_text = f"มีทั้งหมด {len(self.all_display_entries)} รายการ"
            if self.total_pages > 1: footer_text += f" | หน้า {self.current_page_index + 1}/{self.total_pages}"
            embed.set_footer(text=footer_text)
        return embed
    async def send_initial_message(self):
        embed = self._create_ephemeral_queue_embed()
        self.message = await self.original_interaction.followup.send(embed=embed, view=self, ephemeral=True)
    async def _edit_message(self, interaction_from_button: discord.Interaction):
        if interaction_from_button.user.id != self.original_interaction.user.id:
            await interaction_from_button.response.send_message("เฉพาะผู้ขอเท่านั้นที่เปลี่ยนหน้าได้",ephemeral=True, delete_after=5); return
        embed = self._create_ephemeral_queue_embed()
        await interaction_from_button.response.edit_message(embed=embed, view=self)
    async def go_to_first_page(self, interaction: discord.Interaction): self.current_page_index = 0; await self._edit_message(interaction)
    async def go_to_previous_page(self, interaction: discord.Interaction):
        if self.current_page_index > 0: self.current_page_index -= 1
        await self._edit_message(interaction)
    async def go_to_next_page(self, interaction: discord.Interaction):
        if self.current_page_index < self.total_pages - 1: self.current_page_index += 1
        await self._edit_message(interaction)
    async def go_to_last_page(self, interaction: discord.Interaction): self.current_page_index = self.total_pages - 1; await self._edit_message(interaction)
    async def on_timeout(self):
        if self.message:
            try: await self.message.edit(content="คิว (Ephemeral) หมดเวลาแล้ว", embed=None, view=None)
            except (discord.NotFound, discord.HTTPException): pass
        self.stop()


class MusicPanelCog(commands.Cog, name="MusicPanelCog"):
    def __init__(self, bot: commands.Bot): # ... (เหมือนเดิม)
        self.bot = bot; self.music_cog = None
        loaded_settings = load_guild_settings()
        if loaded_settings is None: self.guild_settings = {}
        else: self.guild_settings = loaded_settings
        self.bot.loop.create_task(self.ensure_views_are_loaded_after_ready())

    async def ensure_views_are_loaded_after_ready(self): # ... (เหมือนเดิม)
        await self.bot.wait_until_ready()
        self.music_cog = self.bot.get_cog("MusicCog")
        if not self.music_cog: print("!!! CRITICAL: MusicCog not found by MusicPanelCog after bot is ready."); return
        settings_copy = list(self.guild_settings.items()); changed_settings = False
        for guild_id_str, settings in settings_copy:
            guild = self.bot.get_guild(int(guild_id_str))
            if not guild:
                if guild_id_str in self.guild_settings: del self.guild_settings[guild_id_str]; changed_settings = True; continue
            msg_id = settings.get("music_panel_message_id"); channel_id = settings.get("music_channel_id")
            if msg_id and channel_id:
                try:
                    channel = guild.get_channel(channel_id)
                    if channel and isinstance(channel, discord.TextChannel):
                        try:
                            # await channel.fetch_message(msg_id) # Consider removing if causing startup delays
                            view = MusicControllerView(self.music_cog, self, guild.id); view.message_id = msg_id
                            view.update_button_states()
                            self.bot.add_view(view, message_id=msg_id)
                            print(f"Re-added/Verified MusicControllerView for message {msg_id} in guild {guild_id_str}")
                        except discord.NotFound:
                            print(f"Panel message {msg_id} not found in channel {channel_id} (guild {guild_id_str}). Clearing setting.")
                            if guild_id_str in self.guild_settings and "music_panel_message_id" in self.guild_settings[guild_id_str]:
                                del self.guild_settings[guild_id_str]["music_panel_message_id"]; changed_settings = True
                        except discord.Forbidden: print(f"Forbidden to fetch message {msg_id} in channel {channel_id} (guild {guild_id_str}).")
                        except Exception as e_fetch: print(f"Error fetching/re-adding view for message {msg_id} in guild {guild_id_str}: {e_fetch}")
                    else: 
                        print(f"Music channel {channel_id} not found or not TextChannel in guild {guild_id_str}. Clearing settings.")
                        if guild_id_str in self.guild_settings: del self.guild_settings[guild_id_str]; changed_settings = True
                except Exception as e: print(f"Generic error re-adding view for guild {guild_id_str}: {e}")
        if changed_settings: save_guild_settings(self.guild_settings)


    def get_guild_setting(self, guild_id: int, key: str, default=None): # ... (เหมือนเดิม)
        return self.guild_settings.get(str(guild_id), {}).get(key, default)
    def set_guild_setting(self, guild_id: int, key: str, value): # ... (เหมือนเดิม)
        guild_id_str = str(guild_id)
        if guild_id_str not in self.guild_settings: self.guild_settings[guild_id_str] = {}
        self.guild_settings[guild_id_str][key] = value; save_guild_settings(self.guild_settings)

    async def create_embed_panel(self, guild: discord.Guild): # *** แก้ไขตามคำขอ ***
        if not self.music_cog: print(f"PanelCog: MusicCog not ready for guild {guild.id}"); return None
        guild_id = guild.id; current_song_data = self.music_cog.current_song.get(guild_id)
        # ใช้ DEFAULT_PANEL_IMAGE_URL ที่ hardcode ไว้ในไฟล์นี้เสมอสำหรับ default
        panel_image_url = DEFAULT_PANEL_IMAGE_URL
        if current_song_data and current_song_data.get('thumbnail'): panel_image_url = current_song_data['thumbnail']
        
        embed = discord.Embed(color=0x7E009F); embed.set_image(url=panel_image_url); bot_name = self.bot.user.name
        # --- แก้ไข Footer ---
        footer_text = f"{bot_name} Music System" 
        # --------------------
        current_time_utc = datetime.datetime.now(datetime.timezone.utc)
        embed.set_footer(text=footer_text, icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None); embed.timestamp = current_time_utc
        queue = self.music_cog._get_song_queue(guild_id); active_summaries = self.music_cog.active_playlist_summaries.get(guild_id, {}).get('entries', [])
        queue_count_display = len(queue) + len(active_summaries)
        
        vc = guild.voice_client

        if current_song_data:
            song_title = current_song_data.get('title', "N/A") # แสดงชื่อเต็ม
            duration_seconds = current_song_data.get('duration', 0)
            total_duration_str = str(datetime.timedelta(seconds=int(duration_seconds))).split('.')[0] if duration_seconds > 0 else "Live"
            if total_duration_str.startswith("0:") and len(total_duration_str) > 4 : total_duration_str = total_duration_str[2:]
            elif not total_duration_str.startswith("0:") and len(total_duration_str) > 5 : pass
            
            requester_obj = current_song_data.get('requester')
            requester_display = requester_obj.mention if isinstance(requester_obj, (discord.Member, discord.User)) else "N/A"
            
            volume_percent_val = int(self.music_cog.guild_volumes.get(guild_id, {}).get('current', 0.7) * 100)
            volume_display = f"``{volume_percent_val}%``"
            if self.music_cog.is_guild_muted.get(guild_id, False): volume_display = "``Muted (0%)``"

            voice_channel_mention = vc.channel.mention if vc and vc.channel else "N/A" # <--- ใช้ mention

            embed.add_field(name=f"{bot_name} Music Room | Now Playing | {queue_count_display} songs", value="\u200b", inline=False)
            embed.add_field(name="Song", value=f"``{song_title}``", inline=False)
            embed.add_field(name="Time", value=total_duration_str, inline=True)
            embed.add_field(name="Requested by", value=requester_display, inline=True)
            embed.add_field(name="Volume", value=volume_display, inline=True)
            embed.add_field(name="Channel", value=f"{voice_channel_mention}", inline=True) # <--- ฟิลด์ช่องเสียง
            embed.add_field(name="More", value=f"ติดตาม {self.bot.user.mention}!", inline=True) # <--- More inline
            # Optional: Add an empty inline field to balance layout if needed, or if you have an odd number of inlines
            # embed.add_field(name="\u200b", value="\u200b", inline=True) 
        else:
            embed.add_field(name=f"{bot_name} Music Room | No Playing", value="ไม่มีคิวเพลงที่กำลังเล่นอยู่ในขณะนี้. \n สามารถพิมพ์ ชื่อเพลง หรือ ลิงค์เพลงที่ห้องนี้ได้เลย", inline=False)
            embed.add_field(name="More", value=f"ติดตาม {self.bot.user.mention}!", inline=False)
        return embed

    # *** /setup-music ไม่ต้องรับ custom_default_image_url ***
    @app_commands.command(name="setup-music", description="สร้างช่องสำหรับสั่งเพลงและ Music Control Panel")
    @app_commands.checks.has_permissions(manage_channels=True, manage_messages=True, embed_links=True, read_message_history=True)
    async def setup_music_command(self, interaction: discord.Interaction): # ลบ custom_default_image_url ออก
        guild_id_str = str(interaction.guild.id); print(f"[SETUP DEBUG {guild_id_str}] Command received. Thinking...")
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if not self.music_cog: print(f"[SETUP DEBUG {guild_id_str}] MusicCog not ready."); return await interaction.followup.send("MusicCog ยังไม่พร้อม.", ephemeral=True)
        
        channel_name = "🎵jukebox-slime"; print(f"[SETUP DEBUG {guild_id_str}] Target channel name: {channel_name}")
        existing_channel_id = self.get_guild_setting(guild.id, "music_channel_id")
        music_channel: discord.TextChannel = guild.get_channel(existing_channel_id) if existing_channel_id else None
        
        if music_channel and music_channel.name != channel_name :
            print(f"[SETUP DEBUG {guild_id_str}] Existing channel '{music_channel.name}' name mismatch. Will create new '{channel_name}'.")
            music_channel = None; self.set_guild_setting(guild.id, "music_channel_id", None) # Clear old ID from settings
        
        if not music_channel:
            print(f"[SETUP DEBUG {guild_id_str}] No suitable existing channel. Attempting to create '{channel_name}'.")
            overwrites = {guild.default_role: discord.PermissionOverwrite(send_messages=True, read_messages=True, view_channel=True), guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True, embed_links=True, manage_messages=True, attach_files=True, read_message_history=True)}
            try:
                music_channel = await guild.create_text_channel(channel_name, overwrites=overwrites, topic="พิมพ์ชื่อเพลงหรือวางลิงก์ที่นี่เพื่อเล่นเพลง | Music Control Panel")
                self.set_guild_setting(guild.id, "music_channel_id", music_channel.id); print(f"[SETUP DEBUG {guild_id_str}] Channel '{channel_name}' created: {music_channel.id}")
            except discord.Forbidden: print(f"[SETUP DEBUG {guild_id_str}] Forbidden to create channel."); return await interaction.followup.send("บอทไม่มีสิทธิ์ในการสร้างช่อง.", ephemeral=True)
            except Exception as e: print(f"[SETUP DEBUG {guild_id_str}] Error creating channel: {e}"); return await interaction.followup.send(f"เกิดข้อผิดพลาดในการสร้างช่อง: {e}", ephemeral=True)
        else: print(f"[SETUP DEBUG {guild_id_str}] Using existing channel: {music_channel.name} ({music_channel.id})")
        
        # ไม่มีการตั้งค่า default_panel_image_url ใน guild_settings อีกต่อไป เพราะจะใช้ค่า hardcode
        # print(f"[SETUP DEBUG {guild_id_str}] Default panel image URL will be from hardcoded value.")
        
        old_panel_id = self.get_guild_setting(guild.id, "music_panel_message_id")
        if old_panel_id: # ... (ส่วนลบ panel เก่า เหมือนเดิม) ...
            print(f"[SETUP DEBUG {guild_id_str}] Attempting to delete old panel: {old_panel_id}")
            try:
                old_msg = await asyncio.wait_for(music_channel.fetch_message(old_panel_id), timeout=5.0)
                await old_msg.delete(); print(f"[SETUP DEBUG {guild_id_str}] Old panel deleted.")
            except asyncio.TimeoutError: print(f"[SETUP DEBUG {guild_id_str}] Timeout deleting old panel.")
            except (discord.NotFound, discord.Forbidden): print(f"[SETUP DEBUG {guild_id_str}] Old panel not found or no perm to delete.")
            except Exception as e_del: print(f"[SETUP DEBUG {guild_id_str}] Error deleting old panel: {e_del}")

        print(f"[SETUP DEBUG {guild_id_str}] Creating new embed panel...")
        try: # ... (ส่วนส่ง panel ใหม่ เหมือนเดิม + แก้ไขการส่ง followup) ...
            embed_to_send = await self.create_embed_panel(guild); print(f"[SETUP DEBUG {guild_id_str}] Embed created: {'Yes' if embed_to_send else 'No'}")
            view_to_send = MusicControllerView(self.music_cog, self, guild.id); print(f"[SETUP DEBUG {guild_id_str}] View created.")
            view_to_send.update_button_states(); print(f"[SETUP DEBUG {guild_id_str}] View buttons updated.")
            if embed_to_send:
                print(f"[SETUP DEBUG {guild_id_str}] Sending panel message to {music_channel.name}...")
                panel_message = await music_channel.send(content=None, embed=embed_to_send, view=view_to_send)
                print(f"[SETUP DEBUG {guild_id_str}] Panel message sent, ID: {panel_message.id}")
                self.set_guild_setting(guild.id, "music_panel_message_id", panel_message.id)
                view_to_send.message_id = panel_message.id; self.bot.add_view(view_to_send, message_id=panel_message.id)
                final_followup_message = f"Music Control Panel ถูกสร้าง/อัปเดตในช่อง {music_channel.mention} แล้ว."
                await interaction.followup.send(final_followup_message, ephemeral=True)
                print(f"[SETUP DEBUG {guild_id_str}] Followup sent.")
            else: 
                print(f"[SETUP DEBUG {guild_id_str}] Embed creation failed.")
                await interaction.followup.send("ไม่สามารถสร้าง Embed Panel ได้ (MusicCog อาจยังไม่พร้อม).", ephemeral=True)
        except Exception as e:
            print(f"[SETUP DEBUG {guild_id_str}] Exception during panel creation/sending: {e}"); traceback.print_exc()
            final_error_message = f"เกิดข้อผิดพลาดในการส่ง Music Panel: {e}"
            try: await interaction.edit_original_response(content=final_error_message)
            except discord.HTTPException:
                 try: await interaction.followup.send(final_error_message, ephemeral=True)
                 except discord.HTTPException: print(f"[SETUP DEBUG {guild_id_str}] Failed to send error followup after exception.")

    async def update_music_panel(self, guild_id: int): # ... (เหมือนเดิม) ...
        if not self.music_cog: print(f"UpdatePanel: MusicCog not ready for guild {guild_id}"); return
        guild = self.bot.get_guild(guild_id); 
        if not guild: print(f"UpdatePanel: Guild {guild_id} not found"); return
        channel_id = self.get_guild_setting(guild_id, "music_channel_id"); message_id = self.get_guild_setting(guild_id, "music_panel_message_id")
        if not channel_id or not message_id: print(f"UpdatePanel: Panel not setup for guild {guild_id}"); return
        music_channel = guild.get_channel(channel_id)
        if not music_channel: print(f"UpdatePanel: Music channel {channel_id} not found for guild {guild_id}"); return
        try:
            panel_message = await music_channel.fetch_message(message_id)
            new_embed = await self.create_embed_panel(guild)
            new_view = MusicControllerView(self.music_cog, self, guild_id)
            new_view.message_id = panel_message.id; new_view.update_button_states()
            if new_embed:
                await panel_message.edit(content=None, embed=new_embed, view=new_view)
                self.bot.add_view(new_view, message_id=panel_message.id) 
        except discord.NotFound:
            print(f"Music panel message (ID: {message_id}) not found in guild {guild_id}. Clearing setting.")
            self.set_guild_setting(guild_id, "music_panel_message_id", None) # Clear only message_id
            save_guild_settings(self.guild_settings) # Save the change
        except discord.Forbidden: print(f"Bot lacks permissions to edit the music panel in guild {guild_id}.")
        except Exception as e: print(f"Error updating music panel for guild {guild_id}: {e}")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message): # ... (เหมือนเดิม) ...
        if message.author.bot or not message.guild: return
        guild_id = message.guild.id; music_channel_id = self.get_guild_setting(guild_id, "music_channel_id")
        if not music_channel_id or message.channel.id != music_channel_id: return
        if not self.music_cog:
            try: await message.delete(); await message.channel.send("ระบบเพลงยังไม่พร้อม.", delete_after=7)
            except discord.HTTPException: pass; return
        query = message.content.strip()
        try: await message.delete()
        except discord.HTTPException: pass
        if not query: return
        if not message.author.voice or not message.author.voice.channel:
            try: await message.channel.send(f"{message.author.mention} คุณต้องอยู่ในช่องเสียงเพื่อเพิ่มเพลงค่ะ!", delete_after=10)
            except discord.HTTPException: pass; return
        print(f"MusicPanelCog: Detected query '{query}' in music channel for guild {guild_id} by {message.author.name}")
        try: await self.music_cog.add_to_queue_from_panel(message.guild, message.author, message.channel, query)
        except Exception as e: print(f"Error calling add_to_queue_from_panel from MusicPanelCog: {e}"); traceback.print_exc()

async def setup(bot: commands.Bot):
    if not bot.get_cog("MusicCog"):
        print("MusicPanelCog: MusicCog is not loaded. Music Panel may not function correctly until MusicCog is available.")
    await bot.add_cog(MusicPanelCog(bot))