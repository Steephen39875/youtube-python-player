import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import json
import vlc
from PIL import Image, ImageTk
import requests
import threading
import io
import os
import time
from functools import lru_cache
import re
import humanize
import sys

class AudioPlayerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Music Player")
        self.root.geometry("600x450")
        self.root.minsize(500, 400)
        
        self.init_state()
        self.setup_ui()
        self.search_entry.focus_set()
    
    def init_state(self):
        self.tracks = []
        self.current_track = None
        self.player = None
        self.selected_format = None
        self.available_formats = []
        self.search_cache = {}
        self.thumbnail_cache = {}
        self.downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "MusicPlayer")
        os.makedirs(self.downloads_dir, exist_ok=True)
        self.timer_id = None
        self.is_paused = False
        
    def setup_ui(self):
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        for i, weight in enumerate([0, 0, 1, 0, 0, 0]):
            main_container.rowconfigure(i, weight=weight)
        main_container.columnconfigure(0, weight=1)
        
        self.setup_search_bar(main_container)
        self.setup_player_info(main_container)
        self.setup_track_list(main_container)
        self.setup_info_frame(main_container)
        self.setup_controls(main_container)
        self.setup_progress_bar(main_container)
        self.setup_status_bar(main_container)
    
    def setup_search_bar(self, parent):
        search_frame = ttk.Frame(parent)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        search_frame.columnconfigure(0, weight=1)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, font=('Helvetica', 11))
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.search_entry.bind('<Return>', lambda event: self.search_audio())
        
        self.search_button = ttk.Button(search_frame, text="Search", command=self.search_audio)
        self.search_button.grid(row=0, column=1, sticky="e")
    
    def setup_player_info(self, parent):
        player_info_frame = ttk.Frame(parent)
        player_info_frame.grid(row=1, column=0, sticky="ew", pady=5)
        
        ttk.Label(player_info_frame, text="Player: VLC Media Player | Downloader: yt-dlp", 
                  font=('Helvetica', 9)).pack(side=tk.LEFT)
    
    def setup_track_list(self, parent):
        list_frame = ttk.LabelFrame(parent, text="Results")
        list_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        list_container = ttk.Frame(list_frame)
        list_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)
        
        self.track_listbox = tk.Listbox(list_container, font=('Helvetica', 10), 
                                       selectbackground="#a6a6a6", selectforeground="black")
        self.track_listbox.grid(row=0, column=0, sticky="nsew")
        self.track_listbox.bind('<<ListboxSelect>>', self.on_track_select)
        
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.track_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.track_listbox.configure(yscrollcommand=scrollbar.set)
    
    def setup_info_frame(self, parent):
        info_frame = ttk.Frame(parent)
        info_frame.grid(row=3, column=0, sticky="ew", pady=5)
        info_frame.columnconfigure(0, weight=1)
        
        self.title_var = tk.StringVar(value="No track selected")
        ttk.Label(info_frame, textvariable=self.title_var, 
                 wraplength=580, font=('Helvetica', 10, 'bold')).grid(row=0, column=0, sticky="w")
        
        self.info_var = tk.StringVar(value="Duration: --:-- | Format: -- | Size: --")
        ttk.Label(info_frame, textvariable=self.info_var).grid(row=1, column=0, sticky="w")
    
    def setup_controls(self, parent):
        controls_frame = ttk.Frame(parent)
        controls_frame.grid(row=4, column=0, sticky="ew", pady=5)
        
        button_configs = [
            ("play_button", "▶ Play", self.play_audio, 8),
            ("pause_button", "⏸️ Pause", self.toggle_pause, 8),
            ("stop_button", "■ Stop", self.stop_audio, 8)
        ]
        
        for i, (attr_name, text, command, width) in enumerate(button_configs):
            button = ttk.Button(controls_frame, text=text, command=command, state=tk.DISABLED, width=width)
            button.pack(side=tk.LEFT, padx=5)
            setattr(self, attr_name, button)
        
        download_frame = ttk.Frame(controls_frame)
        download_frame.pack(side=tk.RIGHT)
        
        self.format_var = tk.StringVar(value="Select Format")
        self.format_selector = ttk.Combobox(download_frame, textvariable=self.format_var, 
                                          state="readonly", width=40)
        self.format_selector.pack(side=tk.LEFT, padx=5)
        
        self.download_button = ttk.Button(download_frame, text="⬇ Download", 
                                        command=self.download_audio, state=tk.DISABLED, width=10)
        self.download_button.pack(side=tk.LEFT, padx=5)
    
    def setup_progress_bar(self, parent):
        self.progress_frame = ttk.Frame(parent)
        self.progress_frame.grid(row=5, column=0, sticky="ew", pady=5)
        self.progress_frame.columnconfigure(1, weight=1)
        
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        ttk.Label(self.progress_frame, textvariable=self.time_var).grid(row=0, column=0, sticky="w", padx=(0, 5))
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="determinate")
        self.progress_bar.grid(row=0, column=1, sticky="ew")
    
    def setup_status_bar(self, parent):
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(parent, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=6, column=0, sticky="ew", pady=(5, 0))
    
    def run_hidden_process(self, command, capture_output=True, check=False):
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        
        if capture_output:
            return subprocess.run(command, capture_output=capture_output, text=True, 
                               startupinfo=startupinfo, check=check)
        else:
            return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                 text=True, startupinfo=startupinfo)
    
    def search_audio(self):
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Input Error", "Please enter a search query.")
            return
        
        self.stop_audio()
        self.status_var.set(f"Searching for: {query}")
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    @lru_cache(maxsize=32)
    def cached_search(self, query):
        if query in self.search_cache:
            return self.search_cache[query]
        
        try:
            result = self.run_hidden_process(["yt-dlp", "--flat-playlist", "--quiet", "--dump-json", f"ytsearch20:{query}"], check=True)
            tracks = [json.loads(line) for line in result.stdout.splitlines()]
            self.search_cache[query] = tracks
            return tracks
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []

    def _search_thread(self, query):
        try:
            tracks = self.cached_search(query)
            self.root.after(0, lambda: self._update_search_results(tracks))
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Search error: {str(e)[:50]}"))

    def _update_search_results(self, tracks):
        if not tracks:
            self.status_var.set("No tracks found.")
            return
            
        self.tracks = tracks
        self.track_listbox.delete(0, tk.END)
        
        for i, track in enumerate(tracks):
            title = track.get("title", "N/A")
            duration = self.format_duration(track.get("duration", 0))
            self.track_listbox.insert(tk.END, f"{i+1}. {title} [{duration}]")
        
        self.status_var.set(f"Found {len(tracks)} tracks")

    def on_track_select(self, event):
        selection = self.track_listbox.curselection()
        if not selection:
            return
        
        self.stop_audio()
        
        for btn in [self.play_button, self.pause_button, self.download_button]:
            btn["state"] = tk.DISABLED
        
        self.format_selector["values"] = []
        self.format_var.set("Loading formats...")
            
        index = selection[0]
        if index >= len(self.tracks):
            return
            
        track = self.tracks[index]
        self.current_track = track
        
        self.title_var.set(track.get("title", "Unknown Title"))
        self.info_var.set(f"Duration: {self.format_duration(track.get('duration', 0))} | Loading format info...")
        
        threading.Thread(target=self._fetch_all_formats, args=(track,), daemon=True).start()
        self.status_var.set("Finding available formats...")

    def format_duration(self, seconds):
        if not seconds:
            return "--:--"
            
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    def _fetch_all_formats(self, track):
        track_url = track.get("webpage_url", "")
        if not track_url:
            self.root.after(0, lambda: self.status_var.set("Failed to get track URL"))
            return
            
        try:
            result = self.run_hidden_process(["yt-dlp", "-J", track_url], check=True)
            track_data = json.loads(result.stdout)
            formats = track_data.get("formats", [])
            
            processed_formats = [
                {
                    "format_id": "bestaudio/best",
                    "ext": "best",
                    "format_note": "Best audio quality",
                    "display_name": "Best Audio Quality (auto format)",
                    "is_special": True
                },
                {
                    "format_id": "mp3",
                    "ext": "mp3",
                    "format_note": "MP3 (converted)",
                    "display_name": "MP3 Audio (converted)",
                    "is_special": True
                }
            ]
            
            for fmt in formats:
                if fmt.get("acodec", "none") != "none":
                    ext = fmt.get("ext", "unknown")
                    format_id = fmt.get("format_id", "unknown")
                    abr = fmt.get("abr", fmt.get("tbr", 0))
                    bitrate_str = f"{abr:.1f} kbps" if abr else "?"
                    filesize = fmt.get("filesize", None) or fmt.get("filesize_approx", None)
                    size_str = humanize.naturalsize(filesize) if filesize else "?"
                    is_audio_only = fmt.get("vcodec", "") == "none"
                    type_str = "Audio only" if is_audio_only else "Audio+Video"
                    res_str = ""
                    if not is_audio_only and fmt.get("height"):
                        res_str = f"{fmt.get('height')}p"
                    
                    display_name = f"{format_id} | {ext} | {type_str} | {bitrate_str}"
                    if res_str:
                        display_name += f" | {res_str}"
                    display_name += f" | {size_str}"
                    
                    fmt["display_name"] = display_name
                    processed_formats.append(fmt)
            
            self.available_formats = processed_formats
            
            audio_formats = [fmt for fmt in formats if fmt.get("acodec", "none") != "none" and fmt.get("vcodec", "") == "none"]
            
            self.selected_format = {"format_id": "bestaudio/best", "ext": "mp3", "is_audio_extract": True} if not audio_formats else \
                        sorted(audio_formats, key=lambda x: x.get("abr", 0) or x.get("tbr", 0), reverse=True)[0]
                
            self.root.after(0, lambda: self._update_format_list(processed_formats))
            
        except Exception as e:
            print(f"Format error: {str(e)}")
            self.root.after(0, lambda: self.status_var.set(f"Error: {str(e)[:50]}"))

    def _update_format_list(self, formats):
        display_items = [fmt["display_name"] for fmt in formats]
        
        self.format_selector["values"] = display_items
        
        if display_items:
            self.format_selector.current(0)
        
        if self.selected_format:
            bitrate = self.selected_format.get("abr", self.selected_format.get("tbr", 0))
            bitrate_str = f"{bitrate:.1f} kbps" if bitrate else "Unknown"
            filesize = self.selected_format.get("filesize", None) or self.selected_format.get("filesize_approx", None)
            size_str = humanize.naturalsize(filesize) if filesize else "Unknown"
            ext = self.selected_format.get("ext", "mp3")
            
            self.info_var.set(f"Duration: {self.format_duration(self.current_track.get('duration', 0))} | Format: {ext} | Size: {size_str}")
        
        self.play_button["state"] = tk.NORMAL
        self.download_button["state"] = tk.NORMAL
        
        self.status_var.set(f"Ready to play or download. {len(formats)} formats available.")

    def play_audio(self):
        if not self.current_track or not self.selected_format:
            messagebox.showwarning("Selection Error", "Please select a track first.")
            return
        
        self.stop_audio()
        self.reset_pause_state()
            
        track_url = self.current_track.get("webpage_url", "")
        if not track_url:
            messagebox.showwarning("URL Error", "Failed to retrieve track URL.")
            return
            
        self.status_var.set("Preparing audio for playback...")
        threading.Thread(target=self._setup_streaming, args=(track_url,), daemon=True).start()
    
    def reset_pause_state(self):
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")

    def toggle_pause(self):
        if not self.player:
            return
            
        if self.is_paused:
            self.player.play()
            self.is_paused = False
            self.pause_button.config(text="⏸️ Pause")
            self.status_var.set("Playback resumed")
        else:
            self.player.pause()
            self.is_paused = True
            self.pause_button.config(text="▶️ Continue")
            self.status_var.set("Playback paused")

    def _setup_streaming(self, track_url):
        try:
            format_spec = "bestaudio/best" if self.selected_format.get("is_audio_extract", False) else \
                          self.selected_format.get("format_id", "bestaudio/best")
                
            result = self.run_hidden_process(["yt-dlp", "-f", format_spec, "-g", track_url], check=True)
            stream_url = result.stdout.strip()
            
            self.root.after(0, lambda: self._start_player(stream_url))
            
        except Exception as e:
            print(f"Streaming error: {str(e)}")
            self.root.after(0, lambda: self.status_var.set(f"Error: {str(e)[:50]}"))

    def _start_player(self, stream_url):
        self.clean_player_state()
            
        instance = vlc.Instance('--no-video', '--quiet')
        self.player = instance.media_player_new()
        
        media = instance.media_new(stream_url)
        self.player.set_media(media)
        
        media.parse()
        
        self.player.play()
        self.status_var.set("Playing audio with VLC...")
        self.update_button_states_for_playback()
        
        self.root.after(500, self._update_playback)
    
    def clean_player_state(self):
        if self.player:
            self.player.stop()
            self.player = None
            
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
    
    def update_button_states_for_playback(self):
        self.stop_button["state"] = tk.NORMAL
        self.pause_button["state"] = tk.NORMAL
        self.play_button["state"] = tk.DISABLED
        self.reset_pause_state()

    def _update_playback(self):
        if not self.player:
            return
            
        try:
            if self.player.is_playing():
                current_ms = self.player.get_time()
                length = self.player.get_length()
                
                if length > 0:
                    position = (current_ms / length) * 100
                    self.progress_bar["value"] = position
                    
                    current_sec = current_ms // 1000
                    total_sec = length // 1000
                    current_str = self.format_duration(current_sec)
                    total_str = self.format_duration(total_sec)
                    self.time_var.set(f"{current_str} / {total_str}")
                
                self.timer_id = self.root.after(500, self._update_playback)
            elif self.player.get_state() == vlc.State.Ended:
                self.stop_audio()
                self.status_var.set("Playback finished")
            elif self.player.get_state() == vlc.State.Paused:
                self.timer_id = self.root.after(500, self._update_playback)
            else:
                self.timer_id = self.root.after(500, self._update_playback)
        except Exception as e:
            print(f"Playback error: {str(e)}")
            self.stop_audio()
            self.status_var.set("Playback error")

    def stop_audio(self):
        self.clean_player_state()
            
        self.progress_bar["value"] = 0
        self.time_var.set("0:00 / 0:00")
        self.status_var.set("Playback stopped")
        self.stop_button["state"] = tk.DISABLED
        self.pause_button["state"] = tk.DISABLED
        self.reset_pause_state()
        
        if self.selected_format:
            self.play_button["state"] = tk.NORMAL

    def download_audio(self):
        if not self.current_track:
            messagebox.showwarning("Selection Error", "Please select a track first.")
            return
            
        track_url = self.current_track.get("webpage_url", "")
        if not track_url:
            messagebox.showwarning("URL Error", "Failed to retrieve track URL.")
            return
        
        selected_index = self.format_selector.current()
        if selected_index < 0 or selected_index >= len(self.available_formats):
            messagebox.showwarning("Format Error", "Please select a download format.")
            return
            
        selected_format = self.available_formats[selected_index]
        
        title = self.current_track.get("title", "audio")
        safe_title = re.sub(r'[^a-zA-Z0-9]', "", title)[:20]
        timestamp = str(int(time.time()))
        filename = f"{safe_title}_{timestamp}"
        
        output_path = os.path.join(self.downloads_dir, filename)
        
        self.status_var.set("Starting download...")
        self.progress_bar["value"] = 0
        self.download_button["state"] = tk.DISABLED
        
        threading.Thread(
            target=self._download_thread, 
            args=(track_url, output_path, selected_format),
            daemon=True
        ).start()

    def _download_thread(self, track_url, output_path, selected_format):
        try:
            print(f"Starting download:\nURL: {track_url}\nOutput base: {output_path}")
            
            command = ["yt-dlp", "-o", f"{output_path}.%(ext)s", "--no-playlist"]
            
            if selected_format.get("is_special") and selected_format.get("ext") == "mp3":
                command.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
            elif selected_format.get("is_special"):
                command.extend(["-f", "bestaudio/best"])
            else:
                command.extend(["-f", selected_format.get("format_id")])
            
            command.append(track_url)
            
            print(f"Running command: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True)
            
            if result.returncode == 0:
                downloaded_file = None
                for file in os.listdir(self.downloads_dir):
                    if file.startswith(os.path.basename(output_path)):
                        downloaded_file = os.path.join(self.downloads_dir, file)
                        break
                        
                if downloaded_file:
                    self.root.after(0, lambda: self._download_complete(downloaded_file))
                else:
                    self.root.after(0, lambda: self._download_failed("File downloaded but not found"))
            else:
                error_msg = result.stderr if result.stderr else "Unknown error"
                print(f"yt-dlp error: {error_msg}")
                self.root.after(0, lambda: self._download_failed(f"yt-dlp error: {error_msg[:100]}"))
                
        except Exception as e:
            print(f"Download error: {str(e)}")
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: self._download_failed(str(e)))

    def _download_complete(self, path):
        self.progress_bar["value"] = 100
        self.status_var.set("Download complete!")
        self.download_button["state"] = tk.NORMAL
        
        messagebox.showinfo(
            "Download Complete", 
            f"Audio downloaded successfully!\nSaved to: {path}\n\nClick OK to open containing folder."
        )
        
        try:
            directory = os.path.dirname(path)
            if os.name == 'nt':
                os.startfile(directory)
            elif os.name == 'posix':
                if sys.platform == 'darwin':
                    subprocess.call(['open', directory])
                else:
                    subprocess.call(['xdg-open', directory])
        except Exception as e:
            print(f"Error opening folder: {str(e)}")

    def _download_failed(self, error_msg):
        self.progress_bar["value"] = 0
        self.status_var.set(f"Download failed: {error_msg[:50]}...")
        self.download_button["state"] = tk.NORMAL
        
        messagebox.showerror("Download Error", f"Failed to download audio:\n{error_msg}")

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
        
    try:
        import humanize
    except ImportError:
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "humanize"])
        import humanize
    
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        messagebox.showerror("Missing Dependency", 
                           "yt-dlp is not installed or not in your PATH. Please install it to use this application.")
        sys.exit(1)
    
    if getattr(sys, 'frozen', False):
        vlc_plugin_path = resource_path(os.path.join('vlc', 'plugins'))
        os.environ['VLC_PLUGIN_PATH'] = vlc_plugin_path
        os.environ["YTDLP_FILENAME"] = resource_path("yt-dlp.exe")
        
    root = tk.Tk()
    app = AudioPlayerApp(root)
    root.mainloop()