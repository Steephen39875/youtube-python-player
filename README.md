YouTube-Python-Player
🎵 A Lightweight YouTube Video & Music Player Built with Python (Tkinter, VLC, Pytube)

This Python-based application allows you to search, stream, and download YouTube videos and audio directly from a simple Tkinter GUI. It leverages the power of Pytube for fetching streams, VLC for smooth playback, and Tkinter for an intuitive interface.

🔥 Why I Created This Project
I wanted to build a fast, offline-friendly YouTube player that avoids heavy web-based players and ads. Unlike browser-based streaming, this app:

Reduces resource usage (no browser overhead).

Supports high-quality audio extraction (for music lovers).

Allows video/audio downloads without external websites.

Customizable & open-source (modify it as needed).

🛠 Features
1. Core App (core_app.py - In Development)
Lists all available video & audio formats from YouTube search results.

Built with Tkinter (GUI), Pytube (YouTube data), and VLC (playback).

Current Issue: Separately fetches video & audio streams but struggles to merge them during playback.

2. Music Player (musicapp.py - Fully Functional)
Extracts & plays only the highest bitrate audio (ideal for music).

Supports streaming & downloading in MP3 format.

3. VLC Finder (vlc_finder.py)
Ensures VLC dependencies are detected before packaging the app into an .exe (using PyInstaller).

📥 Installation & Usage
Install dependencies:

sh
pip install pytube python-vlc tkinter pyinstaller
Run the app:

sh
python musicapp.py  # For music-only mode
python core_app.py  # For video playback (under development)
Build to .exe (optional):

sh
pyinstaller --onefile --windowed musicapp.py
🚧 Future Improvements
Fix video+audio sync issue in core_app.py.

Add playlist support & batch downloads.

Improve UI/UX with modern themes.

📜 License
Open-source under MIT License – feel free to modify and distribute!

🔗 Contribute or Report Issues: GitHub Issues

