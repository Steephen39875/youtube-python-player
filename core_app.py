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

class YouTubeDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader")
        self.root.geometry("900x600")
        self.root.minsize(800, 550)
        
        # Application state
        self.videos = []
        self.current_video = None
        self.player = None
        self.formats = []
        self.selected_format = None
        self.search_cache = {}
        self.thumbnail_cache = {}
        self.downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YTDownloader")
        os.makedirs(self.downloads_dir, exist_ok=True)
        self.timer_id = None  # For tracking playback update timer
        self.is_paused = False  # Track pause state
        
        # Create main container with padding
        main_container = ttk.Frame(root, padding="12")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid layout
        main_container.columnconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=0)  # Search bar
        main_container.rowconfigure(1, weight=1)  # Main content
        main_container.rowconfigure(2, weight=0)  # Controls
        main_container.rowconfigure(3, weight=0)  # Progress
        
        # Search bar
        search_frame = ttk.Frame(main_container)
        search_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        search_frame.columnconfigure(0, weight=1)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.search_entry.bind('<Return>', lambda event: self.search_video())
        
        self.search_button = ttk.Button(search_frame, text="Search", command=self.search_video, width=10)
        self.search_button.grid(row=0, column=1, sticky="e")
        
        # Left panel - Video list
        list_panel = ttk.Frame(main_container)
        list_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        list_panel.rowconfigure(0, weight=0)
        list_panel.rowconfigure(1, weight=1)
        list_panel.columnconfigure(0, weight=1)
        
        ttk.Label(list_panel, text="Results").grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        list_container = ttk.Frame(list_panel)
        list_container.grid(row=1, column=0, sticky="nsew")
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)
        
        self.video_listbox = tk.Listbox(list_container)
        self.video_listbox.grid(row=0, column=0, sticky="nsew")
        self.video_listbox.bind('<<ListboxSelect>>', self.on_video_select)
        
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.video_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.video_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Right panel - Video details and controls
        details_panel = ttk.Frame(main_container)
        details_panel.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        details_panel.columnconfigure(0, weight=1)
        details_panel.rowconfigure(0, weight=0)  # Title
        details_panel.rowconfigure(1, weight=1)  # Thumbnail
        details_panel.rowconfigure(2, weight=0)  # Info
        details_panel.rowconfigure(3, weight=0)  # Format
        
        # Video title
        self.title_var = tk.StringVar(value="No video selected")
        title_label = ttk.Label(details_panel, textvariable=self.title_var, wraplength=400)
        title_label.grid(row=0, column=0, sticky="nw", pady=(0, 10))
        
        # Video thumbnail
        thumbnail_frame = ttk.Frame(details_panel)
        thumbnail_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        thumbnail_frame.columnconfigure(0, weight=1)
        thumbnail_frame.rowconfigure(0, weight=1)
        
        self.preview_canvas = tk.Canvas(thumbnail_frame)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        
        # Video info
        info_frame = ttk.Frame(details_panel)
        info_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        info_frame.columnconfigure(0, weight=1)
        
        self.duration_var = tk.StringVar(value="Duration: --:--")
        ttk.Label(info_frame, textvariable=self.duration_var).grid(row=0, column=0, sticky="w")
        
        # Format selector
        format_frame = ttk.Frame(details_panel)
        format_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        format_frame.columnconfigure(1, weight=1)
        
        ttk.Label(format_frame, text="Format:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        # Add a "Best Video+Audio" button
        self.best_combined_button = ttk.Button(details_panel, text="Select Best Video+Audio", 
                                             command=self.select_best_combined_format)
        self.best_combined_button.grid(row=3, column=0, sticky="e", pady=(0, 5))
        self.best_combined_button["state"] = tk.DISABLED
        
        # Format quality selector
        quality_frame = ttk.Frame(details_panel)
        quality_frame.grid(row=4, column=0, sticky="ew", pady=(0, 5))
        
        ttk.Label(quality_frame, text="Quality:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.quality_var = tk.StringVar(value="720p")
        quality_combo = ttk.Combobox(quality_frame, textvariable=self.quality_var, width=10, 
                                    values=["360p", "480p", "720p", "1080p", "1440p", "2160p"])
        quality_combo.grid(row=0, column=1, sticky="w")
        quality_combo.current(2)  # Default to 720p
        
        self.format_listbox = tk.Listbox(details_panel, height=6)
        self.format_listbox.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self.format_listbox.bind('<<ListboxSelect>>', self.on_format_selected)
        
        # Format scroll
        format_scrollbar = ttk.Scrollbar(details_panel, orient="vertical", command=self.format_listbox.yview)
        format_scrollbar.grid(row=5, column=1, sticky="ns")
        self.format_listbox.configure(yscrollcommand=format_scrollbar.set)
        
        # Playback controls
        control_frame = ttk.Frame(main_container)
        control_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)
        control_frame.columnconfigure(2, weight=1)
        control_frame.columnconfigure(3, weight=1)  # Add column for pause button
        
        self.play_button = ttk.Button(control_frame, text="▶ Play", command=self.play_video, state=tk.DISABLED, width=12)
        self.play_button.grid(row=0, column=0, padx=5)
        
        # Add new pause/continue button
        self.pause_button = ttk.Button(control_frame, text="⏸️ Pause", command=self.toggle_pause, state=tk.DISABLED, width=12)
        self.pause_button.grid(row=0, column=1, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="■ Stop", command=self.stop_video, state=tk.DISABLED, width=12)
        self.stop_button.grid(row=0, column=2, padx=5)
        
        self.download_button = ttk.Button(control_frame, text="⬇ Download", command=self.download_video, state=tk.DISABLED, width=12)
        self.download_button.grid(row=0, column=3, padx=5)
        
        # Playback slider and status
        slider_frame = ttk.Frame(main_container)
        slider_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
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
        status_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        status_frame.columnconfigure(0, weight=1)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        
        self.download_progress = ttk.Progressbar(main_container, mode="determinate")
        self.download_progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self.download_progress["value"] = 0
        
        # Set focus to search entry
        self.search_entry.focus_set()
    
    def select_best_combined_format(self):
        """Select the best available combined video+audio format based on selected quality"""
        if not self.current_video:
            return
            
        quality_pref = self.quality_var.get().replace('p', '')
        target_height = int(quality_pref) if quality_pref.isdigit() else 720
        
        # Create a special merged format option
        format_spec = {
            "format_id": f"bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]",
            "ext": "mp4",
            "vcodec": "merged",
            "acodec": "merged",
            "format_note": f"Best {self.quality_var.get()} merged",
            "resolution": f"≤{self.quality_var.get()}",
            "is_merged": True
        }
        
        # Set this as the selected format
        self.selected_format = format_spec
        
        # Update status and enable play button
        self.status_var.set(f"Selected best combined video+audio (≤{self.quality_var.get()})")
        self.play_button["state"] = tk.NORMAL
        self.download_button["state"] = tk.NORMAL
        
        # Update format listbox to show the selection
        self.format_listbox.selection_clear(0, tk.END)
        
        # Add the merged format to the top if not already there
        merged_format_text = f"0. MERGED: Best video+audio (≤{self.quality_var.get()})"
        if self.format_listbox.size() > 0 and self.format_listbox.get(0).startswith("0. MERGED:"):
            self.format_listbox.delete(0)
        
        self.format_listbox.insert(0, merged_format_text)
        self.format_listbox.selection_set(0)
        self.format_listbox.see(0)

    def search_video(self):
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Input Error", "Please enter a search query.")
            return
        
        # Stop any playing video when starting a new search
        self.stop_video()
        
        self.status_var.set(f"Searching for: {query}")
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    @lru_cache(maxsize=32)
    def cached_search(self, query):
        if query in self.search_cache:
            return self.search_cache[query]
        
        # Increased from 10 to 20 search results
        command = ["yt-dlp", "--flat-playlist", "--quiet", "--dump-json", f"ytsearch20:{query}"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            videos = [json.loads(line) for line in result.stdout.splitlines()]
            self.search_cache[query] = videos
            return videos
        except Exception:
            return []

    def _search_thread(self, query):
        videos = self.cached_search(query)
        self.root.after(0, lambda: self._update_search_results(videos))

    def _update_search_results(self, videos):
        if not videos:
            self.status_var.set("No videos found.")
            return
            
        self.videos = videos
        self.video_listbox.delete(0, tk.END)
        
        for i, video in enumerate(videos):
            title = video.get("title", "N/A")
            duration = self.format_duration(video.get("duration", 0))
            self.video_listbox.insert(tk.END, f"{i+1}. {title} [{duration}]")
            
            threading.Thread(
                target=self._load_thumbnail_thread, 
                args=(i, video.get("thumbnail", "")), 
                daemon=True
            ).start()
        
        self.status_var.set(f"Found {len(videos)} videos")

    def _load_thumbnail_thread(self, index, url):
        if not url or url in self.thumbnail_cache:
            return
            
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                image = Image.open(io.BytesIO(response.content))
                self.thumbnail_cache[url] = image
                
                if self.video_listbox.curselection() and self.video_listbox.curselection()[0] == index:
                    self.root.after(0, lambda: self.show_thumbnail(url))
        except Exception:
            pass

    def on_video_select(self, event):
        selection = self.video_listbox.curselection()
        if not selection:
            return
        
        # Stop any playing video when selecting a new one
        self.stop_video()
        
        # Reset format selection and disable play button until format is selected
        self.format_listbox.delete(0, tk.END)
        self.play_button["state"] = tk.DISABLED
        self.pause_button["state"] = tk.DISABLED  # Disable pause button as well
            
        index = selection[0]
        if index >= len(self.videos):
            return
            
        video = self.videos[index]
        self.current_video = video
        
        self.title_var.set(video.get("title", "Unknown Title"))
        self.duration_var.set(f"Duration: {self.format_duration(video.get('duration', 0))}")
        
        thumbnail_url = video.get("thumbnail", "")
        if thumbnail_url:
            self.show_thumbnail(thumbnail_url)
        
        # Enable the best combined format button
        self.best_combined_button["state"] = tk.NORMAL
        
        threading.Thread(target=self._fetch_formats_thread, args=(video,), daemon=True).start()
        self.status_var.set("Loading video formats...")

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
                canvas_width = 320
                canvas_height = 180
                
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
                text="Preview not available"
            )

    def _fetch_formats_thread(self, video):
        video_url = video.get("webpage_url", "")
        if not video_url:
            self.root.after(0, lambda: self.status_var.set("Failed to get video URL"))
            return
            
        try:
            command = ["yt-dlp", "-J", video_url]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            video_data = json.loads(result.stdout)
            
            formats = video_data.get("formats", [])
            format_options = []
            
            # Add video+audio merged formats for common resolutions
            quality_options = [("360p", 360), ("480p", 480), ("720p", 720), ("1080p", 1080), ("1440p", 1440), ("2160p", 2160)]
            
            for quality_name, height in quality_options:
                # Create a merged format option for each resolution
                merged_format = {
                    "format_id": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
                    "ext": "mp4",
                    "vcodec": "merged",
                    "acodec": "merged",
                    "format_note": f"Best {quality_name} merged",
                    "resolution": f"≤{quality_name}",
                    "is_merged": True
                }
                
                label = f"MERGED: Best video+audio (≤{quality_name})"
                format_options.append((label, merged_format))
            
            # Now add the individual formats
            for fmt in formats:
                format_id = fmt.get("format_id", "")
                format_note = fmt.get("format_note", "")
                resolution = fmt.get("resolution", "") or "N/A"
                ext = fmt.get("ext", "")
                vcodec = fmt.get("vcodec", "none")
                acodec = fmt.get("acodec", "none")
                filesize = fmt.get("filesize", None) or fmt.get("filesize_approx", None)
                bitrate = fmt.get("tbr", None)
                
                # Determine media type
                if vcodec != "none" and acodec != "none":
                    media_type = "Video+Audio"
                    prefix = "" 
                elif vcodec != "none":
                    media_type = "Video only"
                    prefix = ""
                else:
                    media_type = "Audio only"
                    prefix = ""
                
                # Format filesize if available
                size_str = ""
                if filesize:
                    size_str = f"{humanize.naturalsize(filesize)}"
                
                # Format bitrate if available
                bitrate_str = ""
                if bitrate:
                    bitrate_str = f"{bitrate:.1f} kbps"
                
                # Add codec information to provide more technical details
                codec_info = []
                if vcodec != "none":
                    codec_info.append(f"vcodec:{vcodec.split('.')[0]}")
                if acodec != "none":
                    codec_info.append(f"acodec:{acodec.split('.')[0]}")
                codec_str = " ".join(codec_info)
                
                # Create detailed format description
                details = []
                details.append(f"ID:{format_id}")
                if size_str:
                    details.append(size_str)
                if bitrate_str:
                    details.append(bitrate_str)
                if format_note:
                    details.append(format_note)
                if codec_str:
                    details.append(codec_str)
                
                details_str = " | ".join(details)
                if details_str:
                    details_str = f" ({details_str})"
                
                label = f"{prefix}{resolution} {ext} - {media_type}{details_str}"
                format_options.append((label, fmt))
            
            # Sort formats by type first, then by quality
            format_options.sort(key=lambda x: self._format_quality_sorter(x[1]), reverse=True)
            self.root.after(0, lambda: self._update_formats(format_options))
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Error fetching formats: {str(e)[:50]}"))

    def _format_quality_sorter(self, fmt):
        # Is this a merged format? Those go first
        is_merged = fmt.get("is_merged", False)
        if is_merged:
            # Put merged formats at the top with their height as priority
            height_str = fmt.get("resolution", "0p").replace("≤", "").replace("p", "")
            try:
                height = int(height_str)
            except:
                height = 0
            return (10, height, 0, 0, "")
    
        # Parse height from resolution
        height = 0
        resolution = fmt.get("resolution", "")
        match = re.search(r"(\d+)x(\d+)", resolution)
        if match:
            height = int(match.group(2))
        
        # Get media type (3=video+audio, 2=video only, 1=audio only)
        has_video = fmt.get("vcodec", "none") != "none"
        has_audio = fmt.get("acodec", "none") != "none"
        format_id = fmt.get("format_id", "0")
        
        # Determine media type category
        if has_video and has_audio:
            format_type = 3  # Combined video+audio
        elif has_video:
            format_type = 2  # Video only
        else:
            format_type = 1  # Audio only
            
        # Consider bitrate and filesize for quality
        bitrate = fmt.get("tbr", 0) or fmt.get("vbr", 0) or fmt.get("abr", 0) or 0
        filesize = fmt.get("filesize", 0) or fmt.get("filesize_approx", 0) or 0
        
        # Return tuple for sorting (keeping original sort order but adding more criteria)
        return (format_type, height, bitrate, filesize, format_id)

    def _update_formats(self, format_options):
        self.formats = format_options
        self.format_listbox.delete(0, tk.END)
        
        # Count combined formats
        combined_count = sum(1 for _, fmt in format_options 
                            if fmt.get("is_merged", False) or 
                            (fmt.get("vcodec", "none") != "none" and 
                             fmt.get("acodec", "none") != "none"))
        
        for i, (label, _) in enumerate(format_options):
            self.format_listbox.insert(tk.END, f"{i+1}. {label}")
        
        if format_options:
            self.status_var.set(f"Found {len(format_options)} formats ({combined_count} with video+audio). Select one.")
            # Auto-select best combined format
            self.select_best_combined_format()
        else:
            self.status_var.set("No formats available")

    def on_format_selected(self, event):
        selection = self.format_listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        if index >= 0 and index < len(self.formats):
            self.selected_format = self.formats[index][1]
            self.play_button["state"] = tk.NORMAL
            self.download_button["state"] = tk.NORMAL
            self.status_var.set("Format selected. Ready to play or download.")

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

    def play_video(self):
        if not self.current_video or not self.selected_format:
            messagebox.showwarning("Selection Error", "Please select a video and format first.")
            return
        
        # Stop any currently playing video
        self.stop_video()
        
        # Reset pause state
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")
            
        video_url = self.current_video.get("webpage_url", "")
        if not video_url:
            messagebox.showwarning("URL Error", "Failed to retrieve video URL.")
            return
            
        self.status_var.set("Preparing video for playback...")
        threading.Thread(target=self._setup_streaming, args=(video_url,), daemon=True).start()

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

    def _setup_streaming(self, video_url):
        try:
            # Check if we're using a merged format
            is_merged = self.selected_format.get("is_merged", False)
            
            if is_merged:
                # Use the format spec for merged video+audio
                format_spec = self.selected_format.get("format_id", "bestvideo+bestaudio/best")
                command = ["yt-dlp", "-f", format_spec, "-g", video_url]
            else:
                # Use the selected format ID
                format_id = self.selected_format.get("format_id", "best")
                command = ["yt-dlp", "-f", format_id, "-g", video_url]
            
            result = subprocess.run(command, capture_output=True, text=True, check=True)
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
            
        instance = vlc.Instance('--avcodec-hw=none')
        self.player = instance.media_player_new()
        
        media = instance.media_new(stream_url)
        self.player.set_media(media)
        
        # Get media properties
        media.parse()
        
        self.player.play()
        self.status_var.set("Playing video...")
        self.stop_button["state"] = tk.NORMAL
        self.pause_button["state"] = tk.NORMAL  # Enable pause button
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
                self.stop_video()
                self.status_var.set("Playback finished")
            elif self.player.get_state() == vlc.State.Paused:
                # Just continue checking while paused
                self.timer_id = self.root.after(500, self._update_playback)
            else:
                # Still loading or in another state, check again soon
                self.timer_id = self.root.after(500, self._update_playback)
        except Exception:
            # Handle any VLC errors
            self.stop_video()
            self.status_var.set("Playback error")

    def on_slider_press(self, event):
        self.slider_dragging = True

    def on_slider_release(self, event):
        if self.player:
            position = self.slider.get() / 100.0
            self.player.set_position(position)
        self.slider_dragging = False

    def stop_video(self):
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
        self.pause_button["state"] = tk.DISABLED  # Disable pause button
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")
        
        # Re-enable play button if format is selected
        if self.selected_format:
            self.play_button["state"] = tk.NORMAL

    def download_video(self):
        if not self.current_video or not self.selected_format:
            messagebox.showwarning("Selection Error", "Please select a video and format first.")
            return
            
        video_url = self.current_video.get("webpage_url", "")
        if not video_url:
            messagebox.showwarning("URL Error", "Failed to retrieve video URL.")
            return
            
        title = self.current_video.get("title", "video")
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}"
        
        # Get format information
        is_merged = self.selected_format.get("is_merged", False)
        
        if is_merged:
            # Use the format spec for merged video+audio
            format_spec = self.selected_format.get("format_id", "bestvideo+bestaudio/best")
            ext = "mp4"  # Default to mp4 for merged formats
        else:
            # Use the selected format ID
            format_spec = self.selected_format.get("format_id", "best")
            ext = self.selected_format.get("ext", "mp4")
        
        output_path = os.path.join(self.downloads_dir, f"{filename}.{ext}")
        
        self.status_var.set("Starting download...")
        self.download_progress["value"] = 0
        self.download_button["state"] = tk.DISABLED
        
        threading.Thread(
            target=self._download_thread, 
            args=(video_url, format_spec, output_path, is_merged),
            daemon=True
        ).start()

    def _download_thread(self, video_url, format_spec, output_path, is_merged):
        try:
            # Base command
            command = [
                "yt-dlp", 
                "-f", format_spec,
                "-o", output_path,
                "--newline"
            ]
            
            # If we're using a merged format, add merge options
            if is_merged:
                command.extend(["--merge-output-format", "mp4"])
            
            # Add the URL
            command.append(video_url)
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
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
            f"Video downloaded successfully!\nSaved to: {path}"
        )

    def _download_failed(self, error_msg):
        self.download_progress["value"] = 0
        self.status_var.set(f"Download failed: {error_msg}")
        self.download_button["state"] = tk.NORMAL
        
        messagebox.showerror("Download Error", f"Failed to download video: {error_msg}")

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
        print("Installing required package: humanize")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "humanize"])
        import humanize
        
    root = tk.Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()