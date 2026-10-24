"""
Personal Task Manager - Python Desktop Application
--------------------------------------------------
Tech: Python 3 + Tkinter (standard library only, no installs needed)

Features
  * Login using credentials stored in a local config file (config.ini)
    - first run asks you to create an account
    - password stored as a salted SHA-256 hash (never plain text)
  * CRUD: add, view, update, delete tasks
  * Task fields: title, description, priority, due date, category, status
  * Search by text + filter by status, priority and due date
  * Click column headings to sort
  * File-based storage in tasks.txt (one JSON record per line)
  * Overdue tasks shown in red, completed tasks in grey

Run:  python task_manager.py
"""

import configparser
import hashlib
import json
import os
import secrets
import tkinter as tk
import uuid
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

# ------------------------------------------------------------------ settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(BASE_DIR, "tasks.txt")
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")

DATE_FMT = "%Y-%m-%d"
PRIORITIES = ["High", "Medium", "Low"]
STATUSES = ["Pending", "In Progress", "Completed"]
CATEGORIES = ["Work", "Personal", "Study", "Shopping", "Other"]
DUE_FILTERS = ["All", "Overdue", "Today", "Next 7 Days", "No Due Date"]
PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}


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
                    continue  # skip a corrupted line instead of crashing
        return tasks

    def save(self, tasks):
        # write to a temp file first, then replace -> no data loss on crash
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
class LoginFrame(ttk.Frame):
    def __init__(self, master, auth, on_success):
        super().__init__(master, padding=30)
        self.auth = auth
        self.on_success = on_success
        self.signup_mode = not auth.has_user()

        title = "Create Account" if self.signup_mode else "Login"
        ttk.Label(self, text="Personal Task Manager",
                  font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 5))
        ttk.Label(self, text=title, font=("Segoe UI", 11)).grid(row=1, column=0, columnspan=2, pady=(0, 15))

        ttk.Label(self, text="Username").grid(row=2, column=0, sticky="w", pady=4)
        self.user_var = tk.StringVar()
        user_entry = ttk.Entry(self, textvariable=self.user_var, width=28)
        user_entry.grid(row=2, column=1, pady=4)

        ttk.Label(self, text="Password").grid(row=3, column=0, sticky="w", pady=4)
        self.pass_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.pass_var, show="*", width=28).grid(row=3, column=1, pady=4)

        row = 4
        if self.signup_mode:
            ttk.Label(self, text="Confirm").grid(row=4, column=0, sticky="w", pady=4)
            self.confirm_var = tk.StringVar()
            ttk.Entry(self, textvariable=self.confirm_var, show="*", width=28).grid(row=4, column=1, pady=4)
            row = 5

        ttk.Button(self, text=title, command=self.submit).grid(
            row=row, column=0, columnspan=2, pady=(15, 0), sticky="ew")

        master.bind("<Return>", lambda e: self.submit())
        user_entry.focus()

    def submit(self):
        username = self.user_var.get().strip()
        password = self.pass_var.get()
        if not username or not password:
            messagebox.showwarning("Missing", "Enter username and password.")
            return

        if self.signup_mode:
            if len(password) < 4:
                messagebox.showwarning("Weak password", "Use at least 4 characters.")
                return
            if password != self.confirm_var.get():
                messagebox.showerror("Mismatch", "Passwords do not match.")
                return
            self.auth.create_user(username, password)
            messagebox.showinfo("Done", "Account created. Welcome!")
            self.finish(username)
        elif self.auth.verify(username, password):
            self.finish(username)
        else:
            messagebox.showerror("Login failed", "Invalid username or password.")
            self.pass_var.set("")

    def finish(self, username):
        self.master.unbind("<Return>")
        self.on_success(username)


# ------------------------------------------------------------------ main app
class TaskManagerFrame(ttk.Frame):
    def __init__(self, master, username, on_logout):
        super().__init__(master, padding=10)
        self.username = username
        self.on_logout = on_logout
        self.storage = TaskStorage(TASKS_FILE)
        self.tasks = self.storage.load()
        self.selected_id = None
        self.sort_col, self.sort_reverse = "due_date", False

        self.build_header()
        self.build_form()
        self.build_filters()
        self.build_table()
        self.build_statusbar()
        self.refresh_table()

    # ---------- layout ----------
    def build_header(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="My Tasks", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(bar, text="Logout", command=self.on_logout).pack(side="right")
        ttk.Label(bar, text=f"Logged in as {self.username}  ").pack(side="right")

    def build_form(self):
        form = ttk.LabelFrame(self, text="Task Details", padding=10)
        form.pack(fill="x")

        self.title_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.priority_var = tk.StringVar(value="Medium")
        self.due_var = tk.StringVar()
        self.category_var = tk.StringVar(value="Personal")
        self.status_var = tk.StringVar(value="Pending")

        ttk.Label(form, text="Title *").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.title_var, width=40).grid(row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=3)

        ttk.Label(form, text="Description").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.desc_var, width=40).grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=3)

        ttk.Label(form, text="Priority").grid(row=2, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.priority_var, values=PRIORITIES,
                     state="readonly", width=12).grid(row=2, column=1, sticky="w", padx=5, pady=3)

        ttk.Label(form, text="Due (YYYY-MM-DD)").grid(row=2, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.due_var, width=14).grid(row=2, column=3, sticky="w", padx=5, pady=3)

        ttk.Label(form, text="Category").grid(row=3, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.category_var, values=CATEGORIES,
                     width=12).grid(row=3, column=1, sticky="w", padx=5, pady=3)  # editable: type new ones

        ttk.Label(form, text="Status").grid(row=3, column=2, sticky="w")
        ttk.Combobox(form, textvariable=self.status_var, values=STATUSES,
                     state="readonly", width=12).grid(row=3, column=3, sticky="w", padx=5, pady=3)

        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        btns = ttk.Frame(form)
        btns.grid(row=4, column=0, columnspan=4, pady=(8, 0), sticky="w")
        ttk.Button(btns, text="Add Task", command=self.add_task).pack(side="left", padx=3)
        ttk.Button(btns, text="Update", command=self.update_task).pack(side="left", padx=3)
        ttk.Button(btns, text="Delete", command=self.delete_task).pack(side="left", padx=3)
        ttk.Button(btns, text="Mark Completed", command=self.mark_completed).pack(side="left", padx=3)
        ttk.Button(btns, text="Clear Form", command=self.clear_form).pack(side="left", padx=3)

    def build_filters(self):
        bar = ttk.LabelFrame(self, text="Search & Filter", padding=8)
        bar.pack(fill="x", pady=8)

        self.search_var = tk.StringVar()
        self.f_status = tk.StringVar(value="All")
        self.f_priority = tk.StringVar(value="All")
        self.f_due = tk.StringVar(value="All")

        ttk.Label(bar, text="Search").pack(side="left")
        ttk.Entry(bar, textvariable=self.search_var, width=22).pack(side="left", padx=(3, 10))
        ttk.Label(bar, text="Status").pack(side="left")
        ttk.Combobox(bar, textvariable=self.f_status, values=["All"] + STATUSES,
                     state="readonly", width=11).pack(side="left", padx=(3, 10))
        ttk.Label(bar, text="Priority").pack(side="left")
        ttk.Combobox(bar, textvariable=self.f_priority, values=["All"] + PRIORITIES,
                     state="readonly", width=8).pack(side="left", padx=(3, 10))
        ttk.Label(bar, text="Due").pack(side="left")
        ttk.Combobox(bar, textvariable=self.f_due, values=DUE_FILTERS,
                     state="readonly", width=12).pack(side="left", padx=(3, 10))
        ttk.Button(bar, text="Reset", command=self.reset_filters).pack(side="left")

        # live filtering: refresh whenever any filter changes
        for v in (self.search_var, self.f_status, self.f_priority, self.f_due):
            v.trace_add("write", lambda *a: self.refresh_table())

    def build_table(self):
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)

        cols = ("title", "priority", "due_date", "category", "status")
        heads = {"title": "Title", "priority": "Priority", "due_date": "Due Date",
                 "category": "Category", "status": "Status"}
        widths = {"title": 280, "priority": 80, "due_date": 100, "category": 100, "status": 100}

        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=heads[c], command=lambda col=c: self.sort_by(col))
            self.tree.column(c, width=widths[c], anchor="w" if c == "title" else "center")

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.tag_configure("overdue", foreground="#c0392b")
        self.tree.tag_configure("completed", foreground="#999999")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

    def build_statusbar(self):
        self.status_label = ttk.Label(self, anchor="w")
        self.status_label.pack(fill="x", pady=(6, 0))

    # ---------- form helpers ----------
    def read_form(self):
        title = self.title_var.get().strip()
        due = self.due_var.get().strip()
        if not title:
            messagebox.showwarning("Missing title", "Title is required.")
            return None
        if due and parse_date(due) is None:
            messagebox.showerror("Bad date", "Use date format YYYY-MM-DD, e.g. 2026-11-05.")
            return None
        return {
            "title": title,
            "description": self.desc_var.get().strip(),
            "priority": self.priority_var.get(),
            "due_date": due,
            "category": self.category_var.get().strip() or "Other",
            "status": self.status_var.get(),
        }

    def clear_form(self):
        self.selected_id = None
        self.title_var.set("")
        self.desc_var.set("")
        self.priority_var.set("Medium")
        self.due_var.set("")
        self.category_var.set("Personal")
        self.status_var.set("Pending")
        self.tree.selection_remove(self.tree.selection())

    def find_task(self, task_id):
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def persist(self):
        self.storage.save(self.tasks)
        self.refresh_table()

    # ---------- CRUD ----------
    def add_task(self):
        data = self.read_form()
        if data is None:
            return
        data["id"] = uuid.uuid4().hex
        data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.tasks.append(data)
        self.persist()
        self.clear_form()

    def update_task(self):
        if not self.selected_id:
            messagebox.showinfo("Select a task", "Click a task in the list first.")
            return
        data = self.read_form()
        if data is None:
            return
        task = self.find_task(self.selected_id)
        if task:
            task.update(data)
            self.persist()
            self.clear_form()

    def delete_task(self):
        if not self.selected_id:
            messagebox.showinfo("Select a task", "Click a task in the list first.")
            return
        task = self.find_task(self.selected_id)
        if task and messagebox.askyesno("Delete", f"Delete '{task['title']}'?"):
            self.tasks.remove(task)
            self.persist()
            self.clear_form()

    def mark_completed(self):
        if not self.selected_id:
            messagebox.showinfo("Select a task", "Click a task in the list first.")
            return
        task = self.find_task(self.selected_id)
        if task:
            task["status"] = "Completed"
            self.persist()
            self.clear_form()

    def on_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        task = self.find_task(sel[0])
        if not task:
            return
        self.selected_id = task["id"]
        self.title_var.set(task["title"])
        self.desc_var.set(task.get("description", ""))
        self.priority_var.set(task["priority"])
        self.due_var.set(task.get("due_date", ""))
        self.category_var.set(task.get("category", ""))
        self.status_var.set(task["status"])

    # ---------- filter / search / sort ----------
    def reset_filters(self):
        self.search_var.set("")
        self.f_status.set("All")
        self.f_priority.set("All")
        self.f_due.set("All")

    def matches(self, t):
        q = self.search_var.get().strip().lower()
        if q and q not in (t["title"] + " " + t.get("description", "") + " " + t.get("category", "")).lower():
            return False
        if self.f_status.get() != "All" and t["status"] != self.f_status.get():
            return False
        if self.f_priority.get() != "All" and t["priority"] != self.f_priority.get():
            return False

        mode = self.f_due.get()
        if mode == "All":
            return True
        d = parse_date(t.get("due_date"))
        today = date.today()
        if mode == "No Due Date":
            return d is None
        if d is None:
            return False
        if mode == "Overdue":
            return d < today and t["status"] != "Completed"
        if mode == "Today":
            return d == today
        if mode == "Next 7 Days":
            return today <= d <= today + timedelta(days=7)
        return True

    def sort_by(self, col):
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col, self.sort_reverse = col, False
        self.refresh_table()

    def sort_key(self, t):
        if self.sort_col == "due_date":
            d = parse_date(t.get("due_date"))
            return (d is None, d or date.max)  # tasks with no date go last
        if self.sort_col == "priority":
            return PRIORITY_RANK.get(t["priority"], 9)
        if self.sort_col == "status":
            return STATUSES.index(t["status"]) if t["status"] in STATUSES else 9
        return str(t.get(self.sort_col, "")).lower()

    def refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        visible = sorted((t for t in self.tasks if self.matches(t)),
                         key=self.sort_key, reverse=self.sort_reverse)
        today = date.today()
        for t in visible:
            d = parse_date(t.get("due_date"))
            tag = ()
            if t["status"] == "Completed":
                tag = ("completed",)
            elif d and d < today:
                tag = ("overdue",)
            self.tree.insert("", "end", iid=t["id"], tags=tag, values=(
                t["title"], t["priority"], t.get("due_date") or "-",
                t.get("category", ""), t["status"]))

        done = sum(t["status"] == "Completed" for t in self.tasks)
        overdue = sum(1 for t in self.tasks if t["status"] != "Completed"
                      and parse_date(t.get("due_date")) and parse_date(t["due_date"]) < today)
        self.status_label.config(text=f"Showing {len(visible)} of {len(self.tasks)} tasks   |   "
                                      f"Completed: {done}   |   Overdue: {overdue}")


# ------------------------------------------------------------------ app shell
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Personal Task Manager")
        self.geometry("820x640")
        self.minsize(720, 520)
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Treeview", rowheight=26)
        self.auth = AuthManager(CONFIG_FILE)
        self.current = None
        self.show_login()

    def switch(self, frame):
        if self.current is not None:
            self.current.destroy()
        self.current = frame
        frame.pack(fill="both", expand=True)

    def show_login(self):
        self.auth = AuthManager(CONFIG_FILE)  # reload in case account was just created
        self.switch(LoginFrame(self, self.auth, self.show_tasks))

    def show_tasks(self, username):
        self.switch(TaskManagerFrame(self, username, self.show_login))


if __name__ == "__main__":
    App().mainloop()
