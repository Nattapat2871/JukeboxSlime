# cogs/music_cog.py
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import math
import traceback
import json

YDL_OPTIONS_SINGLE_SONG = {
    'format': 'bestaudio/best', 
    'noplaylist': True, 
    'quiet': True, 
    'default_search': 'auto',
    'source_address': '0.0.0.0', 
    'extract_flat': False, 
    'forcejson': True,
    # 'dumpjson': True, 
}
YDL_OPTIONS_SEARCH = {
    'format': 'bestaudio/best',
    'quiet': True,
    'default_search': 'ytsearch1:', 
    'noplaylist': True, # Ensure ytsearch1: doesn't return a "playlist of one search result"
    'source_address': '0.0.0.0',
    'extract_flat': False, # Get full data for the first search result
    'forcejson': True,
}
YDL_OPTIONS_PLAYLIST_DETECTED = {
    'extract_flat': True, 
    'noplaylist': False, 
    'quiet': True,
    'source_address': '0.0.0.0',
    'forcejson': True,
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

class LoopMode:
    NONE = 0; SONG = 1; QUEUE = 2
    TEXT = {NONE: "ปิด", SONG: "เพลงเดียว", QUEUE: "ทั้งคิว"}

class MusicCog(commands.Cog, name="MusicCog"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot; self.voice_clients = {}; self.song_queue = {}; self.current_song = {}
        self.auto_leave_tasks = {}; self.playlist_processing_tasks = {}; self.active_playlist_summaries = {}
        self.loop_mode = {}; self.guild_volumes = {}; self.is_guild_muted = {}

    async def _call_panel_update(self, guild_id: int): # ... (เหมือนเดิม)
        try:
            music_panel_cog = self.bot.get_cog("MusicPanelCog")
            if music_panel_cog and hasattr(music_panel_cog, "update_music_panel"):
                self.bot.loop.create_task(music_panel_cog.update_music_panel(guild_id))
        except Exception as e: print(f"Error trying to call panel update for guild {guild_id}: {e}")
    def _get_song_queue(self, guild_id: int): # ... (เหมือนเดิม)
        if guild_id not in self.song_queue: self.song_queue[guild_id] = []
        return self.song_queue[guild_id]
    def _cleanup_guild_data(self, guild_id: int): # ... (เหมือนเดิม)
        if guild_id in self.voice_clients: del self.voice_clients[guild_id]
        if guild_id in self.song_queue: self.song_queue[guild_id].clear()
        if guild_id in self.current_song: self.current_song[guild_id] = None
        if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done(): self.auto_leave_tasks[guild_id].cancel()
        if guild_id in self.auto_leave_tasks: del self.auto_leave_tasks[guild_id]
        if self.playlist_processing_tasks.get(guild_id) and not self.playlist_processing_tasks[guild_id].done(): self.playlist_processing_tasks[guild_id].cancel()
        if guild_id in self.playlist_processing_tasks: del self.playlist_processing_tasks[guild_id]
        if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]
        if guild_id in self.loop_mode: del self.loop_mode[guild_id]
        if guild_id in self.is_guild_muted: del self.is_guild_muted[guild_id]
        print(f"Cleaned up music data for guild {guild_id}")
        self.bot.loop.create_task(self._call_panel_update(guild_id))
    async def _schedule_auto_leave(self, guild_or_ctx, delay: int, reason: str = "inactivity"): # ... (เหมือนเดิม)
        guild_id = guild_or_ctx.id if isinstance(guild_or_ctx, discord.Guild) else guild_or_ctx.guild.id
        if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done():
            self.auto_leave_tasks[guild_id].cancel(); 
            if guild_id in self.auto_leave_tasks: del self.auto_leave_tasks[guild_id]
        async def leave_task():
            await asyncio.sleep(delay)
            current_task_in_map = self.auto_leave_tasks.get(guild_id)
            if current_task_in_map != asyncio.current_task(): return
            vc = self.voice_clients.get(guild_id); queue = self._get_song_queue(guild_id)
            if vc and vc.is_connected():
                is_looping_queue_and_empty = (self.loop_mode.get(guild_id, LoopMode.NONE) == LoopMode.QUEUE and not queue)
                if not vc.is_playing() and not vc.is_paused() and not queue and not is_looping_queue_and_empty :
                    message_on_leave = f"🎵 ออกจากช่องเสียงเนื่องจาก {reason} เป็นเวลา {delay} วินาที"
                    if reason == "queue_empty": message_on_leave = f"🎵 คิวเพลงว่างเป็นเวลา {delay} วินาที จึงออกจากช่องเสียง"
                    channel_to_send = None
                    if isinstance(guild_or_ctx, commands.Context) and guild_or_ctx.channel and hasattr(guild_or_ctx.channel, 'send'): channel_to_send = guild_or_ctx.channel
                    elif isinstance(guild_or_ctx, discord.Guild):
                        guild = guild_or_ctx
                        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages: channel_to_send = guild.system_channel
                    if channel_to_send:
                        try: await channel_to_send.send(message_on_leave, delete_after=30)
                        except discord.HTTPException: print(f"Failed to send auto-leave message to channel in guild {guild_id}")
                    else: print(f"Bot auto-disconnected from guild {guild_id} due to {reason}. (No suitable ctx/channel to send message)")
                    await vc.disconnect()
                else: print(f"Auto-leave for guild {guild_id} ({reason}) aborted: Conditions no longer met.")
            if guild_id in self.auto_leave_tasks and self.auto_leave_tasks.get(guild_id) == asyncio.current_task(): del self.auto_leave_tasks[guild_id]
        new_task = self.bot.loop.create_task(leave_task()); self.auto_leave_tasks[guild_id] = new_task
    async def _play_next(self, guild_id: int, text_channel_for_notif: discord.TextChannel = None, silent_mode: bool = False): # ... (เหมือนเดิม)
        queue = self._get_song_queue(guild_id); vc = self.voice_clients.get(guild_id)
        current_loop_mode = self.loop_mode.get(guild_id, LoopMode.NONE); song_that_just_finished = self.current_song.get(guild_id)
        if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done():
            self.auto_leave_tasks[guild_id].cancel()
            if guild_id in self.auto_leave_tasks: del self.auto_leave_tasks[guild_id]
        if not vc or not vc.is_connected():
            self.current_song[guild_id] = None
            if not queue and not self.active_playlist_summaries.get(guild_id) and not silent_mode and text_channel_for_notif:
                await text_channel_for_notif.send("🎶 **ไม่มีเพลงในคิวแล้ว** และบอทไม่ได้อยู่ในช่องเสียง", delete_after=15)
            await self._call_panel_update(guild_id); return
        if song_that_just_finished:
            if current_loop_mode == LoopMode.SONG: queue.insert(0, song_that_just_finished)
            elif current_loop_mode == LoopMode.QUEUE: queue.append(song_that_just_finished)
        if not queue:
            self.current_song[guild_id] = None
            if not self.active_playlist_summaries.get(guild_id) and not silent_mode and text_channel_for_notif:
                 await text_channel_for_notif.send("🎶 **ไม่มีเพลงในคิวแล้ว**", delete_after=15)
            if vc and vc.is_connected() and current_loop_mode != LoopMode.QUEUE :
                 await self._schedule_auto_leave(vc.guild, delay=60, reason="queue_empty")
            await self._call_panel_update(guild_id); return
        if vc.is_playing() or vc.is_paused(): return
        song_info = queue.pop(0); self.current_song[guild_id] = song_info
        class MinimalCtxForAfter:
            def __init__(self, bot, guild, channel): self.bot = bot; self.guild = guild; self.channel = channel
        fake_after_ctx = MinimalCtxForAfter(self.bot, vc.guild, text_channel_for_notif)
        try:
            audio_source_url = song_info['stream_url']
            guild_volume_settings = self.guild_volumes.get(guild_id, {}) 
            current_volume_float = guild_volume_settings.get('current', 0.7)
            volume_to_apply = 0.0 if self.is_guild_muted.get(guild_id, False) else current_volume_float
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(audio_source_url, **FFMPEG_OPTIONS), volume=volume_to_apply)
            vc.play(source, after=lambda e: self.bot.loop.create_task(self._check_after_play(fake_after_ctx, guild_id, text_channel_for_notif, silent_mode, e)))
            if not silent_mode and text_channel_for_notif:
                try: await text_channel_for_notif.send(f"🎶 กำลังเล่น: **{song_info['title']}**", delete_after=song_info.get('duration', 600))
                except discord.HTTPException as e: print(f"Failed to send 'Now playing' message to {text_channel_for_notif.name}: {e}")
            await self._call_panel_update(guild_id)
        except Exception as e:
            print(f"Error in _play_next trying to play {song_info.get('title', 'Unknown')}: {e}"); traceback.print_exc()
            if not silent_mode and text_channel_for_notif:
                try: await text_channel_for_notif.send(f"เกิดข้อผิดพลาดในการเล่นเพลง: {e}", delete_after=10)
                except discord.HTTPException as he: print(f"Failed to send error message in _play_next: {he}")
            self.current_song[guild_id] = None; await self._call_panel_update(guild_id)
            self.bot.loop.create_task(self._play_next(guild_id, text_channel_for_notif, silent_mode))
    async def _check_after_play(self, ctx_like_object, guild_id: int, text_channel_for_notif: discord.TextChannel = None, silent_mode: bool = False, error_obj=None): # ... (เหมือนเดิม)
        if error_obj:
            print(f"!!! Player event/error in guild {guild_id} !!!"); print(f"    Error Object (str): {str(error_obj)}"); print(f"    Error Object (repr): {repr(error_obj)}"); print(f"    Error Object (type): {type(error_obj)}")
            error_message_to_send = str(error_obj).strip()
            user_facing_error_message = f"เกิดเหตุขัดข้องเล็กน้อยระหว่างเล่นเพลง ({error_message_to_send})" if error_message_to_send and error_message_to_send.lower() != "none" else "เกิดเหตุขัดข้องเล็กน้อยระหว่างเล่นเพลง"
            if not silent_mode:
                channel_to_notify = text_channel_for_notif if text_channel_for_notif else (ctx_like_object.channel if ctx_like_object and hasattr(ctx_like_object, 'channel') and ctx_like_object.channel else None)
                if channel_to_notify:
                    try: await channel_to_notify.send(user_facing_error_message, delete_after=10)
                    except discord.HTTPException as e_send: print(f"Error sending player error/event message to Discord: {e_send}")
        await self._play_next(guild_id, text_channel_for_notif, silent_mode)
    async def _fetch_song_data(self, query_or_url: str, ydl_opts: dict): # ... (เหมือนเดิม)
        loop = asyncio.get_event_loop(); 
        try:
            print(f"[YTDL_FETCH] Query: '{query_or_url}', Opts: extract_flat={ydl_opts.get('extract_flat')}, default_search={ydl_opts.get('default_search')}")
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(query_or_url, download=False))
            return data
        except Exception as e: print(f"YTDL Error for query '{query_or_url}': {e}"); traceback.print_exc(); raise
    async def _process_playlist_entries_background(self, guild_id: int, member_who_requested: discord.Member, text_channel_for_reply: discord.TextChannel, original_playlist_title: str, silent_mode: bool = False): # ... (เหมือนเดิม + แก้ไขการดึง stream URL)
        playlist_summary_data = self.active_playlist_summaries.get(guild_id)
        if not playlist_summary_data or not playlist_summary_data['entries']:
            if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]; return
        entries_to_process = list(playlist_summary_data['entries']); queue = self._get_song_queue(guild_id); songs_added_count = 0
        current_processing_task = self.playlist_processing_tasks.get(guild_id)
        if current_processing_task != asyncio.current_task(): return
        print(f"Background processing starting for playlist '{original_playlist_title}' in guild {guild_id} with {len(entries_to_process)} entries.")
        for i, entry_summary in enumerate(entries_to_process):
            if guild_id not in self.voice_clients or asyncio.current_task().cancelled():
                if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]
                print(f"Playlist processing for '{original_playlist_title}' stopped or cancelled early."); return
            video_url_from_summary = entry_summary.get('url'); video_title_summary = entry_summary.get('title', f"เพลงที่ {i + 1 + len(queue)} จาก '{original_playlist_title}'")
            if not video_url_from_summary: continue
            try:
                song_data = await self._fetch_song_data(video_url_from_summary, YDL_OPTIONS_SINGLE_SONG)
                if not song_data: print(f"[YTDL_DEBUG BG] No song_data for {video_title_summary} ({video_url_from_summary})"); continue
                stream_url = song_data.get('url')
                if not stream_url:
                    formats = song_data.get('formats', []); selected_format = None
                    for f_data in formats:
                        if f_data.get('acodec') and f_data.get('acodec') != 'none' and f_data.get('url'):
                            if f_data.get('vcodec') == 'none' or not f_data.get('vcodec'): selected_format = f_data; break
                            if not selected_format: selected_format = f_data
                    if selected_format: stream_url = selected_format.get('url')
                if stream_url:
                    song_info = {'title': song_data.get('title', video_title_summary), 'stream_url': stream_url, 'webpage_url': song_data.get('webpage_url', video_url_from_summary), 'duration': song_data.get('duration', 0), 'uploader': song_data.get('uploader', 'Unknown Uploader'), 'requester': member_who_requested, 'thumbnail': song_data.get('thumbnail')}
                    queue.append(song_info); songs_added_count += 1
                    active_entries_list = self.active_playlist_summaries.get(guild_id, {}).get('entries', [])
                    entry_id_to_remove = entry_summary.get('id'); url_to_remove = entry_summary.get('url')
                    for idx, summ_entry in enumerate(active_entries_list):
                        if (entry_id_to_remove and summ_entry.get('id') == entry_id_to_remove) or \
                           (not entry_id_to_remove and summ_entry.get('url') == url_to_remove):
                            active_entries_list.pop(idx); break 
                    await self._call_panel_update(guild_id)
                else: print(f"[YTDL_DEBUG BG] Could not get stream URL for {video_title_summary} ({video_url_from_summary}) even after checking formats.")
            except Exception as e: print(f"Error processing playlist entry {video_title_summary} ({video_url_from_summary}): {e}"); traceback.print_exc()
            await asyncio.sleep(0.1)
        if songs_added_count > 0 and not silent_mode and text_channel_for_reply:
            try: await text_channel_for_reply.send(f"✅ เพลงที่เหลือจากเพลย์ลิสต์ **'{original_playlist_title}'** ({songs_added_count} เพลง) ถูกเพิ่มเข้าคิวแล้ว", delete_after=15)
            except discord.HTTPException: pass
        if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]
        if self.playlist_processing_tasks.get(guild_id) == asyncio.current_task(): del self.playlist_processing_tasks[guild_id]
        print(f"Finished background processing for playlist '{original_playlist_title}' in guild {guild_id}.")
        await self._call_panel_update(guild_id)

    async def _process_and_play_query(self, guild: discord.Guild, member: discord.Member, text_channel: discord.TextChannel, voice_channel: discord.VoiceChannel, query: str, processing_msg: discord.Message = None, silent_mode: bool = False):
        guild_id = guild.id
        current_vc = self.voice_clients.get(guild_id)

        # ... (ส่วนเชื่อมต่อ VC และ cancel auto-leave เหมือนเดิม) ...
        if not current_vc or not current_vc.is_connected() or current_vc.channel != voice_channel:
            if current_vc and current_vc.is_connected(): await current_vc.move_to(voice_channel)
            else:
                try: current_vc = await voice_channel.connect(); self.voice_clients[guild_id] = current_vc
                except Exception as e:
                    err_msg = f"ไม่สามารถเข้าร่วมช่องเสียง: {e}"
                    if not silent_mode:
                        if processing_msg: await processing_msg.edit(content=err_msg)
                        else: await text_channel.send(err_msg, delete_after=10)
                    return
        
        if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done():
            self.auto_leave_tasks[guild_id].cancel(); 
            if guild_id in self.auto_leave_tasks: del self.auto_leave_tasks[guild_id]

        try:
            print(f"[PROCESS_QUERY {guild_id}] Initial query: '{query}' by {member.name}")
            is_url = query.startswith(('http://', 'https://', 'www.'))
            
            first_song_to_play_data = None # This will store the FULL data for the first song
            is_playlist = False
            playlist_entries_summary = []
            playlist_title = ""

            # Cleanup previous playlist tasks for this guild first
            if self.active_playlist_summaries.get(guild_id): del self.active_playlist_summaries[guild_id]
            if self.playlist_processing_tasks.get(guild_id):
                if not self.playlist_processing_tasks[guild_id].done(): self.playlist_processing_tasks[guild_id].cancel()
                if guild_id in self.playlist_processing_tasks: del self.playlist_processing_tasks[guild_id]

            if is_url:
                print(f"[PROCESS_QUERY {guild_id}] Query is URL. Detecting playlist: {query}")
                playlist_check_data = await self._fetch_song_data(query, YDL_OPTIONS_PLAYLIST_DETECTED)
                if playlist_check_data and playlist_check_data.get('_type') == 'playlist' and 'entries' in playlist_check_data and playlist_check_data['entries']:
                    is_playlist = True
                    playlist_entries_summary = playlist_check_data.get('entries', [])
                    playlist_title = playlist_check_data.get('title', query)
                    print(f"[PROCESS_QUERY {guild_id}] Playlist detected. Title: '{playlist_title}', Entries: {len(playlist_entries_summary)}")
                    
                    first_entry_summary = playlist_entries_summary[0]
                    first_song_webpage_url = first_entry_summary.get('url') 
                    if first_song_webpage_url:
                        print(f"[PROCESS_QUERY {guild_id}] Fetching full data for first playlist song: {first_song_webpage_url}")
                        first_song_to_play_data = await self._fetch_song_data(first_song_webpage_url, YDL_OPTIONS_SINGLE_SONG)
                    else: # Error case
                        # ... (error handling for missing URL in first playlist entry)
                        err_msg = f"เพลงแรกในเพลย์ลิสต์ `{playlist_title}` ไม่มีข้อมูล URL"
                        if not silent_mode:
                            if processing_msg: await processing_msg.edit(content=err_msg)
                            else: await text_channel.send(err_msg, delete_after=10)
                        return # No need to cleanup active_playlist_summaries as it's not set yet for this path
                else: # URL is not a playlist, treat as a single song URL
                    is_playlist = False
                    print(f"[PROCESS_QUERY {guild_id}] URL is not a playlist. Fetching full data for single song URL: {query}")
                    first_song_to_play_data = await self._fetch_song_data(query, YDL_OPTIONS_SINGLE_SONG)
            else: # Query is not a URL, so it's a search term
                print(f"[PROCESS_QUERY {guild_id}] Query is a search term. Searching: '{query}'")
                # YDL_OPTIONS_SEARCH should return full data for the first search result
                # because extract_flat=False
                searched_data = await self._fetch_song_data(query, YDL_OPTIONS_SEARCH)
                
                if searched_data and searched_data.get('_type') == 'playlist' and 'entries' in searched_data and searched_data['entries']:
                    # This happens if ytsearch1 actually returns a playlist (e.g. "Artist - Topic" channels)
                    is_playlist = True
                    playlist_entries_summary = searched_data.get('entries', [])
                    playlist_title = searched_data.get('title', query)
                    print(f"[PROCESS_QUERY {guild_id}] Search result IS a playlist. Title: '{playlist_title}', Entries: {len(playlist_entries_summary)}")
                    
                    first_entry_summary = playlist_entries_summary[0]
                    first_song_webpage_url = first_entry_summary.get('url')
                    if first_song_webpage_url:
                        first_song_to_play_data = await self._fetch_song_data(first_song_webpage_url, YDL_OPTIONS_SINGLE_SONG)
                    else: # Error case
                        err_msg = f"เพลงแรกในเพลย์ลิสต์ที่ค้นเจอ `{playlist_title}` ไม่มี URL"
                        # ... (send error) ...
                        if not silent_mode:
                            if processing_msg: await processing_msg.edit(content=err_msg)
                            else: await text_channel.send(err_msg, delete_after=10)
                        return
                elif searched_data: # Search result is a single video, searched_data IS first_song_to_play_data
                    print(f"[PROCESS_QUERY {guild_id}] Search result is single video: '{searched_data.get('title', 'N/A')}'")
                    first_song_to_play_data = searched_data # <--- ใช้ข้อมูลนี้โดยตรง
                else: # Search found nothing
                    err_msg = f"ไม่พบผลลัพธ์สำหรับ: `{query}`"
                    if not silent_mode:
                        if processing_msg: await processing_msg.edit(content=err_msg)
                        else: await text_channel.send(err_msg, delete_after=10)
                    return

            if not first_song_to_play_data:
                err_msg = f"ไม่สามารถดึงข้อมูลเพลงสำหรับ: `{query}` (final check after processing logic)"
                if not silent_mode:
                    if processing_msg: await processing_msg.edit(content=err_msg)
                    else: await text_channel.send(err_msg, delete_after=10)
                # No active_playlist_summaries to clean if first_song_to_play_data is None here without being a playlist before
                return
            
            # --- DEBUG PRINT FOR THE FINAL DATA ---
            print(f"\n[YTDL_FINAL_DATA for '{first_song_to_play_data.get('title', query)}'] ----")
            # print(json.dumps(first_song_to_play_data, indent=2, ensure_ascii=False)) # Uncomment for full JSON
            print(f"  Title: {first_song_to_play_data.get('title')}")
            print(f"  Duration: {first_song_to_play_data.get('duration')}")
            print(f"  Thumbnail: {first_song_to_play_data.get('thumbnail')}")
            print(f"  Webpage URL: {first_song_to_play_data.get('webpage_url')}")
            print(f"  Original URL (if from ytsearch): {first_song_to_play_data.get('original_url')}")
            print(f"  Top-level URL (stream or manifest): {first_song_to_play_data.get('url')}")
            print(f"  Formats available: {len(first_song_to_play_data.get('formats', [])) > 0}")
            print("---- END YTDL_FINAL_DATA ----\n")
            # --- END DEBUG PRINT ---

            stream_url = first_song_to_play_data.get('url') 
            extracted_title = first_song_to_play_data.get('title', 'Untitled Song')
            if not extracted_title or extracted_title.lower() == 'videoplayback' or "video playback" in extracted_title.lower():
                if not is_url: extracted_title = query # Use search query as title if yt-dlp title is bad
            
            if not stream_url:
                print(f"[YTDL_DEBUG {guild_id}] No top-level 'url' for '{extracted_title}'. Trying 'formats'.")
                formats = first_song_to_play_data.get('formats', [])
                if not formats: print(f"[YTDL_DEBUG {guild_id}] 'formats' list is empty for '{extracted_title}'.")
                selected_format = None
                for f_data in formats:
                    if f_data.get('acodec') and f_data.get('acodec') != 'none' and f_data.get('url'):
                        if f_data.get('vcodec') == 'none' or not f_data.get('vcodec'): selected_format = f_data; print(f"[YTDL_DEBUG {guild_id}] Selected audio-only format: id={f_data.get('format_id')}"); break 
                        if not selected_format: selected_format = f_data; print(f"[YTDL_DEBUG {guild_id}] Tentatively selected audio format: id={f_data.get('format_id')}")
                if selected_format: stream_url = selected_format.get('url')
                else: print(f"[YTDL_DEBUG {guild_id}] No suitable format in 'formats' for '{extracted_title}'.")
            
            if not stream_url:
                err_msg = f"ไม่สามารถรับ URL สตรีมสำหรับเพลง: ``{extracted_title}``"
                if not silent_mode:
                    if processing_msg: await processing_msg.edit(content=err_msg)
                    else: await text_channel.send(err_msg, delete_after=10)
                if is_playlist and guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id] # Clear if playlist was set
                return

            thumbnail_url = first_song_to_play_data.get('thumbnail')
            if not thumbnail_url:
                thumbnails_list = first_song_to_play_data.get('thumbnails', [])
                if thumbnails_list: thumbnail_url = thumbnails_list[-1].get('url')
            
            # webpage_url should be from the full data, not from a potentially direct stream URL
            final_webpage_url = first_song_to_play_data.get('webpage_url', first_song_to_play_data.get('original_url'))
            if not final_webpage_url and is_url: # If original query was a URL, use that as webpage_url
                final_webpage_url = query
            elif not final_webpage_url and not is_url: # If original query was search term, we might not have a good webpage_url yet from search data alone
                 # This case needs yt-dlp search to reliably return 'webpage_url' or 'original_url' for the found video
                 print(f"[WARNING {guild_id}] Webpage URL might be missing for search query '{query}' if not in YTDL result.")


            first_song_info = {
                'title': extracted_title, 
                'stream_url': stream_url, 
                'webpage_url': final_webpage_url,
                'duration': first_song_to_play_data.get('duration', 0), 
                'uploader': first_song_to_play_data.get('uploader', 'Unknown Uploader'), 
                'requester': member, 
                'thumbnail': thumbnail_url
            }
            current_song_queue = self._get_song_queue(guild_id); current_song_queue.append(first_song_info)
            
            if is_playlist: # If it was determined to be a playlist earlier
                self.active_playlist_summaries[guild_id] = {'title': playlist_title, 'entries': list(playlist_entries_summary), 'requester': member}
                first_entry_summary_to_remove = playlist_entries_summary[0]
                active_entries = self.active_playlist_summaries[guild_id]['entries']
                if active_entries:
                    entry_id_to_remove = first_entry_summary_to_remove.get('id'); url_to_remove = first_entry_summary_to_remove.get('url')
                    for idx, summ_entry in enumerate(active_entries):
                        if (entry_id_to_remove and summ_entry.get('id') == entry_id_to_remove) or \
                           (not entry_id_to_remove and summ_entry.get('url') == url_to_remove):
                            active_entries.pop(idx); break
            
            msg_to_user = f"▶️ กำลังจะเล่นเพลงแรกจากเพลย์ลิสต์ **'{playlist_title}'** ({len(playlist_entries_summary)} เพลง)..." if is_playlist else f"✅ เพิ่มเข้าคิว: **{first_song_info['title']}**"
            if not silent_mode:
                if processing_msg: await processing_msg.edit(content=msg_to_user)
                else: await text_channel.send(msg_to_user, delete_after=20 if is_playlist else 10)
            
            await self._call_panel_update(guild_id)
            if not current_vc.is_playing() and not current_vc.is_paused(): await self._play_next(guild_id, text_channel, silent_mode)
            
            if is_playlist and self.active_playlist_summaries.get(guild_id) and self.active_playlist_summaries[guild_id]['entries']:
                new_processing_task = self.bot.loop.create_task(self._process_playlist_entries_background(guild_id, member, text_channel, playlist_title, silent_mode))
                self.playlist_processing_tasks[guild_id] = new_processing_task
            elif is_playlist: 
                 if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]
                 await self._call_panel_update(guild_id)

        except yt_dlp.utils.DownloadError as e:
            # ... (error handling เหมือนเดิม) ...
            error_lines = str(e).splitlines(); relevant_error = error_lines[-1] if error_lines else str(e)
            if "is not a valid URL" in relevant_error and "ytsearch" not in query.lower() and not query.startswith(('http','www')): relevant_error = f"ไม่พบผลลัพธ์สำหรับ '{query}'"
            err_msg = f"YTDL Error: {relevant_error}"
            if not silent_mode:
                if processing_msg: await processing_msg.edit(content=err_msg)
                else: await text_channel.send(err_msg, delete_after=10)
            if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]; await self._call_panel_update(guild_id)
        except Exception as e:
            # ... (error handling เหมือนเดิม) ...
            err_msg = f"เกิดข้อผิดพลาดทั่วไป: {type(e).__name__} - {e}"
            if not silent_mode:
                if processing_msg: await processing_msg.edit(content=err_msg)
                else: await text_channel.send(err_msg, delete_after=10)
            print(f"Generic error in _process_and_play_query for guild {guild_id} on query '{query}': {e}"); traceback.print_exc()
            if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]; await self._call_panel_update(guild_id)

    # ... (โค้ด Listener on_voice_state_update และ Commands อื่นๆ ทั้งหมดเหมือนเดิมจาก request_25) ...
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild_id = member.guild.id; vc = member.guild.voice_client
        if member.id == self.bot.user.id:
            if before.channel and not after.channel: self._cleanup_guild_data(guild_id); return
            elif after.channel:
                self.voice_clients[guild_id] = vc
                if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done():
                    self.auto_leave_tasks[guild_id].cancel(); 
                    if guild_id in self.auto_leave_tasks: del self.auto_leave_tasks[guild_id]
                await self._call_panel_update(guild_id)
        if vc and vc.is_connected() and before.channel == vc.channel:
            if len(vc.channel.members) == 1 and vc.channel.members[0] == self.bot.user:
                queue = self._get_song_queue(guild_id)
                if not vc.is_playing() and not vc.is_paused() and not queue and self.loop_mode.get(guild_id, LoopMode.NONE) == LoopMode.NONE :
                    await self._schedule_auto_leave(member.guild, delay=60, reason="alone_and_idle")
    
    # --- COMMANDS ---
    @commands.command(name="play", aliases=['p'], help="เล่นเพลง")
    async def play(self, ctx: commands.Context, *, query: str = None):
        if not ctx.author.voice or not ctx.author.voice.channel: return await ctx.send("คุณต้องอยู่ในช่องเสียงก่อน")
        voice_channel = ctx.author.voice.channel; guild_id = ctx.guild.id
        current_vc = self.voice_clients.get(guild_id)
        if query is None:
            queue = self._get_song_queue(guild_id)
            if current_vc and current_vc.is_connected():
                if not queue and (not current_vc.is_playing() and not current_vc.is_paused()): return await ctx.send("กรุณาระบุชื่อเพลง/URL")
                elif current_vc.is_paused(): await self.resume(ctx); return 
                elif not current_vc.is_playing() and not current_vc.is_paused() and queue: await self._play_next(guild_id, ctx.channel, silent_mode=False); return
                else: return await ctx.send("กรุณาระบุชื่อเพลง/URL เพื่อเพิ่มเข้าคิว หรือ `s!resume`")
            else: return await ctx.send("กรุณาระบุชื่อเพลง/URL เพื่อให้บอทเข้าร่วมและเล่น")
        processing_msg = await ctx.send(f"🔎 กำลังประมวลผล: `{query}`...")
        await self._process_and_play_query(ctx.guild, ctx.author, ctx.channel, voice_channel, query, processing_msg, silent_mode=False)

    async def add_to_queue_from_panel(self, guild: discord.Guild, member: discord.Member, text_channel_for_reply: discord.TextChannel, query: str):
        if not member.voice or not member.voice.channel:
            try: await text_channel_for_reply.send(f"{member.mention} คุณต้องอยู่ในช่องเสียงก่อนสั่งเพลงจากช่องนี้", delete_after=10)
            except discord.HTTPException: pass; return
        voice_channel = member.voice.channel
        print(f"Panel request: User {member.display_name}, Query: {query} in guild {guild.id}")
        await self._process_and_play_query(guild, member, text_channel_for_reply, voice_channel, query, processing_msg=None, silent_mode=True)

    @commands.command(name="join", help="ให้บอทเข้าร่วมช่องเสียงที่คุณอยู่")
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel: return await ctx.send(f"{ctx.author.name} ไม่ได้อยู่ในช่องเสียงใดๆ")
        channel = ctx.author.voice.channel; guild_id = ctx.guild.id; current_vc = self.voice_clients.get(guild_id)
        if current_vc and current_vc.is_connected():
            if current_vc.channel == channel: return await ctx.send("บอทอยู่ในช่องเสียงนี้แล้ว", delete_after=10)
            try: await current_vc.move_to(channel); self.voice_clients[guild_id] = current_vc
            except asyncio.TimeoutError: return await ctx.send("การย้ายช่องหมดเวลา", delete_after=10)
            await ctx.send(f"ย้ายไปที่ช่อง: {channel.name}", delete_after=10)
        else:
            try: vc = await channel.connect(); self.voice_clients[guild_id] = vc; await ctx.send(f"เข้าร่วมช่อง: {channel.name}", delete_after=10)
            except asyncio.TimeoutError: return await ctx.send("การเข้าร่วมช่องหมดเวลา", delete_after=10)
            except Exception as e: return await ctx.send(f"เกิดข้อผิดพลาดในการเข้าร่วมช่องเสียง: {e}", delete_after=10)
        if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done():
            self.auto_leave_tasks[guild_id].cancel(); 
            if guild_id in self.auto_leave_tasks: del self.auto_leave_tasks[guild_id]
        await self._call_panel_update(guild_id)

    @commands.command(name="leave", aliases=['disconnect', 'dc'], help="ให้บอทออกจากช่องเสียง")
    async def leave(self, ctx: commands.Context):
        guild_id = ctx.guild.id; vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected():
            if vc.is_playing() or vc.is_paused(): vc.stop()
            if self.playlist_processing_tasks.get(guild_id) and not self.playlist_processing_tasks[guild_id].done(): self.playlist_processing_tasks[guild_id].cancel()
            if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done(): self.auto_leave_tasks[guild_id].cancel()
            await vc.disconnect(); await ctx.send("ออกจากช่องเสียงแล้ว", delete_after=10)
        else: await ctx.send("บอทไม่ได้อยู่ในช่องเสียงใดๆ", delete_after=10)

    async def player_pause(self, guild_id: int):
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_playing(): vc.pause(); await self._call_panel_update(guild_id); return "⏸️ หยุดเพลงชั่วคราวแล้ว"
        return "ไม่มีเพลงกำลังเล่นอยู่"
    @commands.command(name="pause", help="หยุดเล่นเพลงชั่วคราว")
    async def pause(self, ctx: commands.Context): msg = await self.player_pause(ctx.guild.id); await ctx.send(msg, delete_after=10)

    async def player_resume(self, guild_id: int):
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_paused():
            if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done():
                self.auto_leave_tasks[guild_id].cancel()
                if guild_id in self.auto_leave_tasks: del self.auto_leave_tasks[guild_id]
            vc.resume(); await self._call_panel_update(guild_id); return "▶️ เล่นเพลงต่อแล้ว"
        return "ไม่มีเพลงที่หยุดพักไว้"
    @commands.command(name="resume", help="เล่นเพลงต่อจากที่หยุดไว้")
    async def resume(self, ctx: commands.Context): msg = await self.player_resume(ctx.guild.id); await ctx.send(msg, delete_after=10)

    async def player_stop(self, guild_id: int):
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected():
            if vc.is_playing() or vc.is_paused(): vc.stop()
            if guild_id in self.song_queue: self.song_queue[guild_id].clear()
            self.current_song[guild_id] = None
            if self.playlist_processing_tasks.get(guild_id) and not self.playlist_processing_tasks[guild_id].done(): self.playlist_processing_tasks[guild_id].cancel()
            if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]
            self.loop_mode[guild_id] = LoopMode.NONE
            await self._call_panel_update(guild_id)
            guild = self.bot.get_guild(guild_id)
            if guild: await self._schedule_auto_leave(guild, delay=60, reason="stopped_via_panel")
            return "⏹️ หยุดเล่นเพลงและล้างคิวแล้ว"
        return "บอทไม่ได้อยู่ในช่องเสียง"
    @commands.command(name="stop", help="หยุดเล่นเพลงและล้างคิว")
    async def stop(self, ctx: commands.Context): msg = await self.player_stop(ctx.guild.id); await ctx.send(msg, delete_after=10)

    async def player_skip(self, guild_id: int):
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected() and (vc.is_playing() or vc.is_paused()):
            if self.auto_leave_tasks.get(guild_id) and not self.auto_leave_tasks[guild_id].done():
                self.auto_leave_tasks[guild_id].cancel()
                if guild_id in self.auto_leave_tasks: del self.auto_leave_tasks[guild_id]
            skipped_song_title = self.current_song.get(guild_id, {}).get('title', 'เพลงปัจจุบัน')
            vc.stop() 
            return f"⏭️ ข้ามเพลง: **{skipped_song_title}**"
        return "ไม่มีเพลงกำลังเล่นอยู่ที่จะข้ามได้"
    @commands.command(name="skip", aliases=['s'], help="ข้ามไปยังเพลงถัดไปในคิว")
    async def skip(self, ctx: commands.Context): msg = await self.player_skip(ctx.guild.id); await ctx.send(msg, delete_after=10)

    @commands.command(name="loop", aliases=['l'], help="เปลี่ยนโหมดการเล่นวน (ปิด -> เพลงเดียว -> ทั้งคิว)")
    async def loop(self, ctx: commands.Context):
        _ , new_mode_text = await self.player_toggle_loop(ctx.guild.id)
        await ctx.send(f"🔁 {new_mode_text}", delete_after=10)

    async def player_toggle_loop(self, guild_id: int) -> tuple[int, str]:
        current_mode = self.loop_mode.get(guild_id, LoopMode.NONE)
        if current_mode == LoopMode.NONE: new_mode = LoopMode.SONG
        elif current_mode == LoopMode.SONG: new_mode = LoopMode.QUEUE
        else: new_mode = LoopMode.NONE
        self.loop_mode[guild_id] = new_mode
        print(f"Guild {guild_id} loop mode set to {LoopMode.TEXT[new_mode]}")
        await self._call_panel_update(guild_id)
        return new_mode, f"โหมดเล่นวน: {LoopMode.TEXT[new_mode]}"

    async def player_toggle_mute(self, guild_id: int) -> tuple[bool, str]:
        vc = self.voice_clients.get(guild_id)
        if guild_id not in self.guild_volumes: self.guild_volumes[guild_id] = {'current': 0.7}
        current_mute_state = self.is_guild_muted.get(guild_id, False); new_mute_state = not current_mute_state
        self.is_guild_muted[guild_id] = new_mute_state; volume_to_apply_after_toggle = 0.0
        if vc and vc.source and hasattr(vc.source, 'volume'):
            if new_mute_state: self.guild_volumes[guild_id]['before_mute_volume'] = vc.source.volume; volume_to_apply_after_toggle = 0.0
            else: volume_to_apply_after_toggle = self.guild_volumes[guild_id].get('before_mute_volume', self.guild_volumes[guild_id].get('current',0.7))
            vc.source.volume = volume_to_apply_after_toggle
        elif new_mute_state: self.guild_volumes[guild_id]['before_mute_volume'] = self.guild_volumes[guild_id].get('current', 0.7)
        print(f"Guild {guild_id} mute state set to {new_mute_state}")
        await self._call_panel_update(guild_id)
        return new_mute_state, "🔇 ปิดเสียงแล้ว" if new_mute_state else "🔊 เปิดเสียงแล้ว"

    async def player_adjust_volume(self, guild_id: int, adjustment_percentage: int) -> tuple[int, str]:
        vc = self.voice_clients.get(guild_id)
        if guild_id not in self.guild_volumes: self.guild_volumes[guild_id] = {'current': 0.7}
        current_logical_volume = self.guild_volumes[guild_id].get('current', 0.7)
        new_logical_volume = current_logical_volume + (adjustment_percentage / 100.0)
        new_logical_volume = max(0.0, min(2.0, new_logical_volume))
        self.guild_volumes[guild_id]['current'] = new_logical_volume; volume_to_apply = new_logical_volume
        if self.is_guild_muted.get(guild_id, False):
            self.guild_volumes[guild_id]['before_mute_volume'] = new_logical_volume; volume_to_apply = 0.0
        if vc and vc.source and hasattr(vc.source, 'volume'): vc.source.volume = volume_to_apply
        new_vol_percent = int(new_logical_volume * 100)
        vol_text = f"🔊 ความดัง: {new_vol_percent}%" if not self.is_guild_muted.get(guild_id,False) else f"🔇 ปิดเสียง (ความดังที่ตั้งค่าไว้: {new_vol_percent}%)"
        print(f"Guild {guild_id} logical volume set to {new_vol_percent}%, applied {int(volume_to_apply*100)}%")
        await self._call_panel_update(guild_id); return new_vol_percent, vol_text

    @commands.command(name="queue", aliases=['q'], help="แสดงรายการเพลงในคิว")
    async def queue_command(self, ctx: commands.Context):
        guild_id = ctx.guild.id; processed_song_queue = self._get_song_queue(guild_id); current_song_data = self.current_song.get(guild_id)
        current_song_field_text = None
        if current_song_data: current_song_field_text = f"**``{current_song_data.get('title', 'N/A')}``**"
        all_display_entries = []
        for i, song_info in enumerate(processed_song_queue):
            title = song_info.get('title', 'N/A'); 
            if len(title) > 60: title = title[:57] + "..."
            webpage_url = song_info.get('webpage_url', None)
            all_display_entries.append(f"`{i + 1}.` [{title}]({webpage_url})" if webpage_url and webpage_url != '#' else f"`{i + 1}.` {title}")
        next_song_number = len(all_display_entries) + 1
        active_summary_data = self.active_playlist_summaries.get(guild_id)
        if active_summary_data and active_summary_data['entries']:
            for summary_info in active_summary_data['entries']:
                title = summary_info.get('title', 'เพลงกำลังโหลดชื่อ...'); 
                if len(title) > 50: title = title[:47] + "..."
                pending_webpage_url = summary_info.get('url', summary_info.get('webpage_url', None))
                entry_text = f"`{next_song_number}.` {title} `(กำลังโหลด...)`"
                if pending_webpage_url and pending_webpage_url != '#': entry_text = f"`{next_song_number}.` [{title}]({pending_webpage_url}) `(กำลังโหลด...)`"
                all_display_entries.append(entry_text); next_song_number +=1
        if not all_display_entries and not current_song_data: return await ctx.send("คิวเพลงว่างเปล่า และไม่มีเพลงกำลังเล่น")
        embed = discord.Embed(title="รายการเพลง (คิว) 🎵", color=discord.Color.purple())
        if current_song_field_text: embed.add_field(name="กำลังเล่น 🎶", value=current_song_field_text, inline=False)
        else: embed.add_field(name="กำลังเล่น 🎶", value="ขณะนี้ไม่มีเพลงกำลังเล่น", inline=False)
        if not all_display_entries: embed.add_field(name="ในคิว ⏳", value="ว่าง", inline=False)
        else:
            display_text = "\n".join(all_display_entries[:20])
            if len(all_display_entries) > 20: display_text += f"\n...และอีก {len(all_display_entries) - 20} เพลง"
            embed.add_field(name="ในคิว ⏳", value=display_text if display_text else "ว่าง", inline=False)
        embed.set_footer(text=f"มีทั้งหมด {len(all_display_entries)} รายการในคิว | ใช้ปุ่ม Queue ใน Panel เพื่อดูแบบแบ่งหน้า"); await ctx.send(embed=embed)

    @commands.command(name="nowplaying", aliases=['np'], help="แสดงเพลงที่กำลังเล่นอยู่")
    async def nowplaying(self, ctx: commands.Context):
        current = self.current_song.get(ctx.guild.id)
        if current:
            embed = discord.Embed(title="กำลังเล่น 🎶", description=f"**``{current.get('title','N/A')}``**", color=discord.Color.green())
            requester_obj = current.get('requester')
            requester_mention = requester_obj.mention if isinstance(requester_obj, (discord.Member, discord.User)) else "N/A"
            embed.add_field(name="Requested by", value=requester_mention, inline=True)
            if current.get('duration', 0) > 0:
                m, s = divmod(current['duration'], 60); h, m = divmod(m, 60)
                duration_str = (f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")
                embed.add_field(name="Time", value=duration_str, inline=True)
            current_guild_volume = self.guild_volumes.get(ctx.guild.id, {}).get('current', 0.7)
            volume_display = f"``{int(current_guild_volume * 100)}%``"
            if self.is_guild_muted.get(ctx.guild.id, False): volume_display = "``Muted (0%)``"
            embed.add_field(name="Volume", value=volume_display, inline=True)
            await ctx.send(embed=embed)
        else: await ctx.send("ไม่มีเพลงกำลังเล่นอยู่")

    @commands.command(name="clear", aliases=['clr'], help="ล้างคิวเพลงทั้งหมด")
    async def clear(self, ctx: commands.Context):
        guild_id = ctx.guild.id; queue = self._get_song_queue(guild_id); items_cleared = False
        if queue: queue.clear(); items_cleared = True
        if self.playlist_processing_tasks.get(guild_id) and not self.playlist_processing_tasks[guild_id].done():
            self.playlist_processing_tasks[guild_id].cancel(); items_cleared = True
        if guild_id in self.active_playlist_summaries: del self.active_playlist_summaries[guild_id]; items_cleared = True
        if items_cleared: await ctx.send("🧹 ล้างคิวเพลงทั้งหมดและยกเลิกการโหลดเพลย์ลิสต์แล้ว", delete_after=10)
        else: await ctx.send("คิวเพลงว่างอยู่แล้ว", delete_after=10)
        await self._call_panel_update(guild_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))