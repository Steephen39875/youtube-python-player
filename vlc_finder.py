import os
import sys
import shutil
import vlc  # Make sure python-vlc is installed

def get_vlc_path():
    """Get the path to VLC installation."""
    if sys.platform.startswith('win'):
        # Try common installation locations
        possible_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'VideoLAN', 'VLC'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), 'VideoLAN', 'VLC'),
            # Try to get from python-vlc module
            os.path.dirname(vlc.__file__)
        ]
        
        for path in possible_paths:
            if os.path.exists(path) and os.path.isfile(os.path.join(path, 'libvlc.dll')):
                return path
    return None

def copy_vlc_files(vlc_path, target_dir):
    """Copy VLC files to target directory."""
    if not vlc_path:
        print("VLC installation not found!")
        return False
    
    try:
        # Copy DLLs
        for file in ['libvlc.dll', 'libvlccore.dll']:
            src = os.path.join(vlc_path, file)
            if os.path.exists(src):
                shutil.copy2(src, target_dir)
                print(f"Copied {file}")
        
        # Copy plugins directory
        plugins_dir = os.path.join(vlc_path, 'plugins')
        if os.path.exists(plugins_dir):
            target_plugins = os.path.join(target_dir, 'plugins')
            if os.path.exists(target_plugins):
                shutil.rmtree(target_plugins)
            shutil.copytree(plugins_dir, target_plugins)
            print("Copied plugins directory")
        
        return True
    except Exception as e:
        print(f"Error copying VLC files: {e}")
        return False

if __name__ == "__main__":
    vlc_path = get_vlc_path()
    if vlc_path:
        print(f"Found VLC at: {vlc_path}")
        if copy_vlc_files(vlc_path, os.getcwd()):
            print("VLC files copied successfully. Ready to build with PyInstaller.")
        else:
            print("Failed to copy VLC files.")
    else:
        print("VLC installation not found. Please install VLC or copy files manually.")