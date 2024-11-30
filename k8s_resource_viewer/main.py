import curses
import subprocess
import json
import logging
from typing import List, Dict, Optional
import os
import time
import threading
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import tempfile
import sys
import argparse

# Set up logging
class Config:
    LOG_DIR = os.getenv('K8S_VIEWER_LOG_DIR', '~/.k8s_viewer/logs')
    LOG_FILE = 'k8s_viewer.log'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

def setup_logging(log_level: str):
    """Configure logging with the specified level"""
    level_map = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR
    }
    level = level_map.get(log_level.lower(), logging.INFO)
    
    # Ensure log directory exists
    log_dir = os.path.expanduser(Config.LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    
    # Set up log file path
    log_file = os.path.join(log_dir, Config.LOG_FILE)
    
    logging.basicConfig(
        filename=log_file,
        level=level,
        format=Config.LOG_FORMAT
    )
    logging.info(f"Logging to: {log_file}")
    logging.info(f"Log level set to: {logging.getLevelName(level)}")

@contextmanager
def loading_indicator(stdscr, message):
    """Show a loading indicator while executing a long operation"""
    if not stdscr:
        yield
        return

    # Create and start the loading indicator thread
    class LoadingIndicator:
        def __init__(self):
            self.running = True

        def stop(self):
            self.running = False

        def run(self):
            spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            i = 0
            max_y, max_x = stdscr.getmaxyx()
            while self.running:
                try:
                    # Clear the line
                    stdscr.addstr(max_y-1, 0, ' ' * (max_x-1))
                    # Show spinner and message
                    status = f"{spinner[i]} {message}"
                    stdscr.addstr(max_y-1, 0, status[:max_x-1])
                    stdscr.refresh()
                    time.sleep(0.1)
                    i = (i + 1) % len(spinner)
                except:
                    break

    indicator = LoadingIndicator()
    indicator_thread = threading.Thread(target=indicator.run)
    indicator_thread.daemon = True
    indicator_thread.start()

    try:
        yield
    finally:
        indicator.stop()

class K8sViewer:
    def __init__(self, cache_ttl: Optional[int] = None, cache_enabled: bool = True):
        self.current_position = 0
        self.items: List[Dict] = []
        self.window_height = 0
        self.window_width = 0

        # Cache configuration
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl or int(os.getenv('K8S_VIEWER_CACHE_TTL', '30'))  # Cache TTL in seconds
        self.cache_timestamps = {}  # Store timestamps for UI display
        self.current_context = self.get_current_context()

        if self.cache_enabled:
            # Set up cache directory and file
            self.cache_dir = os.path.expanduser(os.getenv('K8S_VIEWER_CACHE_DIR', '~/.k8s_viewer'))
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
            return [{
                'name': ns['metadata']['name'],
                'status': ns['status']['phase']
            } for ns in data['items']]

    def get_deployments(self, namespace: str, stdscr) -> List[Dict]:
        """Get deployments in the specified namespace"""
        with loading_indicator(stdscr, f"Fetching deployments in {namespace}..."):
            logging.info(f"Fetching deployments in {namespace}")
            data = self.run_kubectl(f"kubectl get deployments -n {namespace}")
            return [{
                'name': dep['metadata']['name'],
                'ready': f"{dep['status'].get('readyReplicas', 0)}/{dep['spec']['replicas']}",
                'available': dep['status'].get('availableReplicas', 0)
            } for dep in data['items']]

    def get_karpenter_nodepools(self) -> List[str]:
        """Get Karpenter node pool names"""
        try:
            data = self.run_kubectl("kubectl get nodepools.karpenter.sh")
            if not data.get('items'):
                logging.warning("No Karpenter node pools found")
                return []

            pools = []
            for pool in data['items']:
                name = pool['metadata'].get('name')
                if name:
                    pools.append(name)
            logging.info(f"Found Karpenter pools: {pools}")
            return pools
        except Exception as e:
            logging.error(f"Error fetching Karpenter pools: {str(e)}")
            return []

    def get_node_groups(self, stdscr) -> List[Dict]:
        """Get unique node groups from node labels and Karpenter"""
        with loading_indicator(stdscr, "Fetching node groups..."):
            logging.info("Fetching node groups")
            # Update cache timestamp for node groups
            self.cache_timestamps['node_groups'] = self.get_timestamp()

            # Debug logging
            logging.debug("Starting node group fetch")

            # Fetch all data in parallel using threads
            results = {'nodes': None, 'metrics': None, 'karpenter': None}

            def fetch_nodes():
                try:
                    # Get nodes data with JSON output
                    cmd = "kubectl get nodes -o json"
                    results['nodes'] = self.run_kubectl(cmd)
                    logging.debug(f"Nodes fetch complete: {len(results['nodes'].get('items', []))} nodes found")
                except Exception as e:
                    logging.error(f"Error fetching nodes: {str(e)}")
                    results['nodes'] = {'items': []}

            def fetch_metrics():
                try:
                    results['metrics'] = self.get_node_metrics()
                    logging.debug(f"Metrics fetch complete: {len(results['metrics'])} node metrics found")
                except Exception as e:
                    logging.error(f"Error fetching metrics: {str(e)}")
                    results['metrics'] = {}

            def fetch_karpenter():
                try:
                    results['karpenter'] = self.get_karpenter_nodepools()
                    logging.debug(f"Karpenter fetch complete: {len(results['karpenter'])} pools found")
                except Exception as e:
                    logging.error(f"Error fetching Karpenter pools: {str(e)}")
                    results['karpenter'] = []

            # Start all fetches in parallel
            threads = [
                threading.Thread(target=fetch_nodes),
                threading.Thread(target=fetch_metrics),
                threading.Thread(target=fetch_karpenter)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            logging.debug("All fetches complete")

            node_groups = []
            all_nodes = results['nodes'].get('items', [])
            node_metrics = results['metrics']

            logging.debug(f"Processing {len(all_nodes)} nodes")

            # Process node groups...
            group_map = {}

            # Process nodes
            for node in all_nodes:
                labels = node['metadata'].get('labels', {})
                hostname = node['metadata'].get('name', '')
                metrics = node_metrics.get(hostname, {})

                # Get node capacity and allocatable resources
                capacity = node['status'].get('capacity', {})
                allocatable = node['status'].get('allocatable', {})

                # Parse CPU values
                cpu_capacity = self.parse_cpu_value(capacity.get('cpu', '0'))
                cpu_allocatable = self.parse_cpu_value(allocatable.get('cpu', '0'))
                cpu_used = metrics.get('cpu_used', 0)

                # Parse memory values (strip Ki suffix and convert to bytes)
                memory_capacity = int(capacity.get('memory', '0').rstrip('Ki')) * 1024
                memory_allocatable = int(allocatable.get('memory', '0').rstrip('Ki')) * 1024
                memory_used = metrics.get('memory_used', 0)

                # Check for EKS node groups
                eks_group = labels.get('eks.amazonaws.com/nodegroup')
                if eks_group:
                    group_name = f"eks:{eks_group}"
                else:
                    # Check for Karpenter node pools
                    karpenter_pool = labels.get('karpenter.sh/nodepool')
                    if karpenter_pool:
                        group_name = f"karpenter:{karpenter_pool}"
                    # Check for core services
                    elif labels.get('reserved') == 'core-services':
                        group_name = 'core-services'
                    else:
                        # Default worker nodes
                        group_name = 'worker'

                if group_name not in group_map:
                    group_map[group_name] = {
                        'nodes': [],
                        'total_cpu': 0,
                        'total_memory': 0,
                        'used_cpu': 0,
                        'used_memory': 0,
                        'allocatable_cpu': 0,
                        'allocatable_memory': 0
                    }

                # Add node to group
                group_map[group_name]['nodes'].append(node)
                group_map[group_name]['total_cpu'] += cpu_capacity
                group_map[group_name]['allocatable_cpu'] += cpu_allocatable
                group_map[group_name]['used_cpu'] += cpu_used
                group_map[group_name]['total_memory'] += memory_capacity
                group_map[group_name]['allocatable_memory'] += memory_allocatable
                group_map[group_name]['used_memory'] += memory_used

            logging.debug(f"Found {len(group_map)} node groups")

            # Convert group map to list
            for name, info in group_map.items():
                if not info['nodes']:  # Skip empty groups
                    continue

                # Get creation timestamp from node metadata
                timestamps = [node['metadata'].get('creationTimestamp', '')
                            for node in info['nodes']
                            if node.get('metadata', {}).get('creationTimestamp')]

                age = 'N/A'
                if timestamps:
                    oldest_timestamp = min(timestamps)
                    age = self.calculate_age(oldest_timestamp)
                    logging.debug(f"Group {name} oldest timestamp: {oldest_timestamp}, age: {age}")
                else:
                    logging.warning(f"No valid timestamps found for group {name}")

                node_groups.append({
                    'name': name,
                    'count': len(info['nodes']),
                    'age': age,
                    'total_cpu': self.format_resource(info['total_cpu']),
                    'used_cpu': self.format_resource(info['used_cpu']),
                    'total_memory': self.format_resource(info['total_memory'], True),
                    'used_memory': self.format_resource(info['used_memory'], True)
                })

            logging.debug(f"Returning {len(node_groups)} formatted node groups")
            return sorted(node_groups, key=lambda x: x['name'])

    def draw_title_bar(self, stdscr, title: str, instructions: str):
        """Draw a fancy title bar with box drawing characters"""
        max_y, max_x = stdscr.getmaxyx()

        # Use background color for title bar
        stdscr.attron(curses.A_REVERSE)
        stdscr.addstr(0, 0, " " * max_x)  # Fill entire first line

        # Center the title
        start_x = (max_x - len(title)) // 2
        stdscr.addstr(0, start_x, title)
        stdscr.attroff(curses.A_REVERSE)

        # Add instructions on second line
        stdscr.addstr(1, 2, instructions)

        # Add separator line
        stdscr.addstr(2, 0, "─" * max_x)

    def draw_menu(self, stdscr, title: str, items: List[Dict], fields: List[str]):
        """Draw menu with items"""
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        # Draw title and instructions
        self.draw_title_bar(
            stdscr,
            title,
            "(Use ↑↓ to navigate, Enter to select, 'q' to go back)"
        )

        # Safety check for empty items
        if not items:
            msg = "No items to display"
            stdscr.addstr(height//2, (width-len(msg))//2, msg)
            stdscr.refresh()
            return

        # Draw header
        if "count" in items[0]:  # Node group view
            # Calculate column widths
            name_width = max(30, max(len(str(item.get('name', ''))) for item in items) + 2)

            # Draw headers
            header = (
                f"{'NAME':<{name_width}} │ "
                f"{'NODES':>5} │ "
                f"{'AGE':>5} │ "
                f"{'CPU':>6} │ "
                f"{'MEMORY':>8}"
            )
            stdscr.addstr(2, 0, header, curses.A_BOLD)

            # Draw separator line
            separator = "─" * name_width + "┼" + "─" * 7 + "┼" + "─" * 7 + "┼" + "─" * 8 + "┼" + "─" * 10
            stdscr.addstr(3, 0, separator)

            # Draw items
            for idx, item in enumerate(items):
                if 4 + idx >= height:
                    break

                # Truncate name if too long
                name = str(item.get('name', ''))
                if len(name) > name_width - 2:
                    name = name[:name_width - 5] + "..."

                line = (
                    f"{name:<{name_width}} │ "
                    f"{item.get('count', 0):>5} │ "
                    f"{item.get('age', 'N/A'):>5} │ "
                    f"{item.get('cpu', '0'):>6} │ "
                    f"{item.get('memory', '0'):>8}"
                )

                if idx == self.current_position:
                    stdscr.addstr(4 + idx, 0, line, curses.A_REVERSE)
                else:
                    stdscr.addstr(4 + idx, 0, line)
        else:
            # Regular view
            field_width = max(15, (width - len(fields) - 1) // len(fields))
            header = " | ".join(f"{field.upper():<{field_width}}" for field in fields)
            stdscr.addstr(2, 0, header, curses.A_BOLD)

            # Draw items
            for idx, item in enumerate(items):
                if 2 + idx + 1 >= height:
                    break

                line = " | ".join(f"{str(item.get(field, '')):.<{field_width}}" for field in fields)

                if idx == self.current_position:
                    stdscr.addstr(2 + idx + 1, 0, line, curses.A_REVERSE)
                else:
                    stdscr.addstr(2 + idx + 1, 0, line)

        stdscr.refresh()

    def describe_node(self, node_name: str, stdscr) -> str:
        """Get detailed information about a node using kubectl describe"""
        with loading_indicator(stdscr, f"Getting details for node {node_name}"):
            try:
                return self.run_kubectl(f"kubectl describe node {node_name}", json_output=False)
            except Exception as e:
                logging.error(f"Error describing node {node_name}: {str(e)}")
                return f"Error getting node details: {str(e)}"

    def describe_pod(self, namespace: str, pod_name: str, stdscr) -> str:
        """Get detailed information about a pod using kubectl describe"""
        with loading_indicator(stdscr, f"Getting details for pod {pod_name}"):
            try:
                return self.run_kubectl(f"kubectl describe pod {pod_name} -n {namespace}", json_output=False)
            except Exception as e:
                logging.error(f"Error describing pod {pod_name}: {str(e)}")
                return f"Error getting pod details: {str(e)}"

    def show_scrollable_text(self, stdscr, title: str, text: str):
        """Display text in a scrollable view using less"""
        try:
            # Save the text to a temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write(text)
                temp_file = f.name

            # Use less to display the text
            curses.endwin()  # Temporarily exit curses mode
            subprocess.run(['less', '-R', temp_file])
            curses.doupdate()  # Redraw the screen

            # Clean up
            os.unlink(temp_file)
        except Exception as e:
            logging.error(f"Error showing scrollable text: {str(e)}")
            stdscr.addstr(0, 0, f"Error: {str(e)}")
            stdscr.refresh()
            stdscr.getch()

    def get_pod_metrics(self, node_name: str, stdscr = None) -> List[Dict]:
        """Get pod metrics with caching"""
        # Check cache first
        cached_pods = self.get_cached_data('pods', node_name)
        if cached_pods:
            return cached_pods

        # If not in cache, fetch with loading indicator
        with loading_indicator(stdscr, f"Getting pods for node {node_name}..."):
            try:
                # Get pods with their basic info
                pods_data = self.run_kubectl(f"kubectl get pods --all-namespaces --field-selector=spec.nodeName={node_name} -o json")
                if not pods_data:
                    return []

                # Update cache timestamp for this node's pods
                self.cache_timestamps[f'pods_{node_name}'] = self.get_timestamp()

                # Get pod metrics
                try:
                    metrics_result = subprocess.run(
                        ["kubectl", "top", "pods", "--all-namespaces"],
                        capture_output=True,
                        text=True,
                        check=True
                    )

                    # Parse metrics into a map for quick lookup
                    metrics_map = {}
                    lines = metrics_result.stdout.strip().split('\n')
                    if len(lines) > 1:  # Skip header
                        for line in lines[1:]:
                            parts = line.split()
                            if len(parts) >= 4:  # namespace, pod, cpu, memory
                                namespace = parts[0]
                                pod_name = parts[1]
                                key = f"{namespace}/{pod_name}"

                                # Parse CPU (convert millicores to cores)
                                cpu = parts[2]
                                if cpu.endswith('m'):
                                    cpu_value = float(cpu[:-1]) / 1000
                                else:
                                    cpu_value = float(cpu)

                                # Parse memory
                                memory = parts[3]
                                value = float(memory[:-2])
                                unit = memory[-2:].lower()

                                if unit == 'ki':
                                    memory_value = value * 1024
                                elif unit == 'mi':
                                    memory_value = value * 1024 * 1024
                                elif unit == 'gi':
                                    memory_value = value * 1024 * 1024 * 1024
                                else:
                                    memory_value = value

                                metrics_map[key] = {
                                    'cpu': self.format_resource(cpu_value),
                                    'memory': self.format_resource(memory_value, True)
                                }
                except Exception as e:
                    logging.error(f"Error getting pod metrics: {str(e)}")
                    metrics_map = {}

                # Combine pod info with metrics
                pods = []
                for pod in pods_data['items']:
                    namespace = pod['metadata']['namespace']
                    name = pod['metadata']['name']
                    key = f"{namespace}/{name}"
                    metrics = metrics_map.get(key, {'cpu': '0', 'memory': '0'})

                    pods.append({
                        'namespace': namespace,
                        'name': name,
                        'status': pod['status']['phase'],
                        'age': self.calculate_age(pod['metadata'].get('creationTimestamp', '')),
                        'cpu': metrics['cpu'],
                        'memory': metrics['memory']
                    })

                self.update_cache('pods', node_name, pods)
                return pods
            except Exception as e:
                logging.error(f"Error getting pods for node {node_name}: {str(e)}")
                return []

    def display_pods(self, stdscr, node_name: str, pods: List[Dict]):
        """Display pods in a scrollable view"""
        self.current_position = 0  # Reset position for pod view
        max_y, max_x = stdscr.getmaxyx()
        current_pos = 0

        while True:
            stdscr.erase()  # Use erase instead of clear for less flicker

            # Draw title with better instructions
            self.draw_title_bar(
                stdscr,
                f"Pods on node: {node_name}",
                "(↑↓ to scroll, Enter/d to describe pod, 'r' to refresh, 'q' to go back)"
            )

            # Calculate content area
            content_y = 3
            content_height = max_y - content_y - 1
            visible_pods = pods[current_pos:current_pos + content_height]

            # Calculate max lengths for formatting
            max_namespace = max(len(pod.get('namespace', '')) for pod in pods)
            max_name = max(len(pod.get('name', '')) for pod in pods)

            # Draw header with better formatting
            header = (
                f"{'NAMESPACE':<{max_namespace + 2}} │ "
                f"{'NAME':<{max_name + 2}} │ "
                f"{'STATUS':<12} │ "
                f"{'AGE':<8} │ "
                f"{'CPU':<10} │ "
                f"{'MEMORY':<12}"
            )
            stdscr.addstr(content_y - 1, 2, header, curses.A_BOLD)
            stdscr.addstr(content_y, 2, "─" * (max_x-4))

            # Draw pods
            for idx, pod in enumerate(visible_pods):
                y = content_y + 1 + idx
                if y >= max_y - 1:
                    break

                # Add color based on status
                status = pod.get('status', '')
                status_attr = curses.A_NORMAL
                if status == 'Running':
                    status_str = f"{status:12}"
                elif status == 'Pending':
                    status_str = f"{status:12}"
                elif status == 'Failed':
                    status_str = f"{status:12}"
                else:
                    status_str = f"{status:12}"

                line = (
                    f"{pod.get('namespace', ''):<{max_namespace + 2}} │ "
                    f"{pod.get('name', ''):<{max_name + 2}} │ "
                    f"{status_str} │ "
                    f"{pod.get('age', ''):<8} │ "
                    f"{pod.get('cpu', ''):<10} │ "
                    f"{pod.get('memory', ''):<12}"
                )

                if idx == self.current_position - current_pos:
                    stdscr.attron(curses.A_REVERSE)
                    stdscr.addstr(y, 2, line[:max_x-4])
                    stdscr.attroff(curses.A_REVERSE)
                else:
                    stdscr.addstr(y, 2, line[:max_x-4])

            # Draw scrollbar if needed
            if len(pods) > content_height:
                scrollbar_pos = int((current_pos / len(pods)) * content_height)
                scrollbar_height = max(1, int((content_height / len(pods)) * content_height))
                for i in range(content_height):
                    if i >= scrollbar_pos and i < scrollbar_pos + scrollbar_height:
                        stdscr.addstr(content_y + 1 + i, max_x - 2, "█")
                    else:
                        stdscr.addstr(content_y + 1 + i, max_x - 2, "│")

            # Draw summary at the bottom
            timestamp = self.cache_timestamps.get(f'pods_{node_name}', 'Never')
            summary = f"Total pods: {len(pods)} | Last updated: {timestamp}"
            stdscr.addstr(max_y-1, 2, summary)

            # Stage all changes before refreshing
            stdscr.noutrefresh()
            curses.doupdate()  # Update screen once

            # Handle input
            key = stdscr.getch()

            if key == ord('q'):
                break
            elif key == curses.KEY_UP:
                if self.current_position > 0:
                    self.current_position -= 1
                    if self.current_position < current_pos:
                        current_pos = self.current_position
            elif key == curses.KEY_DOWN:
                if self.current_position < len(pods) - 1:
                    self.current_position += 1
                    if self.current_position >= current_pos + content_height:
                        current_pos = self.current_position - content_height + 1
            elif key in [ord('\n'), ord('d')]:
                # Show pod description
                current_pod = pods[self.current_position]
                details = self.describe_pod(current_pod['namespace'], current_pod['name'], stdscr)
                self.show_scrollable_text(stdscr, f"Pod Description: {current_pod['name']}", details)
            elif key == ord('r'):
                # Refresh pod list
                with loading_indicator(stdscr, f"Refreshing pods for {node_name}..."):
                    new_pods = self.get_pod_metrics(node_name, stdscr)
                if new_pods:
                    pods = new_pods
                    self.current_position = min(self.current_position, len(pods) - 1)
                    current_pos = min(current_pos, len(pods) - content_height)

    def parse_cpu_value(self, cpu_str: str) -> float:
        """Parse CPU value, handling millicores (e.g., '100m') and unknown values"""
        try:
            if isinstance(cpu_str, (int, float)):
                return float(cpu_str)
            # Convert to string and handle '<unknown>' case
            cpu_str = str(cpu_str)
            logging.info(f"Parsed CPU value: {cpu_str}")
            if cpu_str == '<unknown>':
                return 0.0
            if cpu_str.endswith('m'):
                return float(cpu_str[:-1]) / 1000
            return float(cpu_str)
        except (ValueError, AttributeError) as e:
            logging.error(f"Error parsing CPU value '{cpu_str}': {str(e)}")
            return 0.0

    def get_nodes(self, group_name: str, stdscr = None) -> List[Dict]:
        """Get nodes in a specific group"""
        try:
            # Check cache first
            cached_nodes = self.get_cached_data('nodes', group_name)
            if cached_nodes:
                return cached_nodes

            with loading_indicator(stdscr, f"Getting nodes for {group_name}..."):
                # Update cache timestamp for this group's nodes
                self.cache_timestamps[f'nodes_{group_name}'] = self.get_timestamp()

                # Get nodes
                nodes_result = self.run_kubectl("kubectl get nodes -o json")
                logging.debug(f"Got {len(nodes_result.get('items', []))} nodes from kubectl")

                # Get metrics
                metrics = self.get_node_metrics()
                logging.debug(f"Got metrics: {metrics}")

                # Process nodes
                nodes = []
                for node in nodes_result.get('items', []):
                    name = node['metadata'].get('name', '')
                    labels = node['metadata'].get('labels', {})
                    logging.debug(f"Processing node {name} with labels: {labels}")

                    # Check if node belongs to this group
                    if (
                        (group_name.startswith('eks:') and labels.get('eks.amazonaws.com/nodegroup') == group_name[4:]) or
                        (group_name.startswith('karpenter:') and labels.get('karpenter.sh/nodepool') == group_name[10:]) or
                        (group_name == 'core-services' and labels.get('reserved') == 'core-services') or
                        (group_name == 'worker' and
                         not labels.get('eks.amazonaws.com/nodegroup') and
                         not labels.get('karpenter.sh/nodepool') and
                         labels.get('reserved') != 'core-services')
                    ):
                        # Get node metrics
                        node_metrics = metrics.get(name, {})
                        logging.debug(f"Node {name} metrics: {node_metrics}")

                        # Log node status
                        logging.debug(f"Node {name} status:")
                        logging.debug(f"  - status object: {node['status']}")
                        logging.debug(f"  - allocatable: {node['status'].get('allocatable', {})}")
                        logging.debug(f"  - capacity: {node['status'].get('capacity', {})}")

                        try:
                            # Parse CPU values with more detailed logging
                            allocatable_cpu = node['status'].get('allocatable', {}).get('cpu', '0')
                            capacity_cpu = node['status'].get('capacity', {}).get('cpu', '0')
                            logging.debug(f"Raw CPU values for node {name}:")
                            logging.debug(f"  - allocatable_cpu: {allocatable_cpu} (type: {type(allocatable_cpu)})")
                            logging.debug(f"  - capacity_cpu: {capacity_cpu} (type: {type(capacity_cpu)})")
                            logging.debug(f"  - used_cpu: {node_metrics.get('cpu_used', 0)} (type: {type(node_metrics.get('cpu_used', 0))})")

                            cpu_alloc = self.parse_cpu_value(allocatable_cpu)
                            cpu_total = self.parse_cpu_value(capacity_cpu)
                            cpu_used = node_metrics.get('cpu_used', 0)

                            # Log parsed values
                            logging.debug(f"Node {name} parsed CPU values:")
                            logging.debug(f"  - allocatable: {cpu_alloc}")
                            logging.debug(f"  - capacity: {cpu_total}")
                            logging.debug(f"  - used: {cpu_used}")

                            # Add node to list with group name
                            node_data = {
                                'name': name,
                                'status': self.get_node_status(node),
                                'age': self.calculate_age(node['metadata'].get('creationTimestamp', '')),
                                'instance_type': labels.get('node.kubernetes.io/instance-type', 'Unknown'),
                                'cpu_alloc': self.format_resource(cpu_alloc),
                                'cpu_total': self.format_resource(cpu_total),
                                'cpu_used': self.format_resource(cpu_used),
                                'memory_alloc': self.format_resource(int(node['status']['allocatable'].get('memory', '0').rstrip('Ki')) * 1024, True),
                                'memory_total': self.format_resource(int(node['status']['capacity'].get('memory', '0').rstrip('Ki')) * 1024, True),
                                'memory_used': self.format_resource(node_metrics.get('memory_used', 0), True),
                                'group_name': group_name
                            }
                            nodes.append(node_data)
                            logging.debug(f"Added node {name} to list with data: {node_data}")
                        except Exception as e:
                            logging.error(f"Error processing CPU values for node {name}: {str(e)}")
                            continue

                # Update cache
                self.update_cache('nodes', group_name, nodes)
                logging.debug(f"Returning {len(nodes)} nodes for group {group_name}")
                return nodes

        except Exception as e:
            logging.error(f"Error getting nodes in group {group_name}: {str(e)}")
            return []

    def display_nodes(self, stdscr, nodes: List[Dict]):
        """Display nodes in a scrollable view"""
        self.current_position = 0
        max_y, max_x = stdscr.getmaxyx()
        current_pos = 0
        group_name = nodes[0]['group_name'] if nodes else 'unknown'

        while True:
            if nodes:  # Only try to display if we have nodes
                stdscr.erase()  # Use erase instead of clear for less flicker

                # Draw title with better instructions
                self.draw_title_bar(
                    stdscr,
                    "Node Details",
                    "(↑↓ to scroll, Enter to view pods, 'd' for node description, 'r' to refresh, 'q' to go back)"
                )

                # Calculate content area
                content_y = 3
                content_height = max_y - content_y - 1
                visible_nodes = nodes[current_pos:current_pos + content_height]

                # Draw headers with better formatting
                headers = ["NAME", "STATUS", "AGE", "INSTANCE TYPE",
                    "CPU (Used/Alloc)", "MEMORY (Used/Alloc)", "PODS"]
                header_str = " │ ".join(f"{h:<15}" for h in headers)
                stdscr.addstr(content_y - 1, 2, header_str[:max_x-1], curses.A_BOLD)

                # Draw separator line
                separator = "─" * 15 + "┼" + "─" * 15 + "┼" + "─" * 15 + "┼" + "─" * 15 + "┼" + "─" * 15 + "┼" + "─" * 15 + "┼" + "─" * 10
                stdscr.addstr(content_y, 2, separator)

                # Draw nodes
                for idx, node in enumerate(visible_nodes):
                    y = content_y + 1 + idx
                    if y >= max_y - 1:
                        break

                    # Format node info
                    node_str = (
                        f"{node['name'][:15]:<15} │ "
                        f"{node['status'][:15]:<15} │ "
                        f"{node['age'][:15]:<15} │ "
                        f"{node['instance_type'][:15]:<15} │ "
                        f"{node['cpu_used']}/{node['cpu_alloc']:<15} │ "
                        f"{node['memory_used']}/{node['memory_alloc']:<15} │ "
                        f"{len(self.get_pod_metrics(node['name']) or [])} pods"
                    )

                    if idx == self.current_position - current_pos:
                        stdscr.attron(curses.A_REVERSE)
                        stdscr.addstr(y, 2, node_str[:max_x-4])
                        stdscr.attroff(curses.A_REVERSE)
                    else:
                        stdscr.addstr(y, 2, node_str[:max_x-4])

                # Draw summary at the bottom
                timestamp = self.cache_timestamps.get(f'nodes_{group_name}', 'Never')
                summary = f"Total nodes: {len(nodes)} | Last updated: {timestamp}"
                stdscr.addstr(max_y-1, 2, summary)

            else:
                # Display message when no nodes
                stdscr.clear()
                msg = "No nodes found in this group"
                stdscr.addstr(max_y//2, (max_x-len(msg))//2, msg)

            # Stage all changes before refreshing
            stdscr.noutrefresh()
            curses.doupdate()  # Update screen once

            # Handle input
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('r'):
                # Refresh nodes
                with loading_indicator(stdscr, "Refreshing nodes..."):
                    new_nodes = self.get_nodes(group_name, stdscr)
                if new_nodes:
                    nodes = new_nodes
                    self.current_position = min(self.current_position, len(nodes) - 1)
                    current_pos = min(current_pos, len(nodes) - content_height)
            elif key == curses.KEY_UP and self.current_position > 0:
                self.current_position -= 1
                if self.current_position < current_pos:
                    current_pos = self.current_position
            elif key == curses.KEY_DOWN and nodes and self.current_position < len(nodes) - 1:
                self.current_position += 1
                if self.current_position >= current_pos + content_height:
                    current_pos = self.current_position - content_height + 1
            elif key == ord('d') and nodes:
                selected_node = nodes[self.current_position]
                description = self.describe_node(selected_node['name'], stdscr)
                self.show_scrollable_text(stdscr, f"Node Description: {selected_node['name']}", description)
            elif key == 10 and nodes:  # Enter key
                selected_node = nodes[self.current_position]
                pods = self.get_pod_metrics(selected_node['name'], stdscr)
                if pods:
                    self.display_pods(stdscr, selected_node['name'], pods)

        # Reset screen after returning from node view
        stdscr.clear()
        stdscr.refresh()

    def get_node_status(self, node):
        """Get node status from node object"""
        conditions = node['status'].get('conditions', [])
        status = 'Unknown'
        for condition in conditions:
            if condition.get('type') == 'Ready':
                status = 'Ready' if condition.get('status') == 'True' else 'NotReady'
                break
        return status

    def calculate_age(self, timestamp: str) -> str:
        """Calculate age from timestamp"""
        if not timestamp:
            return "N/A"

        try:
            # Parse the timestamp
            created_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age = now - created_time

            # Convert to appropriate unit
            total_seconds = age.total_seconds()
            if total_seconds < 3600:  # Less than 1 hour
                return f"{int(total_seconds / 60)}m"
            elif total_seconds < 86400:  # Less than 1 day
                return f"{int(total_seconds / 3600)}h"
            else:
                return f"{int(total_seconds / 86400)}d"
        except Exception as e:
            logging.error(f"Error calculating age: {str(e)}")
            return "N/A"

    def format_resource(self, value: float, is_memory: bool = False) -> str:
        """Format resource value (CPU cores or memory bytes) to human readable format"""
        try:
            if is_memory:
                # Convert memory from bytes to appropriate unit
                units = ['B', 'Ki', 'Mi', 'Gi', 'Ti']
                unit_index = 0
                while value >= 1024 and unit_index < len(units) - 1:
                    value /= 1024
                    unit_index += 1
                return f"{value:.1f}{units[unit_index]}"
            else:
                # Format CPU cores
                if value < 1:
                    return f"{int(value * 1000)}m"
                return f"{value:.1f}"
        except Exception as e:
            logging.error(f"Error formatting resource: {str(e)}")
            return "N/A"

    def get_node_metrics(self) -> Dict[str, Dict]:
        """Get node metrics from metrics API"""
        try:
            metrics_result = self.run_kubectl("kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes")
            logging.debug(f"Raw metrics result: {metrics_result}")

            metrics = {}
            for item in metrics_result.get('items', []):
                name = item['metadata']['name']
                usage = item.get('usage', {})

                # Handle CPU value
                cpu_value = usage.get('cpu', '0')
                try:
                    if isinstance(cpu_value, str):
                        if cpu_value.endswith('n'):
                            cpu_used = float(cpu_value[:-1]) / 1000000000
                        elif cpu_value.endswith('u'):
                            cpu_used = float(cpu_value[:-1]) / 1000000
                        elif cpu_value.endswith('m'):
                            cpu_used = float(cpu_value[:-1]) / 1000
                        elif cpu_value == '<unknown>':
                            cpu_used = 0.0
                        else:
                            cpu_used = float(cpu_value)
                    else:
                        cpu_used = float(cpu_value)
                except (ValueError, AttributeError) as e:
                    logging.warning(f"Could not parse CPU value '{cpu_value}' for node {name}: {str(e)}")
                    cpu_used = 0.0

                # Handle memory value
                memory_value = usage.get('memory', '0')
                try:
                    if isinstance(memory_value, str):
                        if memory_value.endswith('Ki'):
                            memory_used = int(memory_value[:-2]) * 1024
                        elif memory_value.endswith('Mi'):
                            memory_used = int(memory_value[:-2]) * 1024 * 1024
                        elif memory_value.endswith('Gi'):
                            memory_used = int(memory_value[:-2]) * 1024 * 1024 * 1024
                        elif memory_value == '<unknown>':
                            memory_used = 0
                        else:
                            memory_used = int(memory_value)
                    else:
                        memory_used = int(memory_value)
                except (ValueError, TypeError) as e:
                    logging.warning(f"Could not parse memory value '{memory_value}' for node {name}: {str(e)}")
                    memory_used = 0

                metrics[name] = {
                    'cpu_used': cpu_used,
                    'memory_used': memory_used
                }

            logging.debug(f"Processed metrics for {len(metrics)} nodes: {metrics}")
            return metrics
        except Exception as e:
            logging.error(f"Error fetching metrics: {str(e)}")
            return {}

    def get_timestamp(self):
        """Get current timestamp in a consistent format"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def format_timestamp(self, timestamp: float) -> str:
        """Format a timestamp for display"""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    def get_available_contexts(self, stdscr=None) -> List[Dict[str, str]]:
        """Get list of available kubernetes contexts"""
        try:
            with loading_indicator(stdscr, "Getting available contexts...") if stdscr else nullcontext():
                result = subprocess.run(['kubectl', 'config', 'get-contexts', '-o=name'], 
                                     capture_output=True, text=True, check=True)
                contexts = result.stdout.strip().split('\n')
                
                # Get current context
                current = subprocess.run(['kubectl', 'config', 'current-context'], 
                                      capture_output=True, text=True, check=True).stdout.strip()
                
                return [{'name': ctx.strip(), 'current': ctx.strip() == current} for ctx in contexts]
        except subprocess.CalledProcessError as e:
            logging.error(f"Error getting contexts: {e}")
            return []

    def switch_context(self, context_name: str, stdscr=None) -> bool:
        """Switch to a different kubernetes context"""
        try:
            with loading_indicator(stdscr, f"Switching to context {context_name}...") if stdscr else nullcontext():
                subprocess.run(['kubectl', 'config', 'use-context', context_name], 
                             capture_output=True, text=True, check=True)
                return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Error switching context: {e}")
            return False

    def display_context_menu(self, stdscr):
        """Display context selection menu"""
        contexts = self.get_available_contexts(stdscr)
        if not contexts:
            return

        current_pos = 0
        max_pos = len(contexts) - 1

        while True:
            try:
                stdscr.clear()
                height, width = stdscr.getmaxyx()

                # Display header
                header = "Kubernetes Context Selection"
                help_text = "Press 'q' to return, Enter to select context, arrow keys/j/k to navigate"
                stdscr.addstr(0, 0, header)
                stdscr.addstr(1, 0, help_text)
                stdscr.addstr(2, 0, "=" * min(len(help_text), width - 1))

                # Display contexts
                for i, ctx in enumerate(contexts, start=4):
                    if i >= height - 1:
                        break

                    prefix = "* " if ctx['current'] else "  "
                    line = f"{prefix}{ctx['name']}"

                    if i - 4 == current_pos:
                        stdscr.attron(curses.A_REVERSE)
                        stdscr.addstr(i, 0, line[:width-1])
                        stdscr.attroff(curses.A_REVERSE)
                    else:
                        stdscr.addstr(i, 0, line[:width-1])

                # Stage all changes before refreshing
                stdscr.noutrefresh()
                curses.doupdate()  # Update screen once

                # Handle keyboard input
                key = stdscr.getch()
                if key == -1:  # No input available
                    continue

                if key in [ord('q'), ord('Q')]:
                    break
                elif key in [curses.KEY_UP, ord('k')]:
                    current_pos = max(0, current_pos - 1)
                elif key in [curses.KEY_DOWN, ord('j')]:
                    current_pos = min(max_pos, current_pos + 1)
                elif key in [curses.KEY_ENTER, ord('\n'), ord('\r')]:
                    selected_context = contexts[current_pos]
                    if not selected_context['current']:
                        if self.switch_context(selected_context['name'], stdscr):
                            # Refresh contexts list after switching
                            contexts = self.get_available_contexts(stdscr)
                            max_pos = len(contexts) - 1

            except curses.error:
                stdscr.clear()
                stdscr.refresh()

    def display_main_menu(self, stdscr):
        """Display main menu"""
        # Get initial node groups
        node_groups = self.get_node_groups(stdscr)
        current_pos = 0
        max_pos = len(node_groups) - 1 if node_groups else 0

        while True:
            try:
                stdscr.clear()
                height, width = stdscr.getmaxyx()

                # Get current context
                try:
                    current_context = subprocess.run(['kubectl', 'config', 'current-context'], 
                                                   capture_output=True, text=True, check=True).stdout.strip()
                except subprocess.CalledProcessError:
                    current_context = "Unknown"

                # Display header with current context
                header = "Kubernetes Resource Viewer"
                context_info = f"Current Context: {current_context}"
                help_text = "Press 'q' to quit, 's' to search pods, 'c' to change context, 'r' to refresh"
                
                stdscr.addstr(0, 0, header)
                stdscr.addstr(1, 0, context_info)
                stdscr.addstr(2, 0, help_text)
                stdscr.addstr(3, 0, "=" * min(len(help_text), width - 1))

                if not node_groups:
                    stdscr.addstr(5, 0, "No node groups found")
                    stdscr.refresh()
                    key = stdscr.getch()
                    if key in [ord('q'), ord('Q')]:
                        break
                    elif key in [ord('s'), ord('S')]:
                        self.handle_pod_search(stdscr)
                    elif key in [ord('c'), ord('C')]:
                        self.display_context_menu(stdscr)
                        # Refresh node groups after context switch
                        node_groups = self.get_node_groups(stdscr)
                        max_pos = len(node_groups) - 1 if node_groups else 0
                        current_pos = 0
                    elif key in [ord('r'), ord('R')]:
                        node_groups = self.get_node_groups(stdscr)
                        max_pos = len(node_groups) - 1 if node_groups else 0
                        current_pos = 0
                    continue

                # Column headers
                headers = ["Group Name", "Nodes", "CPU (Used/Total)", "Memory (Used/Total)", "Age"]
                header_line = "{:<40} {:<8} {:<20} {:<20} {:<8}".format(*headers)
                stdscr.addstr(5, 0, header_line[:width-1])

                # Display node groups
                display_start = max(0, current_pos - height + 9)
                for i, group in enumerate(node_groups[display_start:], start=6):
                    if i >= height - 1:
                        break

                    line = "{:<40} {:<8} {:<20} {:<20} {:<8}".format(
                        group['name'][:40],
                        str(group['count']),
                        f"{group['used_cpu']}/{group['total_cpu']}",
                        f"{group['used_memory']}/{group['total_memory']}",
                        group['age']
                    )

                    if display_start + (i - 6) == current_pos:
                        stdscr.attron(curses.A_REVERSE)
                        stdscr.addstr(i, 0, line[:width-1])
                        stdscr.attroff(curses.A_REVERSE)
                    else:
                        stdscr.addstr(i, 0, line[:width-1])

                # Stage all changes before refreshing
                stdscr.noutrefresh()
                curses.doupdate()  # Update screen once

                # Handle keyboard input
                key = stdscr.getch()
                if key == -1:  # No input available
                    continue

                if key in [ord('q'), ord('Q')]:
                    break
                elif key in [curses.KEY_UP, ord('k')]:
                    current_pos = max(0, current_pos - 1)
                elif key in [curses.KEY_DOWN, ord('j')]:
                    current_pos = min(max_pos, current_pos + 1)
                elif key in [curses.KEY_ENTER, ord('\n'), ord('\r')]:
                    if node_groups:
                        selected_group = node_groups[current_pos]
                        nodes = self.get_nodes(selected_group['name'], stdscr)
                        if nodes:
                            self.display_nodes(stdscr, nodes)
                elif key in [ord('s'), ord('S')]:
                    self.handle_pod_search(stdscr)
                elif key in [ord('c'), ord('C')]:
                    self.display_context_menu(stdscr)
                    # Refresh node groups after context switch
                    node_groups = self.get_node_groups(stdscr)
                    max_pos = len(node_groups) - 1 if node_groups else 0
                    current_pos = min(current_pos, max_pos)
                elif key in [ord('r'), ord('R')]:
                    node_groups = self.get_node_groups(stdscr)
                    max_pos = len(node_groups) - 1 if node_groups else 0
                    current_pos = min(current_pos, max_pos)

            except curses.error:
                stdscr.clear()
                stdscr.refresh()

    def run(self, stdscr):
        """Main application loop"""
        # Configure curses
        curses.curs_set(0)  # Hide cursor
        curses.start_color()
        curses.use_default_colors()  # Use terminal's default colors
        curses.init_pair(1, curses.COLOR_WHITE, -1)  # -1 means default background
        stdscr.bkgd(' ', curses.color_pair(1))

        # Enable double buffering to reduce flicker
        stdscr.immedok(False)  # Disable immediate refresh
        stdscr.timeout(100)  # Increase timeout to 100ms to reduce CPU usage

        try:
            # Display main menu
            self.display_main_menu(stdscr)

        except KeyboardInterrupt:
            pass
        except Exception as e:
            logging.error(f"Error in main loop: {str(e)}")
            stdscr.clear()
            error_msg = f"Error: {str(e)}"
            height, width = stdscr.getmaxyx()
            stdscr.addstr(height//2, (width-len(error_msg))//2, error_msg)
            stdscr.noutrefresh()  # Stage changes
            curses.doupdate()  # Update screen once
            time.sleep(2)
        finally:
            # Reset terminal state
            stdscr.immedok(True)  # Reset immediate mode
            stdscr.timeout(-1)  # Reset to blocking mode

    def handle_pod_search(self, stdscr):
        """Handle pod search functionality"""
        # Save current state
        curses.echo()  # Show input
        curses.curs_set(1)  # Show cursor
        stdscr.nodelay(0)  # Make input blocking

        try:
            # Get search pattern from user
            height, width = stdscr.getmaxyx()
            prompt = "Enter pod name pattern: "
            stdscr.addstr(height-1, 0, prompt)
            stdscr.refresh()

            # Create a window for input
            input_win = curses.newwin(1, width - len(prompt), height-1, len(prompt))
            input_win.refresh()

            # Get input
            pattern = input_win.getstr().decode('utf-8').strip()

            if pattern:  # Only search if pattern is not empty
                # Search and display pods
                matching_pods = self.search_pods(pattern, stdscr)
                self.display_pod_search(stdscr, matching_pods)
        finally:
            # Restore curses state
            curses.noecho()
            curses.curs_set(0)
            stdscr.nodelay(1)  # Restore non-blocking mode

    def search_pods(self, pattern: str, stdscr = None) -> List[Dict]:
        """Search for pods by name pattern across all namespaces"""
        try:
            with loading_indicator(stdscr, f"Searching for pods matching '{pattern}'..."):
                # Get all pods
                pods_result = self.run_kubectl("kubectl get pods -A -o json")
                logging.debug(f"Got {len(pods_result.get('items', []))} pods from kubectl")

                # Get pod metrics
                pod_metrics = {}
                try:
                    metrics_result = self.run_kubectl("kubectl get --raw /apis/metrics.k8s.io/v1beta1/pods")
                    for item in metrics_result.get('items', []):
                        key = f"{item['metadata']['namespace']}/{item['metadata']['name']}"
                        usage = item.get('usage', {})
                        pod_metrics[key] = {
                            'cpu': usage.get('cpu', '<unknown>'),
                            'memory': usage.get('memory', '<unknown>')
                        }
                except Exception as e:
                    logging.error(f"Error fetching pod metrics: {str(e)}")

                # Filter and process pods
                matching_pods = []
                pattern = pattern.lower()
                for pod in pods_result.get('items', []):
                    name = pod['metadata'].get('name', '')
                    namespace = pod['metadata'].get('namespace', '')

                    if pattern in name.lower() or pattern in namespace.lower():
                        pod_data = {
                            'name': name,
                            'namespace': namespace,
                            'node': pod['spec'].get('nodeName', 'Unassigned'),
                            'status': pod['status'].get('phase', 'Unknown'),
                            'age': self.calculate_age(pod['metadata'].get('creationTimestamp', '')),
                            'cpu': pod_metrics.get(f"{namespace}/{name}", {}).get('cpu', '0'),
                            'memory': pod_metrics.get(f"{namespace}/{name}", {}).get('memory', '0'),
                            'raw_data': pod  # Store raw data for describe view
                        }
                        matching_pods.append(pod_data)

                logging.debug(f"Found {len(matching_pods)} pods matching pattern '{pattern}'")
                return matching_pods

        except Exception as e:
            logging.error(f"Error searching pods: {str(e)}")
            return []

    def display_pod_search(self, stdscr, pods: List[Dict]):
        """Display pod search results with describe capability"""
        current_pos = 0
        max_pos = len(pods) - 1 if pods else 0

        while True:
            try:
                stdscr.clear()
                height, width = stdscr.getmaxyx()

                # Display header
                header = "Pod Search Results"
                help_text = "Press 'q' to return, Enter/d to describe pod, 'n' to view node, arrow keys/j/k to navigate"
                stdscr.addstr(0, 0, header)
                stdscr.addstr(1, 0, help_text)
                stdscr.addstr(2, 0, "=" * min(len(help_text), width - 1))

                if not pods:
                    stdscr.addstr(4, 0, "No pods found matching the search pattern")
                    stdscr.refresh()
                    key = stdscr.getch()
                    if key in [ord('q'), ord('Q')]:
                        break
                    continue

                # Column headers
                headers = ["Namespace", "Name", "Node", "Status", "Age"]
                header_line = "{:<20} {:<40} {:<30} {:<10} {:<8}".format(*headers)
                stdscr.addstr(4, 0, header_line[:width-1])

                # Display pods
                display_start = max(0, current_pos - height + 8)
                for i, pod in enumerate(pods[display_start:], start=5):
                    if i >= height - 1:
                        break

                    line = "{:<20} {:<40} {:<30} {:<10} {:<8}".format(
                        pod['namespace'][:20],
                        pod['name'][:40],
                        pod['node'][:30],
                        pod['status'][:10],
                        pod['age'][:8]
                    )

                    if display_start + (i - 5) == current_pos:
                        stdscr.attron(curses.A_REVERSE)
                        stdscr.addstr(i, 0, line[:width-1])
                        stdscr.attroff(curses.A_REVERSE)
                    else:
                        stdscr.addstr(i, 0, line[:width-1])

                # Stage all changes before refreshing
                stdscr.noutrefresh()
                curses.doupdate()  # Update screen once

                # Handle keyboard input
                key = stdscr.getch()
                if key == -1:  # No input available
                    continue

                if key in [ord('q'), ord('Q')]:
                    break
                elif key in [curses.KEY_UP, ord('k')]:
                    current_pos = max(0, current_pos - 1)
                elif key in [curses.KEY_DOWN, ord('j')]:
                    current_pos = min(max_pos, current_pos + 1)
                elif key in [curses.KEY_ENTER, ord('\n'), ord('\r'), ord('d'), ord('D')]:
                    if pods:
                        selected_pod = pods[current_pos]
                        # Get pod description
                        pod_desc = self.describe_pod(selected_pod['namespace'], selected_pod['name'], stdscr)
                        # Show in less
                        if pod_desc:
                            # Save terminal state
                            curses.def_prog_mode()
                            curses.endwin()

                            # Save to temp file and show in less
                            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
                                tmp.write(pod_desc)
                                tmp_path = tmp.name

                            try:
                                subprocess.run(['less', '-R', tmp_path])
                            finally:
                                os.unlink(tmp_path)

                            # Restore terminal state
                            curses.reset_prog_mode()
                            stdscr.clear()
                            stdscr.refresh()

                elif key in [ord('n'), ord('N')]:
                    if pods:
                        selected_pod = pods[current_pos]
                        node_name = selected_pod['node']
                        if node_name and node_name != 'Unassigned':
                            # Save terminal state before showing node details
                            curses.def_prog_mode()
                            curses.endwin()
                            
                            # Get node details and show in less
                            node_details = self.describe_node(node_name, stdscr)
                            if node_details:
                                with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
                                    tmp.write(node_details)
                                    tmp_path = tmp.name
                                try:
                                    subprocess.run(['less', '-R', tmp_path])
                                finally:
                                    os.unlink(tmp_path)
                            
                            # Restore terminal state
                            curses.reset_prog_mode()
                            stdscr.clear()
                            stdscr.refresh()

            except curses.error:
                stdscr.clear()
                stdscr.refresh()

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Kubernetes Resource Viewer - An interactive terminal UI for exploring K8s resources',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    cache_group = parser.add_argument_group('Cache Settings')
    cache_group.add_argument(
        '--ttl',
        type=int,
        default=int(os.getenv('K8S_VIEWER_CACHE_TTL', '30')),
        help='Cache TTL in seconds. Can also be set via K8S_VIEWER_CACHE_TTL env var.'
    )
    cache_group.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable caching. Can also be set via K8S_VIEWER_CACHE_ENABLED=0 env var.'
    )
    cache_group.add_argument(
        '--cache-dir',
        type=str,
        default=os.getenv('K8S_VIEWER_CACHE_DIR', '~/.k8s_viewer'),
        help='Cache directory path. Can also be set via K8S_VIEWER_CACHE_DIR env var.'
    )

    log_group = parser.add_argument_group('Logging Settings')
    log_group.add_argument(
        '--log-level',
        type=str,
        choices=['debug', 'info', 'warning', 'error'],
        default=os.getenv('K8S_VIEWER_LOG_LEVEL', 'info'),
        help='Set logging level. Can also be set via K8S_VIEWER_LOG_LEVEL env var.'
    )
    log_group.add_argument(
        '--log-dir',
        type=str,
        default=Config.LOG_DIR,
        help='Log directory path. Can also be set via K8S_VIEWER_LOG_DIR env var.'
    )

    return parser.parse_args()

def main():
    """Main entry point"""
    args = parse_args()
    
    # Configure logging
    setup_logging(args.log_level)

    # Check if cache is disabled via environment variable
    cache_enabled = not args.no_cache and os.getenv('K8S_VIEWER_CACHE_ENABLED', '1') != '0'

    # Set cache directory in environment for potential subprocesses
    os.environ['K8S_VIEWER_CACHE_DIR'] = os.path.expanduser(args.cache_dir)
    os.environ['K8S_VIEWER_CACHE_TTL'] = str(args.ttl)
    os.environ['K8S_VIEWER_CACHE_ENABLED'] = '1' if cache_enabled else '0'

    viewer = K8sViewer(
        cache_ttl=args.ttl,
        cache_enabled=cache_enabled
    )
    curses.wrapper(viewer.run)

if __name__ == '__main__':
    main()
