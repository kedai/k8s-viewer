import os
import platform
import sys
from pathlib import Path

# Cache configuration
DEFAULT_CACHE_TTL = 30  # seconds
DEFAULT_CACHE_DIR = '~/.k8s_viewer'

# Logging configuration
def get_default_log_dir():
    """Get platform-specific default log directory"""
    system = platform.system()
    if system == 'Windows':
        # Windows: %LOCALAPPDATA%\k8s-viewer\logs
        return os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local')),
                          'k8s-viewer', 'logs')
    elif system == 'Darwin':  # macOS
        # macOS: ~/Library/Logs/k8s-viewer
        return os.path.expanduser('~/Library/Logs/k8s-viewer')
    else:  # Linux and others
        # Linux: ~/.local/state/k8s-viewer/logs (XDG Base Directory)
        xdg_state_home = os.environ.get('XDG_STATE_HOME', os.path.expanduser('~/.local/state'))
        return os.path.join(xdg_state_home, 'k8s-viewer', 'logs')

# Get log directory with environment variable override
LOG_DIR = os.getenv('K8S_VIEWER_LOG_DIR', get_default_log_dir())
LOG_FILE = 'k8s_viewer.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Get environment variables with defaults
CACHE_TTL = int(os.getenv('K8S_VIEWER_CACHE_TTL', str(DEFAULT_CACHE_TTL)))
CACHE_DIR = os.getenv('K8S_VIEWER_CACHE_DIR', DEFAULT_CACHE_DIR)
