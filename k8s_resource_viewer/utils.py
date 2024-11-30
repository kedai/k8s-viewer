import curses
import threading
import time
from contextlib import contextmanager

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
