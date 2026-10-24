"""
Personal Task Manager - Fancy UI version
-----------------------------------------
Tech: Python 3 + Tkinter + CustomTkinter

Features
  * Login / first-time sign-up (credentials in config.ini, password hashed)
  * Tasks shown as cards with coloured priority badges and due-date chips
  * Tick the round checkbox on a card to complete / un-complete a task
  * Pop-up window to add or edit a task, with a built-in calendar date picker
  * Sidebar sections: All, Today, Upcoming, Overdue, Completed (with counts)
  * Progress bar, stat cards, search, priority + category filters, sorting
  * Toast messages ("Task added") that appear for a moment
  * Light / dark mode switch
  * Tasks saved in tasks.txt (one JSON record per line) - same file as before

Setup (once):  pip install customtkinter
Run:           python task_manager_fancy.py
Shortcut:      Ctrl+N = new task
"""

import calendar
import configparser
import hashlib
import json
import os
import secrets
import tkinter as tk
import uuid
from datetime import date, datetime
from tkinter import messagebox

import customtkinter as ctk

# ------------------------------------------------------------------ settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(BASE_DIR, "tasks.txt")
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
ICON_FILE = os.path.join(BASE_DIR, "app_icon.ico")   # put app_icon.ico next to this file

DATE_FMT = "%Y-%m-%d"
PRIORITIES = ["High", "Medium", "Low"]
STATUSES = ["Pending", "In Progress", "Completed"]
CATEGORIES = ["Work", "Personal", "Study", "Shopping", "Health", "Other"]
PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}
SORT_OPTIONS = ["Sort: Due date", "Sort: Priority", "Sort: Title", "Sort: Newest"]

# ---- colours: (light mode, dark mode) ----
APP_BG = ("#f3f4f8", "#17181c")
SIDEBAR_BG = ("#ffffff", "#1f2126")
CARD = ("#ffffff", "#25272d")
TEXT = ("#1f2328", "#e8eaed")
MUTED = ("#6b7280", "#9aa0a8")
BORDER = ("#e3e5ea", "#33363d")
HOVER = ("#eef0f4", "#2e3138")
ACCENT = "#6366f1"
ACCENT_HOVER = "#4f46e5"
ACCENT_SOFT = ("#e8e9fd", "#2c2e5a")
ACCENT_TEXT = ("#4338ca", "#a5b4fc")
SUCCESS = "#16a34a"
DANGER = "#dc2626"

PRIORITY_COLORS = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}

# chip styles: (background, text colour), each light/dark
CHIP_RED = (("#fde2e2", "#4a1f22"), ("#dc2626", "#f87171"))
CHIP_AMBER = (("#fdf0d5", "#4a3a17"), ("#b45309", "#fbbf24"))
CHIP_GREEN = (("#dcf5e5", "#1d3d2a"), ("#15803d", "#4ade80"))
CHIP_BLUE = (("#dde7fd", "#1e2a4a"), ("#1d4ed8", "#93b4fd"))
CHIP_GRAY = (("#eceef2", "#33363d"), ("#4b5563", "#b4b9c2"))
CHIP_PURPLE = (("#ece9fe", "#2e2a4f"), ("#6d28d9", "#c4b5fd"))
PRIORITY_CHIP = {"High": CHIP_RED, "Medium": CHIP_AMBER, "Low": CHIP_GREEN}

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")


# ------------------------------------------------------------------ helpers
def parse_date(text):
    """Return a date object, or None if text is blank/invalid."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, DATE_FMT).date()
    except ValueError:
        return None


def nice_date(d):
    return d.strftime("%d %b %Y")


def is_done(t):
    return t["status"] == "Completed"


def is_overdue(t):
    d = parse_date(t.get("due_date"))
    return bool(d and d < date.today() and not is_done(t))


def chip(parent, text, style):
    """Small rounded coloured label, like a tag/badge."""
    bg, fg = style
    return ctk.CTkLabel(parent, text=f"  {text}  ", fg_color=bg, text_color=fg,
                        corner_radius=10, height=24, font=ctk.CTkFont(size=12, weight="bold"))


def apply_icon(window):
    """Show the TM icon in the window's title bar and taskbar (if app_icon.ico exists)."""
    def _set():
        try:
            window.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass   # e.g. file missing or not supported on this system
    if os.path.exists(ICON_FILE):
        _set()
        window.after(250, _set)   # CustomTkinter sets its own icon after 200 ms - override it


def tm_logo(parent, size=40, radius=12, font_size=16, inverted=False):
    """The 'TM' badge used as the app logo inside the window."""
    return ctk.CTkLabel(parent, text="TM", width=size, height=size, corner_radius=radius,
                        fg_color="white" if inverted else ACCENT,
                        text_color=ACCENT if inverted else "white",
                        font=ctk.CTkFont(size=font_size, weight="bold"))


def center_on(window, parent):
    """Place a pop-up window in the middle of its parent window."""
    window.update_idletasks()
    w, h = window.winfo_reqwidth(), window.winfo_reqheight()
    px, py = parent.winfo_rootx(), parent.winfo_rooty()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    window.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")


# ------------------------------------------------------------------ storage
class TaskStorage:
    """Saves/loads tasks to a plain text file, one JSON object per line."""

    def __init__(self, path):
        self.path = path

    def load(self):
        tasks = []
        if not os.path.exists(self.path):
            return tasks
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tasks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return tasks

    def save(self, tasks):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for t in tasks:
                f.write(json.dumps(t) + "\n")
        os.replace(tmp, self.path)


# ------------------------------------------------------------------ auth
def hash_password(password, salt):
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


class AuthManager:
    """Stores one user's credentials in config.ini."""

    def __init__(self, path):
        self.path = path
        self.config = configparser.ConfigParser()
        if os.path.exists(path):
            self.config.read(path)

    def has_user(self):
        return self.config.has_section("user")

    def create_user(self, username, password):
        salt = secrets.token_hex(16)
        self.config["user"] = {
            "username": username,
            "salt": salt,
            "password_hash": hash_password(password, salt),
        }
        with open(self.path, "w") as f:
            self.config.write(f)

    def verify(self, username, password):
        if not self.has_user():
            return False
        u = self.config["user"]
        return (username == u.get("username")
                and hash_password(password, u.get("salt", "")) == u.get("password_hash"))


# ------------------------------------------------------------------ login screen
class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, auth, on_success):
        super().__init__(master, fg_color="transparent")
        self.auth = auth
        self.on_success = on_success
        self.signup_mode = not auth.has_user()

        card = ctk.CTkFrame(self, corner_radius=22, fg_color=CARD, border_width=1, border_color=BORDER)
        card.place(relx=0.5, rely=0.5, anchor="center")

        # left: coloured welcome panel
        hero = ctk.CTkFrame(card, corner_radius=18, fg_color=ACCENT, width=320, height=440)
        hero.grid(row=0, column=0, padx=10, pady=10, sticky="ns")
        hero.pack_propagate(False)
        tm_logo(hero, size=92, radius=26, font_size=38, inverted=True).pack(pady=(56, 14))
        ctk.CTkLabel(hero, text="Task Manager", text_color="white",
                     font=ctk.CTkFont(size=28, weight="bold")).pack()
        ctk.CTkLabel(hero, text="Plan your day.\nFinish what matters.", text_color="#e0e1ff",
                     font=ctk.CTkFont(size=15), justify="center").pack(pady=(10, 26))
        for line in ("✓  Organise tasks by priority", "✓  Never miss a due date", "✓  Track your progress"):
            ctk.CTkLabel(hero, text=line, text_color="white",
                         font=ctk.CTkFont(size=13)).pack(anchor="w", padx=48, pady=3)

        # right: form
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.grid(row=0, column=1, padx=(30, 44), pady=30)
        ctk.CTkLabel(form, text="Create account" if self.signup_mode else "Welcome back",
                     text_color=TEXT, font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(form, text="Set up your login to get started" if self.signup_mode
                     else "Log in to see your tasks",
                     text_color=MUTED, font=ctk.CTkFont(size=13)).pack(anchor="w", pady=(2, 22))

        self.user_entry = self.field(form, "Username", "Enter your username")
        self.pass_entry = self.field(form, "Password", "Enter your password", secret=True)
        self.confirm_entry = None
        if self.signup_mode:
            self.confirm_entry = self.field(form, "Confirm password", "Type it again", secret=True)

        ctk.CTkButton(form, text="Create Account  →" if self.signup_mode else "Log In  →",
                      width=300, height=44, corner_radius=12, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(size=15, weight="bold"), command=self.submit).pack(pady=(18, 0))

        master.bind("<Return>", lambda e: self.submit())
        self.after(200, self.user_entry.focus)

    def field(self, parent, label, hint, secret=False):
        ctk.CTkLabel(parent, text=label, text_color=TEXT,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(6, 2))
        e = ctk.CTkEntry(parent, placeholder_text=hint, width=300, height=42, corner_radius=10,
                         border_color=BORDER, show="•" if secret else "")
        e.pack()
        return e

    def submit(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get()
        if not username or not password:
            messagebox.showwarning("Missing", "Enter username and password.")
            return
        if self.signup_mode:
            if len(password) < 4:
                messagebox.showwarning("Weak password", "Use at least 4 characters.")
                return
            if password != self.confirm_entry.get():
                messagebox.showerror("Mismatch", "Passwords do not match.")
                return
            self.auth.create_user(username, password)
            self.finish(username)
        elif self.auth.verify(username, password):
            self.finish(username)
        else:
            messagebox.showerror("Login failed", "Invalid username or password.")
            self.pass_entry.delete(0, "end")

    def finish(self, username):
        self.master.unbind("<Return>")
        self.on_success(username)


# ------------------------------------------------------------------ calendar pop-up
class DatePicker(ctk.CTkToplevel):
    """Small month calendar. Calls on_pick(date) when a day is clicked."""

    def __init__(self, master, initial, on_pick):
        super().__init__(master)
        self.master_win = master
        self.on_pick = on_pick
        self.selected = initial
        base = initial or date.today()
        self.year, self.month = base.year, base.month

        self.title("Pick a date")
        apply_icon(self)
        self.resizable(False, False)
        self.configure(fg_color=CARD)
        self.transient(master)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(14, 4))
        nav = dict(width=34, height=32, corner_radius=8, fg_color=HOVER,
                   text_color=TEXT, hover_color=BORDER, font=ctk.CTkFont(size=16, weight="bold"))
        ctk.CTkButton(head, text="‹", command=lambda: self.shift(-1), **nav).pack(side="left")
        ctk.CTkButton(head, text="›", command=lambda: self.shift(1), **nav).pack(side="right")
        self.month_label = ctk.CTkLabel(head, text="", text_color=TEXT,
                                        font=ctk.CTkFont(size=15, weight="bold"))
        self.month_label.pack(side="left", expand=True)

        self.days = ctk.CTkFrame(self, fg_color="transparent")
        self.days.pack(padx=14, pady=4)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=(4, 14))
        ctk.CTkButton(foot, text="Today", width=90, height=32, fg_color=ACCENT_SOFT, text_color=ACCENT_TEXT,
                      hover_color=BORDER, command=lambda: self.pick(date.today())).pack(side="left")
        ctk.CTkButton(foot, text="Cancel", width=90, height=32, fg_color="transparent", border_width=1,
                      border_color=BORDER, text_color=TEXT, hover_color=HOVER,
                      command=self.close).pack(side="right")

        self.draw()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        center_on(self, master)
        self.after(150, self.activate)

    def activate(self):
        self.lift()
        self.grab_set()
        self.focus()

    def shift(self, step):
        m = self.month + step
        self.year += (m - 1) // 12
        self.month = (m - 1) % 12 + 1
        self.draw()

    def draw(self):
        for w in self.days.winfo_children():
            w.destroy()
        self.month_label.configure(text=f"{calendar.month_name[self.month]} {self.year}")
        for i, name in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            ctk.CTkLabel(self.days, text=name, width=38, text_color=MUTED,
                         font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=i, pady=(0, 4))
        today = date.today()
        for r, week in enumerate(calendar.monthcalendar(self.year, self.month), start=1):
            for c, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(self.days, text="", width=38).grid(row=r, column=c)
                    continue
                d = date(self.year, self.month, day)
                if d == self.selected:
                    fg, tc = ACCENT, "white"
                elif d == today:
                    fg, tc = ACCENT_SOFT, ACCENT_TEXT
                else:
                    fg, tc = "transparent", TEXT
                ctk.CTkButton(self.days, text=str(day), width=38, height=34, corner_radius=8,
                              fg_color=fg, text_color=tc, hover_color=HOVER,
                              command=lambda d=d: self.pick(d)).grid(row=r, column=c, padx=1, pady=1)

    def pick(self, d):
        self.close()
        self.on_pick(d)

    def close(self):
        self.grab_release()
        self.destroy()
        try:
            self.master_win.grab_set()   # give control back to the task pop-up
        except tk.TclError:
            pass


# ------------------------------------------------------------------ add / edit pop-up
class TaskDialog(ctk.CTkToplevel):
    def __init__(self, master, task, categories, on_save):
        super().__init__(master)
        self.root_win = master
        self.task = task
        self.on_save = on_save
        self.due = parse_date(task.get("due_date")) if task else None

        self.title("Edit Task" if task else "New Task")
        apply_icon(self)
        self.resizable(False, False)
        self.configure(fg_color=APP_BG)
        self.transient(master)

        box = ctk.CTkFrame(self, corner_radius=18, fg_color=CARD)
        box.pack(fill="both", expand=True, padx=16, pady=16)
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(padx=26, pady=22)

        ctk.CTkLabel(inner, text="Edit task" if task else "Create a new task", text_color=TEXT,
                     font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", pady=(0, 14))

        self.label(inner, "Title")
        self.title_entry = ctk.CTkEntry(inner, placeholder_text="What do you need to do?",
                                        width=420, height=42, corner_radius=10, border_color=BORDER)
        self.title_entry.pack()

        self.label(inner, "Description")
        self.desc_box = ctk.CTkTextbox(inner, width=420, height=80, corner_radius=10,
                                       border_width=2, border_color=BORDER)
        self.desc_box.pack()

        self.label(inner, "Priority")
        self.priority_btn = ctk.CTkSegmentedButton(inner, values=PRIORITIES, height=36,
                                                   selected_color=ACCENT, selected_hover_color=ACCENT_HOVER)
        self.priority_btn.pack(fill="x")

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        row.grid_columnconfigure((0, 1), weight=1)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.label(left, "Category")
        self.category_box = ctk.CTkComboBox(left, values=categories, height=38, corner_radius=10,
                                            border_color=BORDER, button_color=ACCENT,
                                            button_hover_color=ACCENT_HOVER)
        self.category_box.pack(fill="x")
        self.label(right, "Status")
        self.status_menu = ctk.CTkOptionMenu(right, values=STATUSES, height=38, corner_radius=10,
                                             fg_color=ACCENT, button_color=ACCENT_HOVER,
                                             button_hover_color="#4338ca")
        self.status_menu.pack(fill="x")

        self.label(inner, "Due date")
        due_row = ctk.CTkFrame(inner, fg_color="transparent")
        due_row.pack(fill="x")
        self.due_btn = ctk.CTkButton(due_row, text="", height=40, corner_radius=10, anchor="w",
                                     fg_color=HOVER, text_color=TEXT, hover_color=BORDER,
                                     command=self.open_calendar)
        self.due_btn.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(due_row, text="✕", width=40, height=40, corner_radius=10, fg_color=HOVER,
                      text_color=MUTED, hover_color=BORDER,
                      command=lambda: self.set_due(None)).pack(side="left", padx=(8, 0))

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(fill="x", pady=(24, 0))
        ctk.CTkButton(btns, text="Save Task" if task else "Add Task", width=140, height=42,
                      corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(size=14, weight="bold"), command=self.save).pack(side="right")
        ctk.CTkButton(btns, text="Cancel", width=100, height=42, corner_radius=10, fg_color="transparent",
                      border_width=1, border_color=BORDER, text_color=TEXT, hover_color=HOVER,
                      command=self.close).pack(side="right", padx=10)

        # fill in values
        if task:
            self.title_entry.insert(0, task["title"])
            self.desc_box.insert("1.0", task.get("description", ""))
            self.priority_btn.set(task["priority"])
            self.category_box.set(task.get("category", "Other"))
            self.status_menu.set(task["status"])
        else:
            self.priority_btn.set("Medium")
            self.category_box.set("Personal")
            self.status_menu.set("Pending")
        self.set_due(self.due)

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        self.title_entry.bind("<Return>", lambda e: self.save())
        center_on(self, master)
        self.after(150, self.activate)

    def label(self, parent, text):
        ctk.CTkLabel(parent, text=text, text_color=MUTED,
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(12, 4))

    def activate(self):
        self.lift()
        self.grab_set()
        self.title_entry.focus()

    def set_due(self, d):
        self.due = d
        self.due_btn.configure(text=f"   {nice_date(d)}" if d else "   Pick a date...",
                               text_color=TEXT if d else MUTED)

    def open_calendar(self):
        DatePicker(self, self.due, self.set_due)

    def save(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Missing title", "Please give the task a title.", parent=self)
            return
        data = {
            "title": title,
            "description": self.desc_box.get("1.0", "end").strip(),
            "priority": self.priority_btn.get() or "Medium",
            "due_date": self.due.strftime(DATE_FMT) if self.due else "",
            "category": self.category_box.get().strip() or "Other",
            "status": self.status_menu.get(),
        }
        self.close()
        self.on_save(self.task, data)

    def close(self):
        self.grab_release()
        self.destroy()


# ------------------------------------------------------------------ main screen
class TaskManagerFrame(ctk.CTkFrame):
    VIEWS = [("All Tasks", "☰"), ("Today", "☀"), ("Upcoming", "➜"),
             ("Overdue", "⚠"), ("Completed", "✓")]

    def __init__(self, master, username, on_logout, toast):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self.username = username
        self.on_logout = on_logout
        self.toast = toast
        self.storage = TaskStorage(TASKS_FILE)
        self.tasks = self.storage.load()
        self.view = "All Tasks"

        self.f_title = ctk.CTkFont(size=15, weight="bold")
        self.f_title_done = ctk.CTkFont(size=15, weight="bold", overstrike=True)
        self.f_small = ctk.CTkFont(size=12)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.build_sidebar()

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=26, pady=20)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)
        self.build_header(main)
        self.build_stats(main)
        self.build_toolbar(main)
        self.list_frame = ctk.CTkScrollableFrame(main, fg_color="transparent")
        self.list_frame.grid(row=3, column=0, sticky="nsew", pady=(6, 0))

        master.bind("<Control-n>", lambda e: self.open_dialog())
        self.refresh()

    # ---------- sidebar ----------
    def build_sidebar(self):
        side = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=SIDEBAR_BG)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.pack_propagate(False)

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=22, pady=(26, 22))
        tm_logo(brand).pack(side="left")
        ctk.CTkLabel(brand, text="  Task Manager", text_color=TEXT,
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        ctk.CTkLabel(side, text="MY LISTS", text_color=MUTED,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=26, pady=(0, 6))
        self.nav_buttons, self.nav_counts = {}, {}
        for name, icon in self.VIEWS:
            holder = ctk.CTkFrame(side, fg_color="transparent")
            holder.pack(fill="x", padx=14, pady=2)
            btn = ctk.CTkButton(holder, text=f"  {icon}    {name}", anchor="w", height=40, corner_radius=10,
                                font=ctk.CTkFont(size=14), command=lambda n=name: self.set_view(n))
            btn.pack(fill="x")
            count = ctk.CTkLabel(holder, text="0", width=30, height=22, corner_radius=8,
                                 font=ctk.CTkFont(size=12, weight="bold"))
            count.place(relx=0.95, rely=0.5, anchor="e")
            count.bind("<Button-1>", lambda e, n=name: self.set_view(n))
            self.nav_buttons[name], self.nav_counts[name] = btn, count

        # progress card
        prog = ctk.CTkFrame(side, corner_radius=14, fg_color=ACCENT_SOFT)
        prog.pack(fill="x", padx=16, pady=(26, 0))
        ctk.CTkLabel(prog, text="Your progress", text_color=ACCENT_TEXT,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(14, 6))
        self.progress = ctk.CTkProgressBar(prog, height=10, corner_radius=5,
                                           progress_color=ACCENT, fg_color=("#ffffff", "#1f2126"))
        self.progress.pack(fill="x", padx=16)
        self.progress_text = ctk.CTkLabel(prog, text="", text_color=ACCENT_TEXT, font=self.f_small)
        self.progress_text.pack(anchor="w", padx=16, pady=(6, 14))

        # bottom: user, theme, logout
        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=16, pady=20)
        user = ctk.CTkFrame(bottom, corner_radius=12, fg_color=HOVER)
        user.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(user, text=self.username[:1].upper(), width=36, height=36, corner_radius=18,
                     fg_color=ACCENT, text_color="white",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left", padx=10, pady=10)
        ctk.CTkLabel(user, text=self.username, text_color=TEXT,
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self.theme_switch = ctk.CTkSwitch(bottom, text="Dark mode", text_color=TEXT,
                                          progress_color=ACCENT, command=self.toggle_theme)
        if ctk.get_appearance_mode() == "Dark":
            self.theme_switch.select()
        self.theme_switch.pack(anchor="w", padx=6, pady=(0, 10))
        ctk.CTkButton(bottom, text="Log out", height=38, corner_radius=10, fg_color="transparent",
                      border_width=1, border_color=BORDER, text_color=TEXT, hover_color=HOVER,
                      command=self.on_logout).pack(fill="x")

    def toggle_theme(self):
        ctk.set_appearance_mode("Dark" if self.theme_switch.get() else "Light")

    def set_view(self, name):
        self.view = name
        self.refresh()

    # ---------- header + stats ----------
    def build_header(self, parent):
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        hour = datetime.now().hour
        greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        text = ctk.CTkFrame(head, fg_color="transparent")
        text.pack(side="left")
        ctk.CTkLabel(text, text=f"{greet}, {self.username}", text_color=TEXT,
                     font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(text, text=date.today().strftime("%A, %d %B %Y"), text_color=MUTED,
                     font=ctk.CTkFont(size=13)).pack(anchor="w")
        ctk.CTkButton(head, text="+   New Task", height=44, width=150, corner_radius=12,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=14, weight="bold"),
                      command=self.open_dialog).pack(side="right")

    def build_stats(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(18, 14))
        self.stat_labels = {}
        stats = [("Total tasks", "total", ACCENT), ("Pending", "pending", "#f59e0b"),
                 ("Completed", "completed", "#22c55e"), ("Overdue", "overdue", "#ef4444")]
        for i, (name, key, color) in enumerate(stats):
            row.grid_columnconfigure(i, weight=1)
            card = ctk.CTkFrame(row, corner_radius=14, fg_color=CARD, border_width=1, border_color=BORDER)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 7, 0 if i == 3 else 7))
            ctk.CTkFrame(card, width=5, height=44, corner_radius=3, fg_color=color).pack(
                side="left", padx=(14, 12), pady=16)
            box = ctk.CTkFrame(card, fg_color="transparent")
            box.pack(side="left", pady=10)
            num = ctk.CTkLabel(box, text="0", text_color=TEXT, font=ctk.CTkFont(size=26, weight="bold"))
            num.pack(anchor="w")
            ctk.CTkLabel(box, text=name, text_color=MUTED, font=self.f_small).pack(anchor="w")
            self.stat_labels[key] = num

    # ---------- toolbar ----------
    def build_toolbar(self, parent):
        bar = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD, border_width=1, border_color=BORDER)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        self.list_title = ctk.CTkLabel(inner, text="", text_color=TEXT,
                                       font=ctk.CTkFont(size=17, weight="bold"))
        self.list_title.pack(side="left", padx=(6, 16))

        self.search = ctk.CTkEntry(inner, placeholder_text="Search tasks...", width=200, height=36,
                                   corner_radius=10, border_color=BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda e: self.refresh())

        refresh = lambda _v: self.refresh()
        self.sort_menu = ctk.CTkOptionMenu(inner, values=SORT_OPTIONS, width=140, height=36, corner_radius=10,
                                           fg_color=HOVER, button_color=BORDER, button_hover_color=HOVER,
                                           text_color=TEXT, command=refresh)
        self.sort_menu.pack(side="right")
        self.cat_menu = ctk.CTkOptionMenu(inner, values=["All categories"], width=140, height=36,
                                          corner_radius=10, fg_color=HOVER, button_color=BORDER,
                                          button_hover_color=HOVER, text_color=TEXT, command=refresh)
        self.cat_menu.pack(side="right", padx=8)
        self.prio_filter = ctk.CTkSegmentedButton(inner, values=["All", "High", "Medium", "Low"], height=36,
                                                  selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
                                                  command=refresh)
        self.prio_filter.set("All")
        self.prio_filter.pack(side="right")

    # ---------- data actions ----------
    def save_tasks(self):
        self.storage.save(self.tasks)
        self.refresh()

    def open_dialog(self, task=None):
        cats = sorted(set(CATEGORIES) | {t.get("category", "Other") for t in self.tasks})
        TaskDialog(self.app, task, cats, self.on_dialog_save)

    def on_dialog_save(self, task, data):
        if task is None:
            data["id"] = uuid.uuid4().hex
            data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.tasks.append(data)
            self.toast("Task added  ✓")
        else:
            task.update(data)
            self.toast("Task updated  ✓", "info")
        self.save_tasks()

    def toggle_done(self, task):
        if is_done(task):
            task["status"] = "Pending"
            self.toast("Marked as pending", "info")
        else:
            task["status"] = "Completed"
            self.toast("Nice work! Task completed  ✓")
        self.save_tasks()

    def delete_task(self, task):
        if messagebox.askyesno("Delete task", f"Delete '{task['title']}'?\nThis cannot be undone."):
            self.tasks.remove(task)
            self.toast("Task deleted", "danger")
            self.save_tasks()

    # ---------- filtering ----------
    def in_view(self, t, view):
        d = parse_date(t.get("due_date"))
        today = date.today()
        if view == "Today":
            return d == today and not is_done(t)
        if view == "Upcoming":
            return bool(d and d > today and not is_done(t))
        if view == "Overdue":
            return is_overdue(t)
        if view == "Completed":
            return is_done(t)
        return True

    def matches(self, t):
        if not self.in_view(t, self.view):
            return False
        q = self.search.get().strip().lower()
        if q and q not in (t["title"] + " " + t.get("description", "") + " " + t.get("category", "")).lower():
            return False
        p = self.prio_filter.get()
        if p in PRIORITIES and t["priority"] != p:
            return False
        c = self.cat_menu.get()
        if c != "All categories" and t.get("category") != c:
            return False
        return True

    def sort_key(self, t):
        mode = self.sort_menu.get()
        if mode == "Sort: Priority":
            return (is_done(t), PRIORITY_RANK.get(t["priority"], 9))
        if mode == "Sort: Title":
            return (is_done(t), t["title"].lower())
        if mode == "Sort: Newest":
            try:
                stamp = datetime.strptime(t.get("created_at", ""), "%Y-%m-%d %H:%M").timestamp()
            except ValueError:
                stamp = 0
            return (is_done(t), -stamp)   # minus = newest first
        d = parse_date(t.get("due_date"))
        return (is_done(t), d is None, d or date.max, PRIORITY_RANK.get(t["priority"], 9))

    # ---------- drawing ----------
    def refresh(self):
        # sidebar highlight + counts
        for name, btn in self.nav_buttons.items():
            active = name == self.view
            btn.configure(fg_color=ACCENT_SOFT if active else "transparent",
                          text_color=ACCENT_TEXT if active else TEXT, hover_color=HOVER)
            n = sum(self.in_view(t, name) for t in self.tasks)
            alert = name == "Overdue" and n > 0
            self.nav_counts[name].configure(text=str(n),
                                            fg_color=CHIP_RED[0] if alert else (ACCENT if active else HOVER),
                                            text_color=CHIP_RED[1] if alert else ("white" if active else MUTED))

        # stats + progress
        total = len(self.tasks)
        done = sum(is_done(t) for t in self.tasks)
        self.stat_labels["total"].configure(text=str(total))
        self.stat_labels["pending"].configure(text=str(total - done))
        self.stat_labels["completed"].configure(text=str(done))
        self.stat_labels["overdue"].configure(text=str(sum(is_overdue(t) for t in self.tasks)))
        pct = done / total if total else 0
        self.progress.set(pct)
        self.progress_text.configure(text=f"{done} of {total} tasks done  ·  {round(pct * 100)}%")

        # category filter options
        cats = sorted({t.get("category", "Other") for t in self.tasks})
        self.cat_menu.configure(values=["All categories"] + cats)
        if self.cat_menu.get() not in ["All categories"] + cats:
            self.cat_menu.set("All categories")

        # task cards
        self.list_title.configure(text=self.view)
        for w in self.list_frame.winfo_children():
            w.destroy()
        visible = sorted((t for t in self.tasks if self.matches(t)), key=self.sort_key)
        if not visible:
            self.draw_empty()
        for t in visible:
            self.draw_card(t)

    def draw_empty(self):
        box = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        box.pack(pady=60)
        ctk.CTkLabel(box, text="✓", width=70, height=70, corner_radius=35, fg_color=ACCENT_SOFT,
                     text_color=ACCENT_TEXT, font=ctk.CTkFont(size=30, weight="bold")).pack()
        msg = "No tasks yet" if not self.tasks else "Nothing here"
        sub = ("Add your first task to get started." if not self.tasks
               else "No tasks match this list or your filters.")
        ctk.CTkLabel(box, text=msg, text_color=TEXT, font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 2))
        ctk.CTkLabel(box, text=sub, text_color=MUTED).pack()
        ctk.CTkButton(box, text="+  New Task", width=140, height=38, corner_radius=10, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self.open_dialog).pack(pady=16)

    def due_chip(self, t):
        d = parse_date(t.get("due_date"))
        if d is None:
            return "No due date", CHIP_GRAY
        if is_done(t):
            return nice_date(d), CHIP_GRAY
        days = (d - date.today()).days
        if days < 0:
            return f"Overdue by {-days} day{'s' if days < -1 else ''}", CHIP_RED
        if days == 0:
            return "Due today", CHIP_AMBER
        if days == 1:
            return "Due tomorrow", CHIP_BLUE
        return f"Due {d.strftime('%d %b')}", CHIP_BLUE

    def draw_card(self, t):
        done = is_done(t)
        card = ctk.CTkFrame(self.list_frame, corner_radius=14, fg_color=CARD,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=(0, 6), pady=5)

        strip_color = ("#c9ccd3", "#4a4d55") if done else PRIORITY_COLORS.get(t["priority"], ACCENT)
        ctk.CTkFrame(card, width=5, height=20, corner_radius=3, fg_color=strip_color).pack(
            side="left", fill="y", padx=(10, 0), pady=12)

        cb = ctk.CTkCheckBox(card, text="", width=28, checkbox_width=24, checkbox_height=24,
                             corner_radius=12, border_width=2, fg_color=SUCCESS, hover_color="#15803d",
                             border_color=("#b9bdc6", "#5a5e67"), command=lambda: self.toggle_done(t))
        if done:
            cb.select()
        cb.pack(side="left", padx=(14, 4))

        # right side buttons
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(side="right", padx=12)
        ctk.CTkButton(actions, text="✎  Edit", width=74, height=32, corner_radius=8, fg_color=HOVER,
                      text_color=TEXT, hover_color=BORDER, command=lambda: self.open_dialog(t)).pack(side="left")
        ctk.CTkButton(actions, text="✕", width=34, height=32, corner_radius=8, fg_color="transparent",
                      text_color=MUTED, hover_color=CHIP_RED[0],
                      command=lambda: self.delete_task(t)).pack(side="left", padx=(6, 0))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, pady=12)
        title = ctk.CTkLabel(body, text=t["title"], anchor="w", justify="left",
                             font=self.f_title_done if done else self.f_title,
                             text_color=MUTED if done else TEXT)
        title.pack(fill="x")
        widgets = [card, body, title]
        if t.get("description"):
            desc = ctk.CTkLabel(body, text=t["description"], anchor="w", justify="left",
                                text_color=MUTED, font=self.f_small, wraplength=520)
            desc.pack(fill="x")
            widgets.append(desc)

        chips = ctk.CTkFrame(body, fg_color="transparent")
        chips.pack(fill="x", pady=(8, 0))
        due_text, due_style = self.due_chip(t)
        chip(chips, t["priority"], CHIP_GRAY if done else PRIORITY_CHIP.get(t["priority"], CHIP_GRAY)).pack(side="left")
        chip(chips, t.get("category", "Other"), CHIP_PURPLE).pack(side="left", padx=6)
        chip(chips, due_text, due_style).pack(side="left")
        if t["status"] == "In Progress":
            chip(chips, "In progress", CHIP_BLUE).pack(side="left", padx=6)

        # double-click anywhere on the card to edit
        for w in widgets:
            w.bind("<Double-Button-1>", lambda e: self.open_dialog(t))


# ------------------------------------------------------------------ app shell
class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=APP_BG)
        self.title("TM · Personal Task Manager")
        apply_icon(self)
        self.geometry("1240x780")
        self.minsize(1100, 700)
        self.current = None
        self.show_login()

    def switch(self, frame):
        if self.current is not None:
            self.current.destroy()
        self.current = frame
        frame.pack(fill="both", expand=True)

    def show_login(self):
        self.unbind("<Control-n>")
        self.switch(LoginFrame(self, AuthManager(CONFIG_FILE), self.show_tasks))

    def show_tasks(self, username):
        self.switch(TaskManagerFrame(self, username, self.show_login, self.toast))

    def toast(self, text, kind="success"):
        """Small message at the bottom-right that disappears by itself."""
        color = {"success": SUCCESS, "info": ACCENT, "danger": DANGER}[kind]
        box = ctk.CTkFrame(self, corner_radius=12, fg_color=color)
        ctk.CTkLabel(box, text=text, text_color="white",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(padx=20, pady=11)
        box.place(relx=0.985, rely=0.97, anchor="se")
        box.lift()
        self.after(2200, box.destroy)


if __name__ == "__main__":
    # On Windows, give the app its own taskbar identity so the TM icon shows
    # in the taskbar instead of the Python icon.
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Haseema.TaskManager")
        except Exception:
            pass
    App().mainloop()
