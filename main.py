"""
main.py
-------
Entry point for the AutoCAD Room Annotation Tool.

Starts the PySide6 (Qt) window. ``python main.py --tk`` starts the previous
Tkinter window instead (kept for comparison while the Qt UI is new).
"""

import os
import sys

# Ensure the project root is on the Python path when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main_tk():
    """Create the Tkinter root window and start its event loop."""
    import tkinter as tk

    from ui import AppUI

    root = tk.Tk()

    # High-DPI awareness on Windows so the UI is not blurry
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    AppUI(root)

    # Centre the window on screen
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    root.mainloop()


def main():
    if "--tk" in sys.argv[1:]:
        main_tk()
        return
    from qt_ui import main as main_qt
    sys.exit(main_qt())


if __name__ == "__main__":
    main()
