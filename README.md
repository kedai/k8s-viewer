# Kubernetes Resource Viewer

A terminal-based interactive UI for viewing and exploring Kubernetes cluster resources. This is a read-only tool designed for safe cluster inspection without modification capabilities.

## Features

- **Node Group Management**
  - View node groups with resource usage
  - Navigate through node groups using arrow keys or j/k
  - See CPU and memory utilization
  - View detailed node information

- **Pod Management**
  - Search pods across all namespaces
  - View pod details and status
  - See pod resource usage (CPU/Memory)
  - Display pod logs and events

- **Context Management**
  - View and switch between Kubernetes contexts
  - See current context in main view
  - Quick context switching with keyboard shortcuts
  - Automatic resource refresh after context switch

- **Interactive Navigation**
  - Vim-style keyboard shortcuts (j/k)
  - Arrow key support
  - Quick access to details with Enter key
  - Easy return to previous views

## Requirements

- Python 3.8+
- `kubectl` installed and configured
- Terminal with curses support
- Active Kubernetes cluster connection
- metrics-server installed in your cluster

## Installation

### Using pip (recommended)

1. Install the package:
   ```bash
   pip install k8s-resource-viewer
   ```

2. Verify kubectl is properly configured:
   ```bash
   kubectl config get-contexts
   ```

3. Run the viewer:
   ```bash
   k8s-viewer
   ```

### From Source

1. Clone the repository:
   ```bash
   git clone [repository-url]
   cd k8s-resource-viewer
   ```

2. Install in development mode:
   ```bash
   pip install -e .
   ```

   For development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

3. Run the viewer:
   ```bash
   k8s-viewer
   ```

### Platform-Specific Notes

- **Windows**: The `windows-curses` package will be automatically installed
- **Linux/MacOS**: Native curses support is included
- All platforms require `kubectl` to be in your system PATH

## Usage

### Command Line Options

```bash
k8s-viewer [options]
```

Options:
- `--log-level {debug,info,warning,error}` - Set logging level (default: info)
- `--log-dir PATH` - Custom log directory path
- `--ttl SECONDS` - Cache TTL in seconds (default: 30)
- `--no-cache` - Disable caching
- `--cache-dir PATH` - Custom cache directory path

### Environment Variables

- `K8S_VIEWER_LOG_LEVEL` - Set logging level (debug, info, warning, error)
- `K8S_VIEWER_LOG_DIR` - Custom log directory path
- `K8S_VIEWER_CACHE_TTL` - Cache TTL in seconds
- `K8S_VIEWER_CACHE_ENABLED` - Enable/disable caching (0/1)
- `K8S_VIEWER_CACHE_DIR` - Custom cache directory path

### Default Log Locations

The application logs are stored in platform-specific locations:

- **Linux**: `~/.local/state/k8s-viewer/logs/k8s_viewer.log`
- **macOS**: `~/Library/Logs/k8s-viewer/k8s_viewer.log`
- **Windows**: `%LOCALAPPDATA%\k8s-viewer\logs\k8s_viewer.log`

### Keyboard Shortcuts

Main Menu:
- `q` - Quit application
- `s` - Search pods
- `c` - Change Kubernetes context
- `r` - Refresh node groups
- `↑/k` - Move cursor up
- `↓/j` - Move cursor down
- `Enter` - View details

Pod Search:
- Type search pattern and press Enter
- `q` - Return to main menu
- `Enter/d` - View pod details
- `n` - View node details
- `↑/k` - Move cursor up
- `↓/j` - Move cursor down

Context Menu:
- `q` - Return to main menu
- `Enter` - Switch to selected context
- `↑/k` - Move cursor up
- `↓/j` - Move cursor down

### Views

1. Main View
   - Shows current Kubernetes context
   - Displays node groups with resource usage
   - Quick access to pod search and context switching

2. Pod Search
   - Search pods by name pattern
   - View pod status and resource usage
   - Access detailed pod information
   - View node details for pods

3. Context Selection
   - List all available contexts
   - Current context marked with *
   - Easy switching between contexts
   - Automatic resource refresh

## Error Handling

- Graceful handling of kubectl command failures
- Clear error messages for connection issues
- Recovery from terminal resize events
- Proper cleanup of temporary files

## Security

- Read-only access to cluster resources
- Uses existing kubectl configuration
- No modification of cluster state
- Clean temporary file management

## Contributing

Contributions are welcome! Please feel free to submit pull requests.

## License

[License information]

## Troubleshooting

1. **Connection Issues**
   - Ensure kubectl is properly configured
   - Check cluster connectivity
   - Verify context permissions

2. **Display Issues**
   - Check terminal size requirements
   - Ensure curses support
   - Verify color terminal support

3. **Performance**
   - Consider cluster size
   - Check network connectivity
   - Monitor resource usage

## Support

For issues and feature requests, please create an issue in the repository.

## Future Improvements

### Core Features
- [ ] Namespace filtering and management
- [ ] Live resource usage monitoring
- [ ] Interactive log streaming
- [ ] Advanced search patterns for resources

### User Interface
- [ ] Mouse support for navigation
- [ ] Resource usage graphs
- [ ] Split-screen view for logs and details
- [ ] Customizable column display

### Performance
- [ ] Intelligent caching system
- [ ] Pagination for large clusters
- [ ] Background resource refresh

### Monitoring
- [ ] Real-time resource metrics
- [ ] Event timeline viewer
- [ ] Multi-container log viewer
- [ ] Custom metric visualization

Want to contribute? Pick an item from the list above and submit a pull request!
