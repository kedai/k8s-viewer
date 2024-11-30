import json
import logging
import os
import subprocess
import time
from typing import List, Dict, Optional
from datetime import datetime, timezone

from . import config
from .utils import loading_indicator

class K8sViewer:
    def __init__(self, cache_ttl: Optional[int] = None, cache_enabled: bool = True):
        self.current_position = 0
        self.items: List[Dict] = []
        self.window_height = 0
        self.window_width = 0

        # Cache configuration
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl or config.CACHE_TTL
        self.cache_timestamps = {}  # Store timestamps for UI display
        self.current_context = self.get_current_context()

        if self.cache_enabled:
            # Set up cache directory and file
            self.cache_dir = os.path.expanduser(config.CACHE_DIR)
            self.cache_file = os.path.join(self.cache_dir, 'cluster_cache.json')
            os.makedirs(self.cache_dir, exist_ok=True)

            # Initialize cache
            self.cache = self.load_cache()
            logging.info(f"Initialized K8sViewer with persistent cache (TTL: {self.cache_ttl}s) for context '{self.current_context}'")
        else:
            self.cache = {}
            logging.info("Initialized K8sViewer with caching disabled")

    def get_current_context(self) -> str:
        """Get current kubectl context"""
        try:
            result = subprocess.run(
                ['kubectl', 'config', 'current-context'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to get current context: {e}")
            return 'default'

    def load_cache(self) -> Dict:
        """Load cache from disk if it exists, otherwise return empty cache structure"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                logging.info(f"Loaded cache from {self.cache_file}")
                # Ensure current context exists in cache
                if self.current_context not in cache_data:
                    cache_data[self.current_context] = {
                        'nodes': {},
                        'pods': {},
                    }
                return cache_data
        except Exception as e:
            logging.warning(f"Failed to load cache: {e}")

        return {
            self.current_context: {
                'nodes': {},  # {group_name: {'data': [...], 'timestamp': time.time()}}
                'pods': {},   # {node_name: {'data': [...], 'timestamp': time.time()}}
            }
        }

    def update_cache(self, cache_type: str, key: str, data: List[Dict]):
        """Update cache with new data and persist to disk"""
        if not self.cache_enabled:
            return

        # Ensure context and cache type exist
        if self.current_context not in self.cache:
            self.cache[self.current_context] = {}
        if cache_type not in self.cache[self.current_context]:
            self.cache[self.current_context][cache_type] = {}

        current_time = time.time()
        self.cache[self.current_context][cache_type][key] = {
            'data': data,
            'timestamp': current_time
        }

        # Update display timestamp
        display_key = f"{self.current_context}_{cache_type}_{key}"
        self.cache_timestamps[display_key] = self.format_timestamp(current_time)

        self.save_cache()

    def get_cached_data(self, cache_type: str, key: str):
        """Get data from cache if valid"""
        if not self.cache_enabled:
            return None

        # Check if context exists in cache
        if self.current_context not in self.cache:
            return None

        cache_entry = self.cache[self.current_context].get(cache_type, {}).get(key)
        if self.is_cache_valid(cache_entry):
            return cache_entry['data']
        return None

    def get_last_update_time(self, cache_type: str, key: str) -> str:
        """Get the last update time for display"""
        display_key = f"{self.current_context}_{cache_type}_{key}"
        return self.cache_timestamps.get(display_key, 'Never')

    def save_cache(self):
        """Save current cache to disk"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
            logging.info(f"Saved cache to {self.cache_file}")
        except Exception as e:
            logging.error(f"Failed to save cache: {e}")

    def is_cache_valid(self, cache_entry) -> bool:
        """Check if cache entry is still valid"""
        if not self.cache_enabled or not cache_entry or 'timestamp' not in cache_entry:
            return False
        return (time.time() - cache_entry['timestamp']) < self.cache_ttl

    def run_kubectl(self, command: str, json_output=True, show_labels=False) -> Dict:
        """Run kubectl command and return output"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
            if json_output:
                return json.loads(result.stdout)
            return result.stdout
        except subprocess.CalledProcessError as e:
            logging.error(f"Error running kubectl command: {str(e)}")
            raise

    def get_all_namespaces(self, stdscr) -> List[Dict]:
        """Get all namespaces"""
        with loading_indicator(stdscr, "Fetching namespaces..."):
            logging.info("Fetching namespaces")
            data = self.run_kubectl("kubectl get namespaces")
            return data.get('items', [])
