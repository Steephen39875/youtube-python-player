import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import json
import vlc
from PIL import Image, ImageTk
import requests
import threading
import io
import os
import time
import re
import humanize
import shutil
import sys

class MediaDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Media Downloader")
        self.root.geometry("900x600")
        self.root.minsize(800, 550)
        
        # Check for required dependencies
        self._check_dependencies()
        
        # State variables
        self.videos = []
        self.current_media = None
        self.player = None
        self.formats = []
        self.selected_format = None
        self.cache = {"search": {}, "thumbnails": {}}
        self.downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "MediaDownloader")
        self.temp_dir = os.path.join(self.downloads_dir, "temp")
        os.makedirs(self.downloads_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        self.timer_id = None
        self.is_paused = False
        self.slider_dragging = False
        self.current_download_process = None
        
        # Create UI
        self._create_ui()
        self.search_entry.focus_set()
    
    def _check_dependencies(self):
        """Check for required external dependencies"""
        # Check for yt-dlp
        try:
            subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            messagebox.showerror("Dependency Error", 
                               "yt-dlp not found. Please install it and try again.")
            sys.exit(1)
        
        # Check for ffmpeg
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            messagebox.showerror("Dependency Error", 
                               "FFmpeg not found. Please install it and try again.")
            sys.exit(1)
            
        # Ensure humanize package is installed
        try:
            import humanize
        except ImportError:
            messagebox.showinfo("Installing Dependency", 
                              "Installing required Python package: humanize")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "humanize"])
    
    def _create_ui(self):
        # Main container
        main = ttk.Frame(self.root, padding="12")
        main.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid layout
        for i, w in enumerate([1, 1]): main.columnconfigure(i, weight=w)
        for i, w in enumerate([0, 1, 0, 0]): main.rowconfigure(i, weight=w)
        
        # Search bar
        search_frame = ttk.Frame(main)
        search_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        search_frame.columnconfigure(0, weight=1)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.search_entry.bind('<Return>', lambda e: self.search_media())
        
        ttk.Button(search_frame, text="Search", command=self.search_media, width=10).grid(row=0, column=1)
        
        # Left panel - Results list
        list_panel = ttk.Frame(main)
        list_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        list_panel.rowconfigure(1, weight=1)
        list_panel.columnconfigure(0, weight=1)
        
        ttk.Label(list_panel, text="Results").grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        list_container = ttk.Frame(list_panel)
        list_container.grid(row=1, column=0, sticky="nsew")
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)
        
        self.media_listbox = tk.Listbox(list_container)
        self.media_listbox.grid(row=0, column=0, sticky="nsew")
        self.media_listbox.bind('<<ListboxSelect>>', self.on_media_select)
        
        ttk.Scrollbar(list_container, orient="vertical", 
                     command=self.media_listbox.yview).grid(row=0, column=1, sticky="ns")
        self.media_listbox.configure(yscrollcommand=lambda f, l: 
                                    list_container.children["!scrollbar"].set(f, l))
        
        # Right panel - Details and controls
        details_panel = ttk.Frame(main)
        details_panel.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        details_panel.columnconfigure(0, weight=1)
        for i, w in enumerate([0, 1, 0, 0]): details_panel.rowconfigure(i, weight=w)
        
        # Title
        self.title_var = tk.StringVar(value="No media selected")
        ttk.Label(details_panel, textvariable=self.title_var, wraplength=400).grid(
            row=0, column=0, sticky="nw", pady=(0, 10))
        
        # Thumbnail
        thumbnail_frame = ttk.Frame(details_panel)
        thumbnail_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        thumbnail_frame.columnconfigure(0, weight=1)
        thumbnail_frame.rowconfigure(0, weight=1)
        
        self.preview_canvas = tk.Canvas(thumbnail_frame)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        
        # Info and format controls
        info_frame = ttk.Frame(details_panel)
        info_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        
        self.duration_var = tk.StringVar(value="Duration: --:--")
        ttk.Label(info_frame, textvariable=self.duration_var).grid(row=0, column=0, sticky="w")
        
        # Format controls
        format_frame = ttk.Frame(details_panel)
        format_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        
        # Quality selector
        quality_frame = ttk.Frame(details_panel)
        quality_frame.grid(row=4, column=0, sticky="ew", pady=(0, 5))
        
        ttk.Label(quality_frame, text="Quality:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.quality_var = tk.StringVar(value="720p")
        ttk.Combobox(quality_frame, textvariable=self.quality_var, width=10, 
                    values=["360p", "480p", "720p", "1080p", "1440p", "2160p"]).grid(row=0, column=1, sticky="w")
        
        # Best format button
        self.best_format_btn = ttk.Button(details_panel, text="Select Best Quality", 
                                      command=self.select_best_format, state=tk.DISABLED)
        self.best_format_btn.grid(row=3, column=0, sticky="e", pady=(0, 5))
        
        # Format list
        self.format_listbox = tk.Listbox(details_panel, height=6)
        self.format_listbox.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self.format_listbox.bind('<<ListboxSelect>>', self.on_format_selected)
        
        ttk.Scrollbar(details_panel, orient="vertical", 
                     command=self.format_listbox.yview).grid(row=5, column=1, sticky="ns")
        self.format_listbox.configure(yscrollcommand=lambda f, l: 
                                     details_panel.children["!scrollbar"].set(f, l))
        
        # Playback controls
        control_frame = ttk.Frame(main)
        control_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)
        for i in range(5): control_frame.columnconfigure(i, weight=1)
        
        self.play_button = ttk.Button(control_frame, text="▶ Play", command=self.play_media, 
                                   state=tk.DISABLED, width=12)
        self.play_button.grid(row=0, column=0, padx=5)
        
        self.pause_button = ttk.Button(control_frame, text="⏸️ Pause", command=self.toggle_pause, 
                                    state=tk.DISABLED, width=12)
        self.pause_button.grid(row=0, column=1, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="■ Stop", command=self.stop_media, 
                                   state=tk.DISABLED, width=12)
        self.stop_button.grid(row=0, column=2, padx=5)
        
        self.download_button = ttk.Button(control_frame, text="⬇ Download", command=self.download_media, 
                                       state=tk.DISABLED, width=12)
        self.download_button.grid(row=0, column=3, padx=5)
        
        self.cancel_button = ttk.Button(control_frame, text="✕ Cancel", command=self.cancel_download, 
                                     state=tk.DISABLED, width=12)
        self.cancel_button.grid(row=0, column=4, padx=5)
        
        # Playback slider
        slider_frame = ttk.Frame(main)
        slider_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
        slider_frame.columnconfigure(1, weight=1)
        
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        ttk.Label(slider_frame, textvariable=self.time_var).grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.slider = ttk.Scale(slider_frame, from_=0, to=100, orient="horizontal")
        self.slider.grid(row=0, column=1, sticky="ew")
        self.slider.bind("<ButtonPress-1>", lambda e: setattr(self, 'slider_dragging', True))
        self.slider.bind("<ButtonRelease-1>", self.on_slider_release)
        
        # Status bar
        status_frame = ttk.Frame(main)
        status_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        status_frame.columnconfigure(0, weight=1)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        
        self.progress = ttk.Progressbar(main, mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(5, 0))
    
    def search_media(self):
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Input Error", "Please enter a search query.")
            return
        
        self.stop_media()
        self.status_var.set(f"Searching for: {query}")
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()
    
    def _search_thread(self, query):
        if query in self.cache["search"]:
            videos = self.cache["search"][query]
        else:
            try:
                cmd = ["yt-dlp", "--flat-playlist", "--quiet", "--dump-json", f"ytsearch20:{query}"]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                videos = [json.loads(line) for line in result.stdout.splitlines()]
                self.cache["search"][query] = videos
            except Exception:
                videos = []
        
        self.root.after(0, lambda: self._update_search_results(videos))
    
    def _update_search_results(self, videos):
        if not videos:
            self.status_var.set("No media found.")
            return
            
        self.videos = videos
        self.media_listbox.delete(0, tk.END)
        
        for i, video in enumerate(videos):
            title = video.get("title", "N/A")
            duration = self._format_time(video.get("duration", 0))
            self.media_listbox.insert(tk.END, f"{i+1}. {title} [{duration}]")
            
            # Load thumbnail in background
            thumbnail_url = video.get("thumbnail", "")
            if thumbnail_url:
                threading.Thread(target=self._load_thumbnail, 
                               args=(thumbnail_url,), daemon=True).start()
        
        self.status_var.set(f"Found {len(videos)} results")
    
    def _load_thumbnail(self, url):
        if not url or url in self.cache["thumbnails"]:
            return
            
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                image = Image.open(io.BytesIO(response.content))
                self.cache["thumbnails"][url] = image
        except Exception:
            pass
    
    def show_thumbnail(self, url):
        try:
            if url in self.cache["thumbnails"]:
                image = self.cache["thumbnails"][url]
            else:
                response = requests.get(url, timeout=5)
                image = Image.open(io.BytesIO(response.content))
                self.cache["thumbnails"][url] = image
                
            # Calculate dimensions
            canvas_width = self.preview_canvas.winfo_width() or 320
            canvas_height = self.preview_canvas.winfo_height() or 180
            img_width, img_height = image.size
            ratio = min(canvas_width/img_width, canvas_height/img_height)
            new_width, new_height = int(img_width * ratio), int(img_height * ratio)
            
            # Resize and display
            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(resized)
            
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(
                (canvas_width - new_width) // 2, 
                (canvas_height - new_height) // 2, 
                anchor="nw", image=photo
            )
            self.preview_canvas.image = photo
            
        except Exception:
            self.preview_canvas.delete("all")
            self.preview_canvas.create_text(
                self.preview_canvas.winfo_width() // 2 or 160,
                self.preview_canvas.winfo_height() // 2 or 90,
                text="Preview not available"
            )
    
    def on_media_select(self, event):
        selection = self.media_listbox.curselection()
        if not selection:
            return
        
        # Stop current playback
        self.stop_media()
        
        # Reset format selection
        self.format_listbox.delete(0, tk.END)
        self._set_button_states({"play": False, "pause": False})
        
        index = selection[0]
        if index >= len(self.videos):
            return
            
        video = self.videos[index]
        self.current_media = video
        
        # Update UI
        self.title_var.set(video.get("title", "Unknown Title"))
        self.duration_var.set(f"Duration: {self._format_time(video.get('duration', 0))}")
        
        thumbnail_url = video.get("thumbnail", "")
        if thumbnail_url:
            self.show_thumbnail(thumbnail_url)
        
        # Enable best format button
        self.best_format_btn["state"] = tk.NORMAL
        
        # Fetch formats
        threading.Thread(target=self._fetch_formats, args=(video,), daemon=True).start()
        self.status_var.set("Loading formats...")
    
    def _fetch_formats(self, video):
        video_url = video.get("webpage_url", "")
        if not video_url:
            self.root.after(0, lambda: self.status_var.set("Failed to get URL"))
            return
            
        try:
            # Get format info
            cmd = ["yt-dlp", "-J", video_url]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            video_data = json.loads(result.stdout)
            
            formats = video_data.get("formats", [])
            format_options = []
            
            # Add merged formats for common resolutions
            for quality, height in [("360p", 360), ("480p", 480), ("720p", 720), 
                                  ("1080p", 1080), ("1440p", 1440), ("2160p", 2160)]:
                merged_format = {
                    "format_id": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
                    "ext": "mp4",
                    "is_merged": True,
                    "resolution": f"≤{quality}",
                    "format_note": f"Best {quality} merged"
                }
                
                label = f"MERGED: Best video+audio (≤{quality})"
                format_options.append((label, merged_format))
            
            # Add individual formats
            for fmt in formats:
                # Extract format details
                fmt_id = fmt.get("format_id", "")
                resolution = fmt.get("resolution", "") or "N/A"
                ext = fmt.get("ext", "")
                vcodec = fmt.get("vcodec", "none")
                acodec = fmt.get("acodec", "none")
                filesize = fmt.get("filesize") or fmt.get("filesize_approx")
                bitrate = fmt.get("tbr")
                
                # Determine media type
                if vcodec != "none" and acodec != "none":
                    media_type = "Video+Audio"
                elif vcodec != "none":
                    media_type = "Video only"
                else:
                    media_type = "Audio only"
                
                # Format details string
                details = [f"ID:{fmt_id}"]
                if filesize:
                    details.append(humanize.naturalsize(filesize))
                if bitrate:
                    details.append(f"{bitrate:.1f} kbps")
                if fmt.get("format_note"):
                    details.append(fmt.get("format_note"))
                if vcodec != "none":
                    details.append(f"vcodec:{vcodec.split('.')[0]}")
                if acodec != "none":
                    details.append(f"acodec:{acodec.split('.')[0]}")
                
                details_str = " | ".join(details)
                if details_str:
                    details_str = f" ({details_str})"
                
                label = f"{resolution} {ext} - {media_type}{details_str}"
                format_options.append((label, fmt))
            
            # Sort formats and update UI
            format_options.sort(key=self._format_sort_key, reverse=True)
            self.root.after(0, lambda: self._update_formats(format_options))
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Error: {str(e)[:50]}"))
    
    def _format_sort_key(self, format_item):
        _, fmt = format_item
        
        # Prioritize merged formats
        if fmt.get("is_merged", False):
            height_str = fmt.get("resolution", "0p").replace("≤", "").replace("p", "")
            return (10, int(height_str) if height_str.isdigit() else 0, 0, 0)
        
        # Parse height from resolution
        height = 0
        resolution = fmt.get("resolution", "")
        match = re.search(r"(\d+)x(\d+)", resolution)
        if match:
            height = int(match.group(2))
        
        # Categorize format type
        vcodec = fmt.get("vcodec", "none")
        acodec = fmt.get("acodec", "none")
        if vcodec != "none" and acodec != "none":
            format_type = 3  # Combined
        elif vcodec != "none":
            format_type = 2  # Video only
        else:
            format_type = 1  # Audio only
            
        # Consider quality metrics
        bitrate = fmt.get("tbr", 0) or fmt.get("vbr", 0) or fmt.get("abr", 0) or 0
        filesize = fmt.get("filesize", 0) or fmt.get("filesize_approx", 0) or 0
        
        return (format_type, height, bitrate, filesize)
    
    def _update_formats(self, format_options):
        self.formats = format_options
        self.format_listbox.delete(0, tk.END)
        
        for i, (label, _) in enumerate(format_options):
            self.format_listbox.insert(tk.END, f"{i+1}. {label}")
        
        if format_options:
            combined_count = sum(1 for _, fmt in format_options 
                                if fmt.get("is_merged", False) or 
                                (fmt.get("vcodec", "none") != "none" and 
                                fmt.get("acodec", "none") != "none"))
                                
            self.status_var.set(f"Found {len(format_options)} formats ({combined_count} with video+audio)")
            self.select_best_format()
        else:
            self.status_var.set("No formats available")
    
    def select_best_format(self):
        """Select best format based on current quality setting"""
        if not self.current_media:
            return
            
        quality_pref = self.quality_var.get().replace('p', '')
        target_height = int(quality_pref) if quality_pref.isdigit() else 720
        
        # Create merged format spec
        format_spec = {
            "format_id": f"bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]",
            "ext": "mp4",
            "is_merged": True,
            "format_note": f"Best {self.quality_var.get()} merged",
            "resolution": f"≤{self.quality_var.get()}"
        }
        
        self.selected_format = format_spec
        self._set_button_states({"play": True, "download": True})
        self.status_var.set(f"Selected best quality (≤{self.quality_var.get()})")
        
        # Update format selection in listbox
        self.format_listbox.selection_clear(0, tk.END)
        merged_format_text = f"0. MERGED: Best video+audio (≤{self.quality_var.get()})"
        
        # Add or update merged option at top
        if self.format_listbox.size() > 0 and self.format_listbox.get(0).startswith("0. MERGED:"):
            self.format_listbox.delete(0)
        
        self.format_listbox.insert(0, merged_format_text)
        self.format_listbox.selection_set(0)
        self.format_listbox.see(0)
    
    def on_format_selected(self, event):
        selection = self.format_listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        if index >= 0 and index < len(self.formats):
            self.selected_format = self.formats[index][1]
            self._set_button_states({"play": True, "download": True})
            self.status_var.set("Format selected. Ready to play or download.")
    
    def play_media(self):
        if not self.current_media or not self.selected_format:
            messagebox.showwarning("Selection Error", "Please select media and format first.")
            return
        
        self.stop_media()
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")
            
        video_url = self.current_media.get("webpage_url", "")
        if not video_url:
            messagebox.showwarning("URL Error", "Failed to retrieve URL.")
            return
            
        self.status_var.set("Preparing media for playback...")
        threading.Thread(target=self._setup_streaming, args=(video_url,), daemon=True).start()
    
    def _setup_streaming(self, video_url):
        """Prepare media for playback with proper format handling"""
        try:
            # Get format specification
            is_merged = self.selected_format.get("is_merged", False)
            format_spec = self.selected_format.get("format_id", "best")
            
            # Create a unique temp directory for this playback session
            temp_id = f"playback_{int(time.time())}"
            temp_path = os.path.join(self.temp_dir, temp_id)
            os.makedirs(temp_path, exist_ok=True)
            
            if is_merged:
                # For merged formats, we'll download video and audio separately 
                # and handle the merging ourselves or use direct FFmpeg streaming
                self.root.after(0, lambda: self.status_var.set("Extracting streams..."))
                
                # Get best video and audio URLs based on format spec
                cmd = ["yt-dlp", "-f", format_spec, "-g", video_url]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                stream_urls = result.stdout.strip().split('\n')
                
                if len(stream_urls) >= 2:
                    # We have separate video and audio URLs
                    video_url = stream_urls[0]
                    audio_url = stream_urls[1]
                    
                    # Create a merged stream file for VLC
                    merged_path = os.path.join(temp_path, "merged_stream.mp4")
                    
                    # Use FFmpeg to create a playable file
                    ffmpeg_cmd = [
                        "ffmpeg", "-y", "-i", video_url, "-i", audio_url,
                        "-c:v", "copy", "-c:a", "aac", merged_path
                    ]
                    
                    # Run FFmpeg process with progress monitoring
                    process = subprocess.Popen(
                        ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        universal_newlines=True
                    )
                    
                    # Monitor progress
                    for line in process.stdout:
                        if "time=" in line:
                            # Update status with processing progress
                            self.root.after(0, lambda l=line: 
                                         self.status_var.set(f"Processing: {l.strip()}"))
                    
                    process.wait()
                    
                    # Start playback once file is ready
                    if process.returncode == 0 and os.path.exists(merged_path):
                        self.root.after(0, lambda: self._start_player(merged_path))
                    else:
                        # If FFmpeg fails, try direct play with the video URL
                        self.root.after(0, lambda: self._start_player(video_url))
                else:
                    # If we only got one URL, just use it
                    self.root.after(0, lambda: self._start_player(stream_urls[0]))
            else:
                # For single formats, just get the URL and play directly
                cmd = ["yt-dlp", "-f", format_spec, "-g", video_url]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                stream_url = result.stdout.strip().split('\n')[0]
                self.root.after(0, lambda: self._start_player(stream_url))
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Error: {str(e)[:50]}"))
    
    def _start_player(self, stream_url):
        # Clean up existing player
        self._cleanup_player()
            
        # Create new player with enhanced options
        instance = vlc.Instance('--input-repeat=1', '--no-video-title-show')
        self.player = instance.media_player_new()
        
        # Set media
        media = instance.media_new(stream_url)
        self.player.set_media(media)
        
        # Set hardware acceleration if available
        self.player.set_hwnd(self.preview_canvas.winfo_id())
        
        # Start playback
        self.player.play()
        
        # Update UI
        self.status_var.set("Playing media...")
        self._set_button_states({"play": False, "pause": True, "stop": True})
        
        # Reset pause state
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")
        
        # Start playback updates
        self.root.after(500, self._update_playback)
    
    def _update_playback(self):
        if not self.player:
            return
            
        try:
            # Get player state
            state = self.player.get_state()
            
            if state in [vlc.State.Playing, vlc.State.Paused]:
                # Update position and time
                current_ms = self.player.get_time()
                length = self.player.get_length()
                
                if length > 0 and not self.slider_dragging:
                    # Update slider and time display
                    self.slider.set((current_ms / length) * 100)
                    current_sec, total_sec = current_ms // 1000, length // 1000
                    self.time_var.set(f"{self._format_time(current_sec)} / {self._format_time(total_sec)}")
                
                # Schedule next update
                self.timer_id = self.root.after(500, self._update_playback)
            elif state == vlc.State.Ended:
                self.stop_media()
                self.status_var.set("Playback finished")
            elif state == vlc.State.Error:
                self.stop_media()
                self.status_var.set("Playback error occurred")
            else:
                # Continue checking (still loading or in transition)
                self.timer_id = self.root.after(500, self._update_playback)
        except Exception as e:
            self.stop_media()
            self.status_var.set(f"Playback error: {str(e)[:50]}")
    
    def toggle_pause(self):
        if not self.player:
            return
            
        if self.is_paused:
            # Resume
            self.player.play()
            self.is_paused = False
            self.pause_button.config(text="⏸️ Pause")
            self.status_var.set("Playback resumed")
        else:
            # Pause
            self.player.pause()
            self.is_paused = True
            self.pause_button.config(text="▶️ Continue")
            self.status_var.set("Playback paused")
    
    def on_slider_release(self, event):
        self.slider_dragging = False
        if self.player:
            position = self.slider.get() / 100.0
            self.player.set_position(position)
    
    def stop_media(self):
        self._cleanup_player()
        
        # Reset UI
        self.slider.set(0)
        self.time_var.set("0:00 / 0:00")
        self.status_var.set("Playback stopped")
        self._set_button_states({"stop": False, "pause": False})
        
        # Reset pause state
        self.is_paused = False
        self.pause_button.config(text="⏸️ Pause")
        
        # Re-enable play if format selected
        if self.selected_format:
            self.play_button["state"] = tk.NORMAL
    
    def _cleanup_player(self):
        # Cancel update timer
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
            
        # Stop player
        if self.player:
            self.player.stop()
            self.player.release()
            self.player = None
    
    def download_media(self):
        if not self.current_media or not self.selected_format:
            messagebox.showwarning("Selection Error", "Please select media and format first.")
            return
            
        video_url = self.current_media.get("webpage_url", "")
        if not video_url:
            messagebox.showwarning("URL Error", "Failed to retrieve URL.")
            return
        
        # Prompt user for save location
        title = self.current_media.get("title", "media")
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        default_filename = f"{safe_title}_{timestamp}.mp4"
        
        save_path = filedialog.asksaveasfilename(
            initialdir=self.downloads_dir,
            initialfile=default_filename,
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4"), ("All Files", "*.*")]
        )
        
        if not save_path:
            return  # User cancelled
        
        # Get format details
        is_merged = self.selected_format.get("is_merged", False)
        format_spec = self.selected_format.get("format_id", "best")
        
        # Start download
        self.status_var.set("Starting download...")
        self.progress["value"] = 0
        self._set_button_states({"download": False, "cancel": True})
        
        threading.Thread(
            target=self._download_thread, 
            args=(video_url, format_spec, save_path, is_merged),
            daemon=True
        ).start()
    
    def _download_thread(self, video_url, format_spec, output_path, is_merged):
        try:
            # Build command
            cmd = ["yt-dlp", "-f", format_spec, "-o", output_path, "--newline"]
            
            # Add specific options for merged formats to ensure proper handling
            if is_merged:
                ext = os.path.splitext(output_path)[1].lstrip('.') or "mp4"
                cmd.extend([
                    "--merge-output-format", ext,
                    "--remux-video", ext,
                    "--ffmpeg-location", self._get_ffmpeg_path()
                ])
            
            cmd.append(video_url)
            
            # Run download process
            self.current_download_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            
            # Monitor progress
            for line in self.current_download_process.stdout:
                if self.current_download_process is None:  # Check if cancelled
                    break
                    
                if "%" in line:
                    try:
                        match = re.search(r'(\d+\.?\d*)%', line)
                        if match:
                            percent = float(match.group(1))
                            self.root.after(0, lambda p=percent, l=line: 
                                        self.progress.configure(value=p) or 
                                        self.status_var.set(f"Downloading: {p:.1f}% - {l.strip()}"))
                    except Exception:
                        self.root.after(0, lambda l=line: self.status_var.set(f"Download: {l.strip()}"))
            
            if self.current_download_process:  # Check if not cancelled
                self.current_download_process.wait()
                
                if self.current_download_process.returncode == 0:
                    self.root.after(0, lambda: self._download_complete(output_path))
                else:
                    self.root.after(0, lambda: self._download_failed("Download failed"))
                
        except Exception as e:
            self.root.after(0, lambda: self._download_failed(str(e)))
        finally:
            self.current_download_process = None

    def cancel_download(self):
        """Cancel the current download process"""
        if self.current_download_process:
            # Terminate the process
            try:
                self.current_download_process.terminate()
                self.current_download_process = None
                
                self.root.after(0, lambda: (
                    self.status_var.set("Download cancelled"),
                    self.progress.configure(value=0),
                    self._set_button_states({"download": True, "cancel": False})
                ))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"Error cancelling: {str(e)[:50]}"))

    def _download_complete(self, path):
        self.progress["value"] = 100
        self.status_var.set("Download complete!")
        self._set_button_states({"download": True, "cancel": False})
        
        messagebox.showinfo(
            "Download Complete", 
            f"Media downloaded successfully!\nSaved to: {path}"
        )

    def _download_failed(self, error_msg):
        self.progress["value"] = 0
        self.status_var.set(f"Download failed: {error_msg}")
        self._set_button_states({"download": True, "cancel": False})
        
        messagebox.showerror("Download Error", f"Failed to download media: {error_msg}")

    def _set_button_states(self, states=None):
        """Update button states based on dictionary of button:state pairs"""
        states = states or {}
        
        if "play" in states:
            self.play_button["state"] = tk.NORMAL if states["play"] else tk.DISABLED
        if "pause" in states:
            self.pause_button["state"] = tk.NORMAL if states["pause"] else tk.DISABLED
        if "stop" in states:
            self.stop_button["state"] = tk.NORMAL if states["stop"] else tk.DISABLED
        if "download" in states:
            self.download_button["state"] = tk.NORMAL if states["download"] else tk.DISABLED
        if "cancel" in states:
            self.cancel_button["state"] = tk.NORMAL if states["cancel"] else tk.DISABLED

    def _format_time(self, seconds):
        """Format seconds into readable time string"""
        if not seconds:
            return "--:--"
            
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def _get_ffmpeg_path(self):
        """Find the FFmpeg executable path"""
        try:
            # Try to find ffmpeg in PATH
            result = subprocess.run(["which", "ffmpeg"] if os.name != 'nt' else ["where", "ffmpeg"], 
                                  capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
            
            # Default paths to check
            default_paths = []
            
            if os.name == 'nt':  # Windows
                default_paths = [
                    os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'ffmpeg', 'bin', 'ffmpeg.exe'),
                    os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'ffmpeg', 'bin', 'ffmpeg.exe'),
                    os.path.join(os.path.dirname(sys.executable), 'ffmpeg.exe')
                ]
            else:  # macOS/Linux
                default_paths = [
                    '/usr/bin/ffmpeg', 
                    '/usr/local/bin/ffmpeg',
                    '/opt/homebrew/bin/ffmpeg'
                ]
            
            # Check default paths
            for path in default_paths:
                if os.path.isfile(path):
                    return path
            
            # If we can't find it, just return "ffmpeg" and hope it's in PATH
            return "ffmpeg"
            
        except Exception:
            return "ffmpeg"
    
    def cleanup_temp_files(self):
        """Clean up temporary files"""
        try:
            # Remove temp directory
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                os.makedirs(self.temp_dir, exist_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    # Set up high DPI awareness for better UI scaling
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
        
    # Make sure we have required modules
    try:
        import humanize
    except ImportError:
        import sys
        print("Installing required package: humanize")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "humanize"])
        import humanize
        
    # Create root window and app
    root = tk.Tk()
    app = MediaDownloaderApp(root)
    
    # Setup cleanup on exit
    root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup_temp_files(), root.destroy()))
    
    # Start main loop
    root.mainloop()