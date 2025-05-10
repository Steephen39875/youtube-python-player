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
        self.root.title("Music Player")
        self.root.geometry("700x500")
        self.root.minsize(600, 450)
        
        # Application state
        self.tracks = []
        self.current_track = None
        self.player = None
        self.selected_format = None
        self.search_cache = {}
        self.thumbnail_cache = {}
        self.downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "MusicPlayer")
        os.makedirs(self.downloads_dir, exist_ok=True)
        self.timer_id = None  # For tracking playback update timer
        self.is_paused = False  # Track pause state
        
        # Set up theme and styles
        style = ttk.Style()
        style.configure('TButton', font=('Helvetica', 10))
        style.configure('TLabel', font=('Helvetica', 10))
        style.configure('Title.TLabel', font=('Helvetica', 12, 'bold'))
        
        # Create main container with padding
        main_container = ttk.Frame(root, padding="12")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid layout
        main_container.columnconfigure(0, weight=1)
        main_container.rowconfigure(0, weight=0)  # Search bar
        main_container.rowconfigure(1, weight=1)  # Results and info
        main_container.rowconfigure(2, weight=0)  # Controls
        main_container.rowconfigure(3, weight=0)  # Progress
        
        # Search bar
        search_frame = ttk.Frame(main_container)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        search_frame.columnconfigure(0, weight=1)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, font=('Helvetica', 11))
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.search_entry.bind('<Return>', lambda event: self.search_audio())
        
        self.search_button = ttk.Button(search_frame, text="Search", command=self.search_audio, width=10)
        self.search_button.grid(row=0, column=1, sticky="e")
        
        # Content area - split into list and details
        content_frame = ttk.Frame(main_container)
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
        # Left panel - Track list
        list_panel = ttk.Frame(content_frame)
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        list_panel.rowconfigure(0, weight=0)
        list_panel.rowconfigure(1, weight=1)
        list_panel.columnconfigure(0, weight=1)
        
        ttk.Label(list_panel, text="Results", style='Title.TLabel').grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        list_container = ttk.Frame(list_panel)
        list_container.grid(row=1, column=0, sticky="nsew")
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)
        
        self.track_listbox = tk.Listbox(list_container, font=('Helvetica', 10), activestyle='dotbox', 
                                        selectbackground="#a6a6a6", selectforeground="black")
        self.track_listbox.grid(row=0, column=0, sticky="nsew")
        self.track_listbox.bind('<<ListboxSelect>>', self.on_track_select)
        
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.track_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.track_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Right panel - Track details
        details_panel = ttk.Frame(content_frame)
        details_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        details_panel.columnconfigure(0, weight=1)
        details_panel.rowconfigure(0, weight=0)  # Title
        details_panel.rowconfigure(1, weight=1)  # Thumbnail
        details_panel.rowconfigure(2, weight=0)  # Info
        
        # Track title
        self.title_var = tk.StringVar(value="No track selected")
        title_label = ttk.Label(details_panel, textvariable=self.title_var, wraplength=300, style='Title.TLabel')
        title_label.grid(row=0, column=0, sticky="nw", pady=(0, 10))
        
        # Track thumbnail
        thumbnail_frame = ttk.Frame(details_panel)
        thumbnail_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        thumbnail_frame.columnconfigure(0, weight=1)
        thumbnail_frame.rowconfigure(0, weight=1)
        
        self.preview_canvas = tk.Canvas(thumbnail_frame, bg="#f0f0f0", highlightthickness=0)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        
        # Track info
        info_frame = ttk.Frame(details_panel)
        info_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        info_frame.columnconfigure(0, weight=1)
        
        self.duration_var = tk.StringVar(value="Duration: --:--")
        ttk.Label(info_frame, textvariable=self.duration_var).grid(row=0, column=0, sticky="w")
        
        self.size_var = tk.StringVar(value="Size: --")
        ttk.Label(info_frame, textvariable=self.size_var).grid(row=1, column=0, sticky="w")
        
        self.bitrate_var = tk.StringVar(value="Bitrate: -- kbps")
        ttk.Label(info_frame, textvariable=self.bitrate_var).grid(row=2, column=0, sticky="w")
        
        # Playback controls
        control_frame = ttk.Frame(main_container)
        control_frame.grid(row=2, column=0, sticky="ew", pady=10)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)
        control_frame.columnconfigure(2, weight=1)
        control_frame.columnconfigure(3, weight=1)
        
        self.play_button = ttk.Button(control_frame, text="▶ Play", command=self.play_audio, state=tk.DISABLED, width=10)
        self.play_button.grid(row=0, column=0, padx=5)
        
        self.pause_button = ttk.Button(control_frame, text="⏸️ Pause", command=self.toggle_pause, state=tk.DISABLED, width=10)
        self.pause_button.grid(row=0, column=1, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="■ Stop", command=self.stop_audio, state=tk.DISABLED, width=10)
        self.stop_button.grid(row=0, column=2, padx=5)
        
        self.download_button = ttk.Button(control_frame, text="⬇ Download", command=self.download_audio, state=tk.DISABLED, width=10)
        self.download_button.grid(row=0, column=3, padx=5)
        
        # Playback slider and status
        slider_frame = ttk.Frame(main_container)
        slider_frame.grid(row=3, column=0, sticky="ew")
        slider_frame.columnconfigure(1, weight=1)
        
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        ttk.Label(slider_frame, textvariable=self.time_var).grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.slider = ttk.Scale(slider_frame, from_=0, to=100, orient="horizontal")
        self.slider.grid(row=0, column=1, sticky="ew")
        self.slider.bind("<ButtonPress-1>", self.on_slider_press)
        self.slider.bind("<ButtonRelease-1>", self.on_slider_release)
        self.slider_dragging = False
        
        # Status bar and progress
        status_frame = ttk.Frame(main_container)
        status_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        status_frame.columnconfigure(0, weight=1)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        
        self.download_progress = ttk.Progressbar(main_container, mode="determinate")
        self.download_progress.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        self.download_progress["value"] = 0
        
        # Set focus to search entry
        self.search_entry.focus_set()
    
    def run_hidden_process(self, command, capture_output=True, check=False):
        """Run a subprocess with hidden console window"""
        startupinfo = None
        if os.name == 'nt':  # Windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
        
        if capture_output:
            result = subprocess.run(
                command,
                capture_output=capture_output,
                text=True,
                startupinfo=startupinfo,
                check=check
            )
            return result
        else:
            return subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo
            )
    
    def search_audio(self):
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Input Error", "Please enter a search query.")
            return
        
        # Stop any playing audio when starting a new search
        self.stop_audio()
        
        self.status_var.set(f"Searching for: {query}")
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    @lru_cache(maxsize=32)
    def cached_search(self, query):
        if query in self.search_cache:
            return self.search_cache[query]
        
        command = ["yt-dlp", "--flat-playlist", "--quiet", "--dump-json", f"ytsearch20:{query}"]
        try:
            result = self.run_hidden_process(command, check=True)
            tracks = [json.loads(line) for line in result.stdout.splitlines()]
            self.search_cache[query] = tracks
            return tracks
        except Exception:
            return []

    def _search_thread(self, query):
        tracks = self.cached_search(query)
        self.root.after(0, lambda: self._update_search_results(tracks))

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
            
            threading.Thread(
                target=self._load_thumbnail_thread, 
                args=(i, track.get("thumbnail", "")), 
                daemon=True
            ).start()
        
        self.status_var.set(f"Found {len(tracks)} tracks")

    def _load_thumbnail_thread(self, index, url):
        if not url or url in self.thumbnail_cache:
            return
            
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                image = Image.open(io.BytesIO(response.content))
                self.thumbnail_cache[url] = image
                
                if self.track_listbox.curselection() and self.track_listbox.curselection()[0] == index:
                    self.root.after(0, lambda: self.show_thumbnail(url))
        except Exception:
            pass

    def on_track_select(self, event):
        selection = self.track_listbox.curselection()
        if not selection:
            return
        
        # Stop any playing audio when selecting a new one
        self.stop_audio()
        
        # Disable buttons until format is loaded
        self.play_button["state"] = tk.DISABLED
        self.pause_button["state"] = tk.DISABLED
        self.download_button["state"] = tk.DISABLED
            
        index = selection[0]
        if index >= len(self.tracks):
            return
            
        track = self.tracks[index]
        self.current_track = track
        
        self.title_var.set(track.get("title", "Unknown Title"))
        self.duration_var.set(f"Duration: {self.format_duration(track.get('duration', 0))}")
        self.size_var.set("Size: Loading...")
        self.bitrate_var.set("Bitrate: Loading...")
        
        thumbnail_url = track.get("thumbnail", "")
        if thumbnail_url:
            self.show_thumbnail(thumbnail_url)
        
        threading.Thread(target=self._fetch_best_audio_format, args=(track,), daemon=True).start()
        self.status_var.set("Finding best audio format...")

    def show_thumbnail(self, url):
        try:
            if url in self.thumbnail_cache:
                image = self.thumbnail_cache[url]
            else:
                response = requests.get(url, timeout=5)
                image = Image.open(io.BytesIO(response.content))
                self.thumbnail_cache[url] = image
                
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            
            if canvas_width < 10 or canvas_height < 10:
                canvas_width = 250
                canvas_height = 150
                
            img_width, img_height = image.size
            ratio = min(canvas_width/img_width, canvas_height/img_height)
            new_width = int(img_width * ratio)
            new_height = int(img_height * ratio)
            
            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(resized)
            
            x_pos = (canvas_width - new_width) // 2
            y_pos = (canvas_height - new_height) // 2
            
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(x_pos, y_pos, anchor="nw", image=photo)
            self.preview_canvas.image = photo
            
        except Exception:
            self.preview_canvas.delete("all")
            self.preview_canvas.create_text(
                self.preview_canvas.winfo_width() // 2,
                self.preview_canvas.winfo_height() // 2,
                text="Album art not available",
                font=('Helvetica', 10)
            )

    def _fetch_best_audio_format(self, track):
        track_url = track.get("webpage_url", "")
        if not track_url:
            self.root.after(0, lambda: self.status_var.set("Failed to get track URL"))
            return
            
        try:
            command = ["yt-dlp", "-J", track_url]
            result = self.run_hidden_process(command, check=True)
            track_data = json.loads(result.stdout)
            
            formats = track_data.get("formats", [])
            
            # Filter only audio formats
            audio_formats = [fmt for fmt in formats if fmt.get("acodec", "none") != "none" and fmt.get("vcodec", "") == "none"]
            
            if not audio_formats:
                # No audio-only formats, look for combined formats and extract audio
                self.selected_format = {
                    "format_id": "bestaudio/best",
                    "ext": "mp3",
                    "is_audio_extract": True
                }
                
                # Update UI with placeholder info
                self.root.after(0, lambda: self._update_track_info({
                    "bitrate": "Unknown",
                    "size": "Unknown",
                    "ext": "mp3"
                }))
            else:
                # Sort by bitrate (highest first)
                audio_formats.sort(key=lambda x: x.get("abr", 0) or x.get("tbr", 0), reverse=True)
                best_audio = audio_formats[0]
                
                self.selected_format = best_audio
                self.root.after(0, lambda: self._update_track_info(best_audio))
                
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Error: {str(e)[:50]}"))

    def _update_track_info(self, format_info):
        # Update format info
        bitrate = format_info.get("abr", format_info.get("tbr", 0))
        if bitrate:
            self.bitrate_var.set(f"Bitrate: {bitrate:.1f} kbps")
        else:
            self.bitrate_var.set("Bitrate: Unknown")
            
        filesize = format_info.get("filesize", None) or format_info.get("filesize_approx", None)
        if filesize:
            self.size_var.set(f"Size: {humanize.naturalsize(filesize)}")
        else:
            self.size_var.set("Size: Unknown")
            
        ext = format_info.get("ext", "mp3")
        
        # Enable playback buttons
        self.play_button["state"] = tk.NORMAL
        self.download_button["state"] = tk.NORMAL
        
        self.status_var.set(f"Ready to play ({ext} format)")

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

    def play_audio(self):
        if not self.current_track or not self.selected_format:
            messagebox.showwarning("Selection Error", "Please select a track first.")
            return
        
        # Stop any currently playing audio
        self.stop_audio()
        
        # Reset pause state
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")
            
        track_url = self.current_track.get("webpage_url", "")
        if not track_url:
            messagebox.showwarning("URL Error", "Failed to retrieve track URL.")
            return
            
        self.status_var.set("Preparing audio for playback...")
        threading.Thread(target=self._setup_streaming, args=(track_url,), daemon=True).start()

    def toggle_pause(self):
        """Toggle between pause and play states"""
        if not self.player:
            return
            
        if self.is_paused:
            # Resume playback
            self.player.play()
            self.is_paused = False
            self.pause_button.config(text="⏸️ Pause")
            self.status_var.set("Playback resumed")
        else:
            # Pause playback
            self.player.pause()
            self.is_paused = True
            self.pause_button.config(text="▶️ Continue")
            self.status_var.set("Playback paused")

    def _setup_streaming(self, track_url):
        try:
            if self.selected_format.get("is_audio_extract", False):
                # Extract audio from best available format
                format_spec = "bestaudio/best"
            else:
                # Use the selected audio format ID
                format_spec = self.selected_format.get("format_id", "bestaudio/best")
                
            command = ["yt-dlp", "-f", format_spec, "-g", track_url]
            result = self.run_hidden_process(command, check=True)
            stream_url = result.stdout.strip()
            
            self.root.after(0, lambda: self._start_player(stream_url))
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Error: {str(e)[:50]}"))

    def _start_player(self, stream_url):
        # Ensure any existing player is stopped
        if self.player:
            self.player.stop()
            self.player = None
            
        # Cancel any existing timer
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
            
        instance = vlc.Instance('--no-video', '--quiet')
        self.player = instance.media_player_new()
        
        media = instance.media_new(stream_url)
        self.player.set_media(media)
        
        # Get media properties
        media.parse()
        
        self.player.play()
        self.status_var.set("Playing audio...")
        self.stop_button["state"] = tk.NORMAL
        self.pause_button["state"] = tk.NORMAL
        self.play_button["state"] = tk.DISABLED
        
        # Reset pause state
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")
        
        # Wait a moment for VLC to start playing before beginning updates
        self.root.after(500, self._update_playback)

    def _update_playback(self):
        if not self.player:
            return
            
        try:
            if self.player.is_playing():
                # Get current time and length in milliseconds
                current_ms = self.player.get_time()
                length = self.player.get_length()
                
                if length > 0 and not self.slider_dragging:
                    # Update slider position (0-100%)
                    position = (current_ms / length) * 100
                    self.slider.set(position)
                    
                    # Update time display
                    current_sec = current_ms // 1000
                    total_sec = length // 1000
                    current_str = self.format_duration(current_sec)
                    total_str = self.format_duration(total_sec)
                    self.time_var.set(f"{current_str} / {total_str}")
                
                # Schedule next update
                self.timer_id = self.root.after(500, self._update_playback)
            elif self.player.get_state() == vlc.State.Ended:
                self.stop_audio()
                self.status_var.set("Playback finished")
            elif self.player.get_state() == vlc.State.Paused:
                # Just continue checking while paused
                self.timer_id = self.root.after(500, self._update_playback)
            else:
                # Still loading or in another state, check again soon
                self.timer_id = self.root.after(500, self._update_playback)
        except Exception:
            # Handle any VLC errors
            self.stop_audio()
            self.status_var.set("Playback error")

    def on_slider_press(self, event):
        self.slider_dragging = True

    def on_slider_release(self, event):
        if self.player:
            position = self.slider.get() / 100.0
            self.player.set_position(position)
        self.slider_dragging = False

    def stop_audio(self):
        # Cancel update timer
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
            
        # Stop player
        if self.player:
            self.player.stop()
            self.player = None
            
        # Reset UI
        self.slider.set(0)
        self.time_var.set("0:00 / 0:00")
        self.status_var.set("Playback stopped")
        self.stop_button["state"] = tk.DISABLED
        self.pause_button["state"] = tk.DISABLED
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")
        
        # Re-enable play button if format is selected
        if self.selected_format:
            self.play_button["state"] = tk.NORMAL

    def download_audio(self):
        if not self.current_track or not self.selected_format:
            messagebox.showwarning("Selection Error", "Please select a track first.")
            return
            
        track_url = self.current_track.get("webpage_url", "")
        if not track_url:
            messagebox.showwarning("URL Error", "Failed to retrieve track URL.")
            return
            
        title = self.current_track.get("title", "audio")
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}"
        
        # Use mp3 as the default format for consistency
        ext = "mp3"
        output_path = os.path.join(self.downloads_dir, f"{filename}.{ext}")
        
        self.status_var.set("Starting download...")
        self.download_progress["value"] = 0
        self.download_button["state"] = tk.DISABLED
        
        # Define format spec for audio download
        if self.selected_format.get("is_audio_extract", False):
            format_spec = "bestaudio/best"
        else:
            format_spec = self.selected_format.get("format_id", "bestaudio/best")
        
        threading.Thread(
            target=self._download_thread, 
            args=(track_url, format_spec, output_path),
            daemon=True
        ).start()

    def _download_thread(self, track_url, format_spec, output_path):
        try:
            # Command for audio download with post-processing to convert to mp3
            command = [
                "yt-dlp", 
                "-f", format_spec,
                "-o", output_path,
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "--newline"
            ]
            
            process = self.run_hidden_process(command, capture_output=False)
            
            for line in process.stdout:
                if "%" in line:
                    try:
                        percent_match = re.search(r'(\d+\.?\d*)%', line)
                        if percent_match:
                            percent = float(percent_match.group(1))
                            self.root.after(0, lambda p=percent: self._update_download_progress(p))
                    except Exception:
                        pass
            
            process.wait()
            
            if process.returncode == 0:
                self.root.after(0, lambda: self._download_complete(output_path))
            else:
                self.root.after(0, lambda: self._download_failed("Download failed"))
                
        except Exception as e:
            self.root.after(0, lambda: self._download_failed(str(e)))

    def _update_download_progress(self, percent):
        self.download_progress["value"] = percent
        self.status_var.set(f"Downloading: {percent:.1f}%")

    def _download_complete(self, path):
        self.download_progress["value"] = 100
        self.status_var.set("Download complete!")
        self.download_button["state"] = tk.NORMAL
        
        messagebox.showinfo(
            "Download Complete", 
            f"Audio downloaded successfully!\nSaved to: {path}"
        )

    def _download_failed(self, error_msg):
        self.download_progress["value"] = 0
        self.status_var.set(f"Download failed: {error_msg}")
        self.download_button["state"] = tk.NORMAL
        
        messagebox.showerror("Download Error", f"Failed to download audio: {error_msg}")

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

if __name__ == "__main__":
    # Set up high DPI awareness for better UI scaling
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
        
    # Make sure we have humanize module
    try:
        import humanize
    except ImportError:
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "humanize"])
        import humanize
    
    # If running as compiled exe, set proper paths for VLC
    if getattr(sys, 'frozen', False):
        # Add VLC plugins path
        vlc_plugin_path = resource_path(os.path.join('vlc', 'plugins'))
        os.environ['VLC_PLUGIN_PATH'] = vlc_plugin_path
        
        # Tell yt-dlp where to find itself when frozen
        os.environ["YTDLP_FILENAME"] = resource_path("yt-dlp.exe")
        
    root = tk.Tk()
    app = AudioPlayerApp(root)
    root.mainloop()