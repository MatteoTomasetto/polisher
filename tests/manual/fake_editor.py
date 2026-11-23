"""A tiny stand-in for a text editor, run as its own process (so it owns keyboard focus,
like Word or a browser would). Content is set via a command file and mirrored to an output file."""
import os
import sys
import tkinter as tk

CMD, OUT = sys.argv[1], sys.argv[2]
root = tk.Tk()
root.title("fake editor")
root.geometry("420x120+40+40")
box = tk.Text(root)
box.pack(fill="both", expand=True)


def paste(event):  # like a normal editor: paste replaces the selection
    try:
        box.delete("sel.first", "sel.last")
    except tk.TclError:
        pass
    box.insert("insert", box.clipboard_get())
    return "break"


box.bind("<<Paste>>", paste)


def tick():
    if os.path.exists(CMD):
        with open(CMD, encoding="utf-8") as fh:
            content = fh.read()
        os.remove(CMD)
        box.delete("1.0", "end")
        box.insert("1.0", content)
        root.lift()
        box.focus_force()
        box.tag_add("sel", "1.0", "end-1c")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(box.get("1.0", "end-1c"))
    root.after(100, tick)


tick()
root.mainloop()
