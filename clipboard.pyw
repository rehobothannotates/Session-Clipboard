import ctypes
import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

# ---------- Look and feel (change these colors if you like) ----------
BG = "#1b1d24"
CARD = "#262833"
SELECT = "#3a4a8a"
ACCENT = "#6c8cff"
ACCENT_HOVER = "#8aa3ff"
BTN = "#323546"
BTN_HOVER = "#41455a"
DANGER = "#c94f63"
DANGER_HOVER = "#e0657a"
TEXT = "#e8e9ef"
MUTED = "#8a8fa3"
GREEN = "#4cd08a"
AMBER = "#f0b45a"
FONT = "Segoe UI"


def make_button(parent, text, command, kind="normal"):
    palette = {
        "normal": (BTN, BTN_HOVER, "white"),
        "accent": (ACCENT, ACCENT_HOVER, "#10131f"),
        "danger": (DANGER, DANGER_HOVER, "white"),
    }
    base, hover, fg = palette[kind]
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=base,
        fg=fg,
        activebackground=hover,
        activeforeground=fg,
        relief="flat",
        bd=0,
        highlightthickness=0,
        padx=12,
        pady=8,
        cursor="hand2",
        font=(FONT, 9, "bold"),
    )
    btn.bind("<Enter>", lambda e: btn.config(bg=hover))
    btn.bind("<Leave>", lambda e: btn.config(bg=base))
    return btn


def dark_titlebar(window):
    """Makes the Windows title bar dark (cosmetic; ignored if unsupported)."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


class ClipboardApp:
    def __init__(self, root):
        self.root = root
        self.items = []  # each item: {"text": ..., "time": ...}, newest first
        self.last = None
        self.recording = True
        self.flash_job = None

        root.title("Session Clipboard")
        root.geometry("460x640")
        root.minsize(400, 460)
        root.configure(bg=BG)
        root.attributes("-topmost", True)

        self.build_ui()
        dark_titlebar(root)
        self.reset_status()
        self.refresh()
        self.poll()

    # ---------- Building the window ----------
    def build_ui(self):
        root = self.root

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=16, pady=(16, 2))
        tk.Label(
            header, text="Session Clipboard", bg=BG, fg=TEXT, font=(FONT, 16, "bold")
        ).pack(side="left")
        self.pause_btn = make_button(header, "Pause", self.toggle_recording, "normal")
        self.pause_btn.pack(side="right")

        self.status = tk.Label(root, text="", bg=BG, fg=GREEN, font=(FONT, 9), anchor="w")
        self.status.pack(fill="x", padx=16, pady=(0, 8))

        # Search box
        search_wrap = tk.Frame(root, bg=CARD)
        search_wrap.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(search_wrap, text="Search", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(
            side="left", padx=(12, 6)
        )
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.refresh())
        tk.Entry(
            search_wrap,
            textvariable=self.search_var,
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=0,
            font=(FONT, 10),
        ).pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 10))

        # List of copied items
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Clip.Treeview",
            background=CARD,
            fieldbackground=CARD,
            foreground=TEXT,
            rowheight=38,
            borderwidth=0,
            font=(FONT, 10),
        )
        style.map(
            "Clip.Treeview",
            background=[("selected", SELECT)],
            foreground=[("selected", "white")],
        )
        style.layout("Clip.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Clip.Vertical.TScrollbar",
            background=BTN,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=TEXT,
            lightcolor=BTN,
            darkcolor=BTN,
        )

        list_frame = tk.Frame(root, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=16)
        self.tree = ttk.Treeview(
            list_frame,
            style="Clip.Treeview",
            columns=("text", "time"),
            show="",
            selectmode="extended",
        )
        self.tree.column("text", anchor="w", stretch=True, width=300)
        self.tree.column("time", anchor="e", stretch=False, width=60)
        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview,
            style="Clip.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self.copy_selected)
        self.tree.bind("<Delete>", lambda e: self.delete_selected())
        self.tree.bind("<Control-a>", self.select_all)

        self.empty_label = tk.Label(
            list_frame, text="", bg=CARD, fg=MUTED, font=(FONT, 10), justify="center"
        )

        # Count and "stay on top"
        footer = tk.Frame(root, bg=BG)
        footer.pack(fill="x", padx=16, pady=(8, 6))
        self.count = tk.Label(footer, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.count.pack(side="left")
        self.top_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            footer,
            text="Stay on top",
            variable=self.top_var,
            command=lambda: self.root.attributes("-topmost", self.top_var.get()),
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=TEXT,
            selectcolor=CARD,
            bd=0,
            highlightthickness=0,
            font=(FONT, 9),
        ).pack(side="right")

        # Buttons
        buttons = tk.Frame(root, bg=BG)
        buttons.pack(fill="x", padx=13, pady=(0, 14))
        layout = [
            [
                ("Copy", self.copy_selected, "accent"),
                ("Edit", self.edit_selected, "normal"),
                ("Delete", self.delete_selected, "normal"),
            ],
            [
                ("Save selected", self.save_selected, "normal"),
                ("Save all", self.save_all, "normal"),
                ("Clear all", self.clear_all, "danger"),
            ],
        ]
        for r, row in enumerate(layout):
            for c, (label, command, kind) in enumerate(row):
                make_button(buttons, label, command, kind).grid(
                    row=r, column=c, sticky="ew", padx=3, pady=3
                )
        for c in range(3):
            buttons.columnconfigure(c, weight=1, uniform="buttons")

    # ---------- Watching the clipboard ----------
    def poll(self):
        if self.recording:
            try:
                text = self.root.clipboard_get()
            except tk.TclError:
                text = None  # clipboard empty or not text
            if text and text.strip() and text != self.last:
                self.last = text
                self.add_item(text)
        self.root.after(400, self.poll)

    def add_item(self, text):
        self.items = [i for i in self.items if i["text"] != text]
        self.items.insert(
            0, {"text": text, "time": datetime.now().strftime("%H:%M")}
        )
        self.refresh()

    def toggle_recording(self):
        self.recording = not self.recording
        if self.recording:
            try:
                self.last = self.root.clipboard_get()  # ignore what was copied while paused
            except tk.TclError:
                self.last = None
            self.pause_btn.config(text="Pause")
        else:
            self.pause_btn.config(text="Resume")
        self.reset_status()

    # ---------- Showing the list ----------
    @staticmethod
    def one_line(text):
        line = " ".join(text.split())
        return line if len(line) <= 90 else line[:90] + "..."

    def selected_indices(self):
        return [int(i) for i in self.tree.selection()]

    def refresh(self):
        query = self.search_var.get().strip().lower()
        keep = {id(self.items[i]) for i in self.selected_indices() if i < len(self.items)}

        self.tree.delete(*self.tree.get_children())
        to_select = []
        shown = 0
        for i, item in enumerate(self.items):
            if query and query not in item["text"].lower():
                continue
            self.tree.insert(
                "", "end", iid=str(i), values=(self.one_line(item["text"]), item["time"])
            )
            shown += 1
            if id(item) in keep:
                to_select.append(str(i))
        if to_select:
            self.tree.selection_set(to_select)

        total = len(self.items)
        if query:
            self.count.config(text=f"{shown} of {total} shown")
        else:
            self.count.config(text=f"{total} item" + ("" if total == 1 else "s"))

        if shown == 0:
            msg = (
                "No matches."
                if total
                else "Nothing copied yet.\nCopy some text and it will appear here."
            )
            self.empty_label.config(text=msg)
            self.empty_label.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self.empty_label.place_forget()

    def select_all(self, event=None):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    # ---------- Status line ----------
    def reset_status(self):
        if self.recording:
            self.status.config(text="●  Recording what you copy", fg=GREEN)
        else:
            self.status.config(text="⏸  Paused (not saving new copies)", fg=AMBER)

    def flash(self, message, color=GREEN, ms=1800):
        self.status.config(text=message, fg=color)
        if self.flash_job:
            self.root.after_cancel(self.flash_job)
        self.flash_job = self.root.after(ms, self.reset_status)

    # ---------- Actions ----------
    def copy_selected(self, event=None):
        idx = self.selected_indices()
        if not idx:
            self.flash("Select an item first", AMBER)
            return
        ordered = sorted(idx, reverse=True)  # oldest first when combining
        text = "\n\n".join(self.items[i]["text"] for i in ordered)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.last = text
        if len(idx) == 1:
            self.flash("Copied. Now paste with Ctrl+V")
        else:
            self.flash(f"Copied {len(idx)} items together. Paste with Ctrl+V")

    def delete_selected(self):
        idx = set(self.selected_indices())
        if not idx:
            self.flash("Select an item first", AMBER)
            return
        self.items = [item for i, item in enumerate(self.items) if i not in idx]
        self.refresh()
        self.flash("Deleted")

    def edit_selected(self, event=None):
        idx = self.selected_indices()
        if not idx:
            self.flash("Select an item first", AMBER)
            return
        item = self.items[idx[0]]

        win = tk.Toplevel(self.root)
        win.title("Edit item")
        win.configure(bg=BG)
        win.geometry("480x380")
        win.minsize(360, 260)
        win.transient(self.root)

        # Buttons are placed first, at the bottom, so they are always visible
        row = tk.Frame(win, bg=BG)
        row.pack(side="bottom", fill="x", padx=16, pady=(0, 14))

        box = tk.Text(
            win,
            height=8,
            wrap="word",
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=SELECT,
            relief="flat",
            highlightthickness=0,
            font=(FONT, 10),
            padx=12,
            pady=12,
            undo=True,
        )
        box.insert("1.0", item["text"])
        box.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        box.focus_set()

        def save():
            new_text = box.get("1.0", "end-1c")
            if new_text.strip():
                item["text"] = new_text
                self.refresh()
                self.flash("Item updated")
            win.destroy()

        make_button(row, "Save changes", save, "accent").pack(side="right")
        make_button(row, "Cancel", win.destroy, "normal").pack(side="right", padx=(0, 8))
        box.bind("<Control-Return>", lambda e: (save(), "break")[1])
        dark_titlebar(win)

    def notes_path(self):
        folder = os.path.join(os.path.expanduser("~"), "Documents")
        if not os.path.isdir(folder):
            folder = os.path.expanduser("~")
        return os.path.join(folder, "clipboard_notes.txt")

    def save_to_notes(self, texts):
        if not texts:
            self.flash("Nothing to save yet", AMBER)
            return
        path = self.notes_path()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n--- Saved {stamp} ---\n")
            for t in texts:
                f.write(t + "\n\n")
        folder_name = os.path.basename(os.path.dirname(path))
        self.flash(f"Saved to {folder_name}\\clipboard_notes.txt", GREEN, 3500)

    def save_selected(self):
        idx = self.selected_indices()
        if not idx:
            self.flash("Select one or more items first", AMBER)
            return
        self.save_to_notes([self.items[i]["text"] for i in sorted(idx, reverse=True)])

    def save_all(self):
        self.save_to_notes([item["text"] for item in reversed(self.items)])

    def clear_all(self):
        if self.items and messagebox.askyesno("Clear all", "Remove everything from the list?"):
            self.items.clear()
            self.refresh()
            self.flash("Cleared")


if __name__ == "__main__":
    root = tk.Tk()
    ClipboardApp(root)
    root.mainloop()
