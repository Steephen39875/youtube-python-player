import tkinter as tk
from tkinter import ttk, messagebox
import subprocess, json, vlc, threading, os, time, re, humanize, sys

class App:
    def __init__(self, root):
        self.root = root
        root.title("YT-DLP")
        root.geometry("600x450")
        root.minsize(500, 400)
        
        # State vars
        self.tracks = []
        self.player = self.current = None
        self.fmt = self.avail_fmts = []
        self.cache = {}
        self.dl_dir = os.path.join(os.path.expanduser("~"), "Downloads", "MusicPlayer")
        os.makedirs(self.dl_dir, exist_ok=True)
        self.timer = None
        self.paused = self.dragging = False
        
        self.create_ui()
        self.search_entry.focus_set()
    
    def create_ui(self):
        mf = ttk.Frame(self.root, padding="10")
        mf.pack(fill=tk.BOTH, expand=True)
        
        # Grid config
        mf.columnconfigure(0, weight=1)
        for i, w in enumerate([0, 0, 1, 0, 0, 0]): mf.rowconfigure(i, weight=w)
        
        # Search 
        sf = ttk.Frame(mf)
        sf.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        sf.columnconfigure(0, weight=1)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(sf, textvariable=self.search_var, font=('Helvetica', 11))
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.search_entry.bind('<Return>', lambda e: self.search())
        
        ttk.Button(sf, text="🔍", command=self.search).grid(row=0, column=1, sticky="e")
        
        # Info label
        ttk.Label(mf, text="Player: VLC Media Player | Downloader: yt-dlp", 
                font=('Helvetica', 9)).grid(row=1, column=0, sticky="w", pady=5)
        
        # Results list
        lf = ttk.LabelFrame(mf, text="Results")
        lf.grid(row=2, column=0, sticky="nsew", pady=5)
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        
        self.list = tk.Listbox(lf, font=('Helvetica', 10), 
                              selectbackground="#a6a6a6", selectforeground="black")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.list.yview)
        self.list.config(yscrollcommand=sb.set)
        
        self.list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 5), pady=5)
        self.list.bind('<<ListboxSelect>>', self.on_select)
        
        # Track info
        if_frame = ttk.Frame(mf)
        if_frame.grid(row=3, column=0, sticky="ew", pady=5)
        
        self.title_var = tk.StringVar(value="No track selected")
        ttk.Label(if_frame, textvariable=self.title_var, 
                wraplength=580, font=('Helvetica', 10, 'bold')).pack(anchor="w")
        
        self.info_var = tk.StringVar(value="Duration: --:-- | Format: -- | Size: --")
        ttk.Label(if_frame, textvariable=self.info_var).pack(anchor="w")
        
        # Controls
        cf = ttk.Frame(mf)
        cf.grid(row=4, column=0, sticky="ew", pady=5)
        
        # Player controls
        btns = ttk.Frame(cf)
        btns.pack(side=tk.LEFT)
        
        self.play_btn = ttk.Button(btns, text="▶", command=self.play, state=tk.DISABLED, width=3)
        self.pause_btn = ttk.Button(btns, text="⏸", command=self.toggle_pause, state=tk.DISABLED, width=3)
        self.stop_btn = ttk.Button(btns, text="⏹", command=self.stop, state=tk.DISABLED, width=3)
        
        for b in (self.play_btn, self.pause_btn, self.stop_btn): b.pack(side=tk.LEFT, padx=3)
        
        # Download controls
        dlf = ttk.Frame(cf)
        dlf.pack(side=tk.RIGHT)
        
        self.fmt_var = tk.StringVar(value="Select Format")
        self.fmt_sel = ttk.Combobox(dlf, textvariable=self.fmt_var, state="readonly", width=40)
        self.fmt_sel.pack(side=tk.LEFT, padx=5)
        
        self.dl_btn = ttk.Button(dlf, text="⬇", command=self.download, state=tk.DISABLED, width=3)
        self.dl_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress bar
        pf = ttk.Frame(mf)
        pf.grid(row=5, column=0, sticky="ew", pady=5)
        pf.columnconfigure(1, weight=1)
        
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        ttk.Label(pf, textvariable=self.time_var).grid(row=0, column=0, sticky="w", padx=(0, 5))
        
        self.slider = ttk.Scale(pf, from_=0, to=100, orient="horizontal")
        self.slider.grid(row=0, column=1, sticky="ew")
        self.slider.bind("<ButtonPress-1>", lambda e: setattr(self, 'dragging', True))
        self.slider.bind("<ButtonRelease-1>", self.on_slider_release)
        
        # Status bar
        self.status = tk.StringVar(value="Ready")
        ttk.Label(mf, textvariable=self.status, relief=tk.SUNKEN, anchor=tk.W).grid(
            row=6, column=0, sticky="ew", pady=(5, 0))
    
    def on_slider_release(self, e):
        if self.player:
            pos, length = self.slider.get(), self.player.get_length()
            self.player.set_time(int(length * (pos / 100)))
        self.dragging = False
    
    def run_cmd(self, cmd, capture=True, check=False):
        si = None
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        return subprocess.run(cmd, capture_output=capture, text=True, 
                           startupinfo=si, check=check) if capture else \
               subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                             text=True, startupinfo=si)
    
    def search(self):
        q = self.search_var.get().strip()
        if not q:
            messagebox.showwarning("Input Error", "Please enter a search query.")
            return
        
        self.stop()
        self.status.set(f"Searching for: {q}")
        threading.Thread(target=self._search_thread, args=(q,), daemon=True).start()

    def _search_thread(self, q):
        try:
            if q in self.cache:
                tracks = self.cache[q]
            else:
                result = self.run_cmd(["yt-dlp", "--flat-playlist", "--quiet", "--dump-json", f"ytsearch20:{q}"], check=True)
                tracks = [json.loads(line) for line in result.stdout.splitlines()]
                self.cache[q] = tracks
                
            self.root.after(0, lambda: self._update_results(tracks))
        except Exception as e:
            self.root.after(0, lambda: self.status.set(f"Search error: {str(e)[:50]}"))

    def _update_results(self, tracks):
        self.tracks = tracks
        self.list.delete(0, tk.END)
        
        if not tracks:
            self.status.set("No tracks found.")
            return
            
        for i, t in enumerate(tracks):
            title = t.get("title", "N/A")
            dur = self.fmt_time(t.get("duration", 0))
            self.list.insert(tk.END, f"{i+1}. {title} [{dur}]")
        
        self.status.set(f"Found {len(tracks)} tracks")

    def fmt_time(self, secs):
        if not secs: return "--:--"
        secs = int(secs)
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

    def on_select(self, e):
        sel = self.list.curselection()
        if not sel: return
        
        self.stop()
        
        for b in [self.play_btn, self.pause_btn, self.dl_btn]: b["state"] = tk.DISABLED
        
        self.fmt_sel["values"] = []
        self.fmt_var.set("Loading formats...")
            
        idx = sel[0]
        if idx >= len(self.tracks): return
            
        track = self.tracks[idx]
        self.current = track
        
        self.title_var.set(track.get("title", "Unknown Title"))
        self.info_var.set(f"Duration: {self.fmt_time(track.get('duration', 0))} | Loading format info...")
        
        threading.Thread(target=self._fetch_formats, args=(track,), daemon=True).start()
        self.status.set("Finding available formats...")

    def _fetch_formats(self, track):
        url = track.get("webpage_url", "")
        if not url:
            self.root.after(0, lambda: self.status.set("Failed to get track URL"))
            return
            
        try:
            result = self.run_cmd(["yt-dlp", "-J", url], check=True)
            data = json.loads(result.stdout)
            fmts = data.get("formats", [])
            
            # Add special formats first
            proc_fmts = [
                {"format_id": "bestaudio/best", "ext": "best", "display_name": "Best Audio Quality (auto format)", "is_special": True},
                {"format_id": "mp3", "ext": "mp3", "display_name": "MP3 Audio (converted)", "is_special": True}
            ]
            
            # Include audio formats
            for f in fmts:
                if f.get("acodec", "none") != "none":
                    ext = f.get("ext", "unknown")
                    fid = f.get("format_id", "unknown")
                    abr = f.get("abr", f.get("tbr", 0))
                    br_str = f"{abr:.1f}kbps" if abr else "?"
                    fsize = f.get("filesize", None) or f.get("filesize_approx", None)
                    size_str = humanize.naturalsize(fsize) if fsize else "?"
                    is_audio = f.get("vcodec", "") == "none"
                    type_str = "Audio" if is_audio else "A+V"
                    
                    details = [fid, ext, type_str, br_str]
                    
                    if not is_audio and f.get("height"):
                        details.append(f"{f.get('height')}p")
                    
                    details.append(size_str)
                    
                    f["display_name"] = " | ".join(details)
                    proc_fmts.append(f)
            
            self.avail_fmts = proc_fmts
            self.fmt = proc_fmts[0] if proc_fmts else None
            self.root.after(0, lambda: self._update_formats(proc_fmts))
            
        except Exception as e:
            print(f"Format error: {str(e)}")
            self.root.after(0, lambda: self.status.set(f"Error: {str(e)[:50]}"))

    def _update_formats(self, fmts):
        display = [f["display_name"] for f in fmts]
        
        self.fmt_sel["values"] = display
        if display: self.fmt_sel.current(0)
        
        if self.fmt:
            if self.fmt.get("is_special", False):
                best = None
                best_q = 0
                
                for f in fmts:
                    if f.get("is_special", False): continue
                    if f.get("vcodec", "") == "none":
                        q = f.get("abr", f.get("tbr", 0) or 0)
                        if q > best_q:
                            best_q = q
                            best = f
                
                if best:
                    br = best.get("abr", best.get("tbr", 0))
                    fsize = best.get("filesize") or best.get("filesize_approx")
                    ext = best.get("ext", "mp3")
                else:
                    br, fsize, ext = 0, None, self.fmt.get("ext", "mp3")
            else:
                br = self.fmt.get("abr", self.fmt.get("tbr", 0))
                fsize = self.fmt.get("filesize") or self.fmt.get("filesize_approx")
                ext = self.fmt.get("ext", "mp3")
            
            br_str = f"{br:.1f} kbps" if br else "Unknown"
            dur = self.current.get("duration", 0)
            
            if not fsize and br and dur:
                est = (br * dur) / 8
                size_str = humanize.naturalsize(est * 1000) + " (est.)"
            elif fsize:
                size_str = humanize.naturalsize(fsize)
            else:
                size_str = "Unknown"
                
            self.info_var.set(f"Duration: {self.fmt_time(dur)} | Format: {ext} | Size: {size_str}")
        
        self.play_btn["state"] = self.dl_btn["state"] = tk.NORMAL
        self.status.set(f"Ready. {len(fmts)} formats available.")

    def play(self):
        if not self.current:
            messagebox.showwarning("Selection Error", "Please select a track first.")
            return
        
        self.stop()
        self.paused = False
        self.pause_btn.config(text="⏸")
            
        url = self.current.get("webpage_url", "")
        if not url:
            messagebox.showwarning("URL Error", "Failed to retrieve track URL.")
            return
            
        self.status.set("Preparing audio...")
        threading.Thread(target=self._setup_stream, args=(url,), daemon=True).start()

    def toggle_pause(self):
        if not self.player: return
            
        if self.paused:
            self.player.play()
            self.paused = False
            self.pause_btn.config(text="⏸")
            self.status.set("Playback resumed")
        else:
            self.player.pause()
            self.paused = True
            self.pause_btn.config(text="▶")
            self.status.set("Playback paused")

    def _setup_stream(self, url):
        try:
            fmt_spec = "bestaudio/best" if self.fmt.get("is_special", False) else self.fmt.get("format_id", "bestaudio/best")
            result = self.run_cmd(["yt-dlp", "-f", fmt_spec, "-g", url], check=True)
            stream_url = result.stdout.strip()
            self.root.after(0, lambda: self._start_player(stream_url))
        except Exception as e:
            print(f"Streaming error: {str(e)}")
            self.root.after(0, lambda: self.status.set(f"Error: {str(e)[:50]}"))

    def _start_player(self, stream_url):
        self._cleanup()
            
        inst = vlc.Instance('--no-video', '--quiet')
        self.player = inst.media_player_new()
        
        media = inst.media_new(stream_url)
        self.player.set_media(media)
        media.parse()
        self.player.play()
        
        self.status.set("Playing audio with VLC...")
        self.stop_btn["state"] = self.pause_btn["state"] = tk.NORMAL
        self.play_btn["state"] = tk.DISABLED
        
        self.root.after(500, self._update_playback)
    
    def _cleanup(self):
        if self.player:
            self.player.stop()
            self.player = None
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None

    def _update_playback(self):
        if not self.player: return
            
        try:
            curr = self.player.get_time()
            total = self.player.get_length()
            
            if total > 0 and not self.dragging:
                pos = (curr / total) * 100
                self.slider.set(pos)
                
                curr_sec, total_sec = curr // 1000, total // 1000
                curr_str, total_str = self.fmt_time(curr_sec), self.fmt_time(total_sec)
                self.time_var.set(f"{curr_str} / {total_str}")
            
            if self.player.get_state() == vlc.State.Ended:
                self.stop()
                self.status.set("Playback finished")
            else:
                self.timer = self.root.after(500, self._update_playback)
                
        except Exception as e:
            print(f"Playback error: {str(e)}")
            self.stop()
            self.status.set("Playback error")

    def stop(self):
        self._cleanup()
        self.slider.set(0)
        self.time_var.set("0:00 / 0:00")
        self.status.set("Playback stopped")
        self.stop_btn["state"] = self.pause_btn["state"] = tk.DISABLED
        self.paused = False
        self.pause_btn.config(text="⏸")
        
        if self.fmt: self.play_btn["state"] = tk.NORMAL

    def download(self):
        if not self.current:
            messagebox.showwarning("Selection Error", "Please select a track first.")
            return
            
        url = self.current.get("webpage_url", "")
        if not url:
            messagebox.showwarning("URL Error", "Failed to retrieve track URL.")
            return
        
        sel_idx = self.fmt_sel.current()
        if sel_idx < 0 or sel_idx >= len(self.avail_fmts):
            messagebox.showwarning("Format Error", "Please select a download format.")
            return
            
        sel_fmt = self.avail_fmts[sel_idx]
        
        title = self.current.get("title", "audio")
        safe = re.sub(r'[^a-zA-Z0-9]', "", title)[:20]
        ts = str(int(time.time()))
        fname = f"{safe}_{ts}"
        
        out_path = os.path.join(self.dl_dir, fname)
        
        self.status.set("Starting download...")
        self.slider.set(0)
        self.dl_btn["state"] = tk.DISABLED
        
        threading.Thread(target=self._dl_thread, args=(url, out_path, sel_fmt), daemon=True).start()

    def _dl_thread(self, url, path, fmt):
        try:
            cmd = ["yt-dlp", "-o", f"{path}.%(ext)s", "--no-playlist"]
            
            if fmt.get("is_special") and fmt.get("ext") == "mp3":
                cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
            elif fmt.get("is_special"):
                cmd.extend(["-f", "bestaudio/best"])
            else:
                cmd.extend(["-f", fmt.get("format_id")])
            
            cmd.append(url)
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                dl_file = None
                for file in os.listdir(self.dl_dir):
                    if file.startswith(os.path.basename(path)):
                        dl_file = os.path.join(self.dl_dir, file)
                        break
                        
                if dl_file:
                    self.root.after(0, lambda: self._dl_complete(dl_file))
                else:
                    self.root.after(0, lambda: self._dl_failed("File downloaded but not found"))
            else:
                err = result.stderr if result.stderr else "Unknown error"
                self.root.after(0, lambda: self._dl_failed(f"yt-dlp error: {err[:100]}"))
                
        except Exception as e:
            self.root.after(0, lambda: self._dl_failed(str(e)))

    def _dl_complete(self, path):
        self.slider.set(100)
        self.status.set("Download complete!")
        self.dl_btn["state"] = tk.NORMAL
        
        messagebox.showinfo(
            "Download Complete", 
            f"Audio downloaded successfully!\nSaved to: {path}\n\nClick OK to open containing folder."
        )
        
        try:
            dir_path = os.path.dirname(path)
            if os.name == 'nt':
                os.startfile(dir_path)
            elif os.name == 'posix':
                if sys.platform == 'darwin':
                    subprocess.call(['open', dir_path])
                else:
                    subprocess.call(['xdg-open', dir_path])
        except Exception as e:
            print(f"Error opening folder: {str(e)}")

    def _dl_failed(self, err):
        self.slider.set(0)
        self.status.set(f"Download failed: {err[:50]}...")
        self.dl_btn["state"] = tk.NORMAL
        messagebox.showerror("Download Error", f"Failed to download audio:\n{err}")

def resource_path(rel_path):
    return os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), rel_path)

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
        
    try:
        import humanize
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "humanize"])
        import humanize
    
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        messagebox.showerror("Missing Dependency", 
                        "yt-dlp is not installed or not in your PATH. Please install it to use this application.")
        sys.exit(1)
    
    if getattr(sys, 'frozen', False):
        vlc_path = resource_path(os.path.join('vlc', 'plugins'))
        os.environ['VLC_PLUGIN_PATH'] = vlc_path
        os.environ["YTDLP_FILENAME"] = resource_path("yt-dlp.exe")
        
    root = tk.Tk()
    app = App(root)
    root.mainloop()