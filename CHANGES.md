# Changelog

All notable changes to the Kubernetes Resource Viewer will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Double buffering for smoother screen rendering
- Configurable screen refresh rates
- Optimized terminal state management
- Status line showing full group name for truncated entries

### Changed
- Improved screen rendering performance
  - Replaced `clear()` with `erase()` for less visual disruption
  - Implemented double buffering using `noutrefresh()` and `doupdate()`
  - Increased input timeout from 50ms to 100ms for better CPU usage
  - Disabled immediate mode to prevent automatic refreshes
- Enhanced terminal state handling
  - Better cleanup on exit
  - Improved resize event handling
- Made group name display more compact while preserving readability
  - Reduced group column width
  - Added truncation with "..." for long names
  - Show full name in status line when highlighted

### Fixed
- Screen flickering in sub-screen displays
- Visual artifacts during screen transitions
- Excessive CPU usage from frequent screen refreshes
- Truncated group names in main display
- Navigation keys not working in main menu
  - Fixed up/down arrow key handling
  - Added support for both uppercase and lowercase 'j'/'k' keys
  - Corrected cursor position management

## [0.1.0] - Initial Release

### Added
- Basic Kubernetes resource viewing functionality
- Node group management
- Pod management and search
- Context switching
- Interactive navigation
- Caching system for improved performance
- Logging system
- Configuration via environment variables and command line options
