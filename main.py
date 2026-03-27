"""
main.py
-------
Entry point for the AutoCAD Room Annotation Tool.
Initialises the Tkinter root window and launches the AppUI.
"""

import sys
import tkinter as tk

# Ensure the project root is on the Python path when run directly
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import AppUI


def main():
    """Create the root window and start the Tkinter event loop."""
    root = tk.Tk()

    # High-DPI awareness on Windows so the UI is not blurry
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = AppUI(root)

    # Centre the window on screen
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.mainloop()


if __name__ == "__main__":
    main()
