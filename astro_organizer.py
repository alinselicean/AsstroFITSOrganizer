import ctypes
import hashlib
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

if sys.platform == "win32":
    import winreg

if getattr(sys, "frozen", False):
    # Running as compiled .exe -> keep config, DB, and log next to the executable
    APP_DIR = Path(sys.executable).resolve().parent
else:
    # Running as .py script
    APP_DIR = Path(__file__).resolve().parent

CONFIG_FILE = APP_DIR / "config.json"

VALID_THEMES = ("System", "Dark", "Light")


def normalize_path(path_str: str) -> str:
    """Normalizes path separators to match the host OS ('\\' on Windows, '/' on POSIX)."""
    cleaned = path_str.strip()
    return os.path.normpath(cleaned) if cleaned else ""


def detect_system_theme() -> str:
    """Detects OS light/dark preference ('Dark' or 'Light') using stdlib only."""
    if sys.platform == "win32":
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "Light" if int(val) == 1 else "Dark"
        except Exception:
            return "Light"
    elif sys.platform == "darwin":
        try:
            res = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if "Dark" in res.stdout:
                return "Dark"
        except Exception:
            pass
    return "Light"


def apply_windows_titlebar_theme(window: tk.Misc, is_dark: bool):
    """Applies immersive dark/light title bar on Windows 10/11 when supported."""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        value = ctypes.c_int(1 if is_dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 11 / 10 20H1+), fallback 19
        for attr in (20, 19):
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            )
            if res == 0:
                break
    except Exception:
        pass


def get_theme_palette(theme_setting: str) -> dict:
    """Resolves 'System', 'Dark', or 'Light' into a concrete UI color palette."""
    resolved = detect_system_theme() if theme_setting == "System" else theme_setting
    if resolved == "Dark":
        return {
            "mode": "Dark",
            "bg": "#1e1e1e",
            "panel_bg": "#252526",
            "field_bg": "#2d2d30",
            "btn_bg": "#333337",
            "btn_active": "#3e3e42",
            "fg": "#e6e6e6",
            "muted_fg": "#9aa0a6",
            "border": "#3f3f46",
            "select_bg": "#264f78",
            "select_fg": "#ffffff",
            "tree_bg": "#1b1b1c",
            "heading_bg": "#2d2d30",
            "dup_bg": "#4a1f24",
            "dup_fg": "#ffd6d6",
            "folder_bg": "#1e3246",
            "folder_fg": "#d6ebff",
            "text_bg": "#1b1b1c",
            "text_fg": "#e6e6e6",
        }
    return {
        "mode": "Light",
        "bg": "#f0f0f0",
        "panel_bg": "#f0f0f0",
        "field_bg": "#ffffff",
        "btn_bg": "#e1e1e1",
        "btn_active": "#e5f1fb",
        "fg": "#000000",
        "muted_fg": "#555555",
        "border": "#adadad",
        "select_bg": "#0078d7",
        "select_fg": "#ffffff",
        "tree_bg": "#ffffff",
        "heading_bg": "#f0f0f0",
        "dup_bg": "#ffe6e6",
        "dup_fg": "#000000",
        "folder_bg": "#eef6ff",
        "folder_fg": "#000000",
        "text_bg": "#ffffff",
        "text_fg": "#000000",
    }


def apply_ttk_theme(root: tk.Tk, theme_setting: str) -> dict:
    """Configures ttk styles and global tk widget colors for Light or Dark mode."""
    palette = get_theme_palette(theme_setting)
    is_dark = palette["mode"] == "Dark"
    style = ttk.Style(root)

    if is_dark:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    else:
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

    root.configure(bg=palette["bg"])
    root.option_add("*TCombobox*Listbox.background", palette["field_bg"])
    root.option_add("*TCombobox*Listbox.foreground", palette["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", palette["select_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", palette["select_fg"])

    if is_dark:
        style.configure(".", background=palette["bg"], foreground=palette["fg"], bordercolor=palette["border"])
        style.configure("TFrame", background=palette["bg"])
        style.configure("TLabelframe", background=palette["bg"], bordercolor=palette["border"])
        style.configure("TLabelframe.Label", background=palette["bg"], foreground=palette["fg"])
        style.configure("TLabel", background=palette["bg"], foreground=palette["fg"])
        style.configure(
            "TButton",
            background=palette["btn_bg"],
            foreground=palette["fg"],
            bordercolor=palette["border"],
            lightcolor=palette["btn_bg"],
            darkcolor=palette["btn_bg"],
            padding=(8, 3),
        )
        style.map(
            "TButton",
            background=[("disabled", "#252526"), ("pressed", "#007acc"), ("active", palette["btn_active"])],
            foreground=[("disabled", "#6e6e6e"), ("active", "#ffffff")],
        )
        style.configure(
            "TEntry",
            fieldbackground=palette["field_bg"],
            foreground=palette["fg"],
            insertcolor=palette["fg"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", "#252526")],
            foreground=[("disabled", "#6e6e6e")],
        )
        style.configure(
            "TCombobox",
            fieldbackground=palette["field_bg"],
            background=palette["btn_bg"],
            foreground=palette["fg"],
            arrowcolor=palette["fg"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette["field_bg"]), ("disabled", "#252526")],
            foreground=[("readonly", palette["fg"]), ("disabled", "#6e6e6e")],
            background=[("active", palette["btn_active"])],
        )
        style.configure(
            "TCheckbutton",
            background=palette["bg"],
            foreground=palette["fg"],
            indicatorcolor=palette["field_bg"],
            indicatorrelief="flat",
        )
        style.map(
            "TCheckbutton",
            background=[("active", palette["bg"])],
            foreground=[("disabled", "#6e6e6e")],
            indicatorcolor=[("selected", "#007acc"), ("active", palette["btn_active"])],
        )
        style.configure(
            "Treeview",
            background=palette["tree_bg"],
            fieldbackground=palette["tree_bg"],
            foreground=palette["fg"],
            bordercolor=palette["border"],
            rowheight=22,
        )
        style.map(
            "Treeview",
            background=[("selected", palette["select_bg"])],
            foreground=[("selected", palette["select_fg"])],
        )
        style.configure(
            "Treeview.Heading",
            background=palette["heading_bg"],
            foreground=palette["fg"],
            bordercolor=palette["border"],
            relief="flat",
        )
        style.map(
            "Treeview.Heading",
            background=[("active", palette["btn_active"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=palette["btn_bg"],
            troughcolor=palette["panel_bg"],
            bordercolor=palette["border"],
            arrowcolor=palette["fg"],
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=palette["btn_bg"],
            troughcolor=palette["panel_bg"],
            bordercolor=palette["border"],
            arrowcolor=palette["fg"],
        )
    else:
        style.configure(
            "Treeview",
            background=palette["tree_bg"],
            fieldbackground=palette["tree_bg"],
            foreground=palette["fg"],
            rowheight=22,
        )
        style.map(
            "Treeview",
            background=[("selected", palette["select_bg"])],
            foreground=[("selected", palette["select_fg"])],
        )

    apply_windows_titlebar_theme(root, is_dark)
    return palette


DEFAULT_CONFIG = {
    "default_scan_dir": normalize_path(r"D:\Astrophoto\Sessions"),
    "quarantine_dir": normalize_path(r"D:\Astrophoto\_Quarantine_Duplicates"),
    "db_path": normalize_path(str(APP_DIR / "astro_archive.db")),
    "log_path": normalize_path(str(APP_DIR / "astro_organizer.log")),
    "max_table_rows": 2000,
    "theme": "System",
    "last_scanned_dir": "",  # Internal hidden setting; not editable via Settings UI
}

PATH_CONFIG_KEYS = (
    "default_scan_dir",
    "quarantine_dir",
    "db_path",
    "log_path",
    "last_scanned_dir",
)


class ConfigManager:
    """Handles loading and saving JSON configuration settings with OS-normalized paths."""

    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except Exception:
                pass

        for key in PATH_CONFIG_KEYS:
            if key in self.data and isinstance(self.data[key], str):
                self.data[key] = normalize_path(self.data[key])

        if self.data.get("theme") not in VALID_THEMES:
            self.data["theme"] = "System"

        if not self.config_path.exists():
            self.save()
        return self.data

    def save(self, new_data: dict | None = None):
        if new_data is not None:
            self.data.update(new_data)
        for key in PATH_CONFIG_KEYS:
            if key in self.data and isinstance(self.data[key], str):
                self.data[key] = normalize_path(self.data[key])
        if self.data.get("theme") not in VALID_THEMES:
            self.data["theme"] = "System"
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)


class AuditLogger:
    """Writes timestamped audit records for scans, moves, and permanent deletions."""

    def __init__(self, log_path: str):
        self.log_path = Path(normalize_path(log_path))

    def set_path(self, log_path: str):
        self.log_path = Path(normalize_path(log_path))

    def log_event(self, action: str, summary: str, details: list[str] | None = None):
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            lines = [f"[{timestamp}] [{action}] {summary}"]
            if details:
                for item in details:
                    lines.append(f"    {item}")
            lines.append("")
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass


def parse_float_header(val) -> float | None:
    """Safely extracts a numeric float value from a FITS header card."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        cleaned = str(val).strip().rstrip("mMsS").strip()
        return float(cleaned)
    except ValueError:
        return None


def read_fits_header_fast(file_path: Path) -> dict:
    """Reads only the 2880-byte ASCII FITS header blocks up to the END keyword."""
    header = {}
    with open(file_path, "rb") as f:
        while True:
            block = f.read(2880)
            if not block or len(block) < 80:
                break
            for i in range(0, len(block), 80):
                card = block[i:i + 80].decode("ascii", errors="ignore")
                key = card[:8].strip()
                if key == "END":
                    return header
                if card[8:10] != "= ":
                    continue
                rest = card[10:]
                if rest.lstrip().startswith("'"):
                    s = rest.lstrip()[1:]
                    idx = 0
                    chars = []
                    while idx < len(s):
                        if s[idx] == "'":
                            if idx + 1 < len(s) and s[idx + 1] == "'":
                                chars.append("'")
                                idx += 2
                                continue
                            break
                        chars.append(s[idx])
                        idx += 1
                    header[key] = "".join(chars).strip()
                else:
                    val_str = rest.split("/", 1)[0].strip()
                    if val_str == "T":
                        header[key] = True
                    elif val_str == "F":
                        header[key] = False
                    else:
                        try:
                            header[key] = (
                                float(val_str)
                                if ("." in val_str or "E" in val_str.upper())
                                else int(val_str)
                            )
                        except ValueError:
                            header[key] = val_str
    return header


def compute_file_hash(file_path: str, size_bytes: int, full: bool = False) -> str:
    """
    Computes a blake2b content fingerprint:
    - full=False: fast sample (first 64KB + middle 64KB + last 64KB)
    - full=True: full file hash
    """
    h = hashlib.blake2b(digest_size=16)
    chunk = 65536
    try:
        with open(file_path, "rb") as f:
            if full or size_bytes <= chunk * 4:
                while True:
                    buf = f.read(262144)
                    if not buf:
                        break
                    h.update(buf)
            else:
                h.update(f.read(chunk))
                f.seek(size_bytes // 2)
                h.update(f.read(chunk))
                f.seek(max(0, size_bytes - chunk))
                h.update(f.read(chunk))
        return h.hexdigest()
    except Exception:
        return f"ERR_{file_path}"


def get_path_size_and_count(target: Path) -> tuple[int, int]:
    """Returns (total_size_bytes, total_file_count) for a file or recursively for a directory."""
    if not target.exists():
        return 0, 0
    if target.is_file():
        try:
            return target.stat().st_size, 1
        except Exception:
            return 0, 1
    total_bytes = 0
    total_files = 0
    stack = [str(target)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total_files += 1
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                    except Exception:
                        pass
        except Exception:
            pass
    return total_bytes, total_files


def format_size(size_bytes: int) -> str:
    """Formats a byte count into human-readable MB or GB."""
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB ({mb:,.1f} MB)"
    return f"{mb:,.1f} MB"


class SettingsDialog(tk.Toplevel):
    """Modal dialog for configuring visible application paths, display limits, and theme."""

    def __init__(self, parent, config_manager: ConfigManager, on_save_callback):
        super().__init__(parent)
        self.title("Configuration Settings")
        self.geometry("680x325")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.config_manager = config_manager
        self.on_save_callback = on_save_callback

        cfg = self.config_manager.data
        palette = get_theme_palette(cfg.get("theme", "System"))
        self.configure(bg=palette["bg"])
        apply_windows_titlebar_theme(self, palette["mode"] == "Dark")

        self.scan_dir_var = tk.StringVar(value=normalize_path(cfg.get("default_scan_dir", "")))
        self.quarantine_var = tk.StringVar(value=normalize_path(cfg.get("quarantine_dir", "")))
        self.db_path_var = tk.StringVar(value=normalize_path(cfg.get("db_path", "")))
        self.log_path_var = tk.StringVar(value=normalize_path(cfg.get("log_path", "")))
        self.max_rows_var = tk.StringVar(value=str(cfg.get("max_table_rows", 2000)))
        self.theme_var = tk.StringVar(value=cfg.get("theme", "System"))

        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Default Scan Folder:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.scan_dir_var, width=56).grid(row=0, column=1, padx=8, pady=5)
        ttk.Button(frame, text="Browse...", command=self._browse_scan_dir).grid(row=0, column=2, pady=5)

        ttk.Label(frame, text="Quarantine Folder:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.quarantine_var, width=56).grid(row=1, column=1, padx=8, pady=5)
        ttk.Button(frame, text="Browse...", command=self._browse_quarantine_dir).grid(row=1, column=2, pady=5)

        ttk.Label(frame, text="SQLite Database File:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.db_path_var, width=56).grid(row=2, column=1, padx=8, pady=5)
        ttk.Button(frame, text="Browse...", command=self._browse_db_file).grid(row=2, column=2, pady=5)

        ttk.Label(frame, text="Audit Log File:").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.log_path_var, width=56).grid(row=3, column=1, padx=8, pady=5)
        ttk.Button(frame, text="Browse...", command=self._browse_log_file).grid(row=3, column=2, pady=5)

        ttk.Label(frame, text="Max Displayed Rows:").grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.max_rows_var, width=15).grid(row=4, column=1, sticky=tk.W, padx=8, pady=5)

        ttk.Label(frame, text="Theme:").grid(row=5, column=0, sticky=tk.W, pady=5)
        theme_combo = ttk.Combobox(
            frame,
            textvariable=self.theme_var,
            values=list(VALID_THEMES),
            state="readonly",
            width=15,
        )
        theme_combo.grid(row=5, column=1, sticky=tk.W, padx=8, pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=3, sticky=tk.E, pady=(18, 0))

        ttk.Button(btn_frame, text="Save Settings", command=self._save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT)

    def _browse_scan_dir(self):
        folder = filedialog.askdirectory(initialdir=self.scan_dir_var.get(), parent=self)
        if folder:
            self.scan_dir_var.set(normalize_path(folder))

    def _browse_quarantine_dir(self):
        folder = filedialog.askdirectory(initialdir=self.quarantine_var.get(), parent=self)
        if folder:
            self.quarantine_var.set(normalize_path(folder))

    def _browse_db_file(self):
        file_path = filedialog.asksaveasfilename(
            title="Select SQLite Database File",
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
            initialfile=Path(self.db_path_var.get()).name,
            parent=self,
        )
        if file_path:
            self.db_path_var.set(normalize_path(file_path))

    def _browse_log_file(self):
        file_path = filedialog.asksaveasfilename(
            title="Select Audit Log File",
            defaultextension=".log",
            filetypes=[("Log Files", "*.log *.txt"), ("All Files", "*.*")],
            initialfile=Path(self.log_path_var.get()).name,
            parent=self,
        )
        if file_path:
            self.log_path_var.set(normalize_path(file_path))

    def _save(self):
        try:
            max_rows = int(self.max_rows_var.get().strip())
            if max_rows < 100:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Value", "Max Displayed Rows must be an integer >= 100.", parent=self)
            return

        selected_theme = self.theme_var.get().strip()
        if selected_theme not in VALID_THEMES:
            selected_theme = "System"

        new_cfg = {
            "default_scan_dir": normalize_path(self.scan_dir_var.get()),
            "quarantine_dir": normalize_path(self.quarantine_var.get()),
            "db_path": normalize_path(self.db_path_var.get()),
            "log_path": normalize_path(self.log_path_var.get()),
            "max_table_rows": max_rows,
            "theme": selected_theme,
        }
        if not new_cfg["quarantine_dir"] or not new_cfg["db_path"] or not new_cfg["log_path"]:
            messagebox.showwarning("Missing Fields", "Quarantine, Database, and Log paths cannot be empty.", parent=self)
            return

        self.config_manager.save(new_cfg)
        self.on_save_callback()
        self.destroy()


class LogViewerDialog(tk.Toplevel):
    """Read-only viewer for inspecting the audit log inside the application."""

    def __init__(self, parent, log_path: Path, palette: dict):
        super().__init__(parent)
        self.title(f"Audit Log — {log_path}")
        self.geometry("920x520")
        self.transient(parent)
        self.log_path = log_path
        self.palette = palette

        self.configure(bg=palette["bg"])
        apply_windows_titlebar_theme(self, palette["mode"] == "Dark")

        self._build_ui()
        self._load_log()

    def _build_ui(self):
        top = ttk.Frame(self, padding=(10, 10, 10, 5))
        top.pack(fill=tk.X)

        ttk.Button(top, text="Refresh", command=self._load_log).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Clear Log File", command=self._clear_log).pack(side=tk.LEFT)
        ttk.Button(top, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        text_frame = ttk.Frame(self, padding=(10, 5, 10, 10))
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(
            text_frame,
            wrap="none",
            font=("Consolas", 9),
            state="disabled",
            bg=self.palette["text_bg"],
            fg=self.palette["text_fg"],
            insertbackground=self.palette["text_fg"],
            selectbackground=self.palette["select_bg"],
            selectforeground=self.palette["select_fg"],
            relief="flat",
        )
        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        hsb = ttk.Scrollbar(text_frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.text.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

    def _load_log(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        if self.log_path.exists():
            try:
                content = self.log_path.read_text(encoding="utf-8")
                self.text.insert(tk.END, content)
                self.text.see(tk.END)
            except Exception as e:
                self.text.insert(tk.END, f"Failed to read log file: {e}")
        else:
            self.text.insert(tk.END, "No audit log entries recorded yet.")
        self.text.configure(state="disabled")

    def _clear_log(self):
        if not self.log_path.exists():
            return
        if messagebox.askyesno("Clear Log", "Are you sure you want to clear the audit log file?", parent=self):
            self.log_path.write_text("", encoding="utf-8")
            self._load_log()


class AstroOrganizerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Astro FITS Organizer & Deduplicator")
        self.root.geometry("1300x735")

        self.config_manager = ConfigManager()
        self.logger = AuditLogger(self.config_manager.data["log_path"])
        self.palette = apply_ttk_theme(self.root, self.config_manager.data.get("theme", "System"))

        self.conn: sqlite3.Connection | None = None
        self._connect_db()

        self.scan_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.is_scanning = False
        self.scan_start_time = 0.0
        self.scan_root_active = ""
        self.sample_hash_cache = {}  # (path, size_bytes) -> short_blake2b

        self._build_ui()
        self.apply_theme()
        self._load_initial_db_state()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def apply_theme(self):
        """Applies the configured theme ('System', 'Dark', or 'Light') across all widgets."""
        theme_setting = self.config_manager.data.get("theme", "System")
        self.palette = apply_ttk_theme(self.root, theme_setting)

        if hasattr(self, "tree"):
            self.tree.tag_configure(
                "duplicate",
                background=self.palette["dup_bg"],
                foreground=self.palette["dup_fg"],
            )
            self.tree.tag_configure(
                "folder",
                background=self.palette["folder_bg"],
                foreground=self.palette["folder_fg"],
            )

        if hasattr(self, "_muted_labels"):
            for lbl in self._muted_labels:
                lbl.configure(foreground=self.palette["muted_fg"])

    def on_closing(self):
        """Cleanly stops any active background scan and closes SQLite (flushing WAL locks)."""
        self.stop_event.set()
        if self.conn is not None:
            try:
                self.conn.commit()
                self.conn.close()
            except Exception:
                pass
        self.root.destroy()

    def _get_startup_scan_dir(self) -> str:
        """Returns last_scanned_dir if set in config; otherwise falls back to default_scan_dir."""
        last_dir = normalize_path(self.config_manager.data.get("last_scanned_dir", ""))
        if last_dir:
            return last_dir
        return normalize_path(self.config_manager.data.get("default_scan_dir", ""))

    def _connect_db(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass

        db_file = Path(normalize_path(self.config_manager.data["db_path"]))
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_file))
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS frames (
                id INTEGER PRIMARY KEY,
                path TEXT,
                filename TEXT,
                size_bytes INTEGER,
                mtime REAL,
                size_mb REAL,
                imagetyp TEXT,
                object_name TEXT,
                date_obs TEXT,
                exptime REAL,
                focal_len REAL,
                filter_name TEXT,
                file_hash TEXT DEFAULT ''
            )
        """)

        existing_frame_cols = {row[1] for row in cur.execute("PRAGMA table_info(frames)").fetchall()}
        if "focal_len" not in existing_frame_cols:
            cur.execute("ALTER TABLE frames ADD COLUMN focal_len REAL")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY,
                path TEXT,
                folder_name TEXT,
                mod_date TEXT,
                file_count INTEGER DEFAULT 0
            )
        """)

        existing_folder_cols = {row[1] for row in cur.execute("PRAGMA table_info(folders)").fetchall()}
        if "file_count" not in existing_folder_cols:
            cur.execute("ALTER TABLE folders ADD COLUMN file_count INTEGER DEFAULT 0")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS hash_cache (
                path TEXT,
                size_bytes INTEGER,
                mtime REAL,
                file_hash TEXT,
                PRIMARY KEY (path, size_bytes, mtime)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_frames_path ON frames(path)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_frames_date ON frames(date_obs)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_frames_size ON frames(size_bytes)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_frames_focal ON frames(focal_len)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_folders_name ON folders(folder_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_folders_path ON folders(path)")
        self.conn.commit()

    def _build_ui(self):
        # --- SECTION 1: Source Folder, Scan Controls & Settings ---
        top_frame = ttk.Frame(self.root, padding=(10, 10, 10, 5))
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="Scan Folder:").pack(side=tk.LEFT, padx=(0, 5))
        self.folder_var = tk.StringVar(value=self._get_startup_scan_dir())
        ttk.Entry(top_frame, textvariable=self.folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(top_frame, text="Browse...", command=self.browse_folder).pack(side=tk.LEFT, padx=4)

        self.btn_scan = ttk.Button(top_frame, text="Scan Folder", command=self.start_scan)
        self.btn_scan.pack(side=tk.LEFT, padx=(6, 4))

        self.btn_stop = ttk.Button(top_frame, text="Stop", command=self.stop_scan, state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(top_frame, text="Settings...", command=self.open_settings).pack(side=tk.LEFT)

        # --- SECTION 2: Dedicated Filter Panel (optional criteria combined with AND) ---
        filter_frame = ttk.LabelFrame(
            self.root,
            text="Filter Criteria (all optional, combined with AND)",
            padding=10,
        )
        filter_frame.pack(fill=tk.X, padx=10, pady=5)

        self.type_var = tk.StringVar()
        self.object_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.exp_var = tk.StringVar()
        self.focal_var = tk.StringVar()
        self.year_var = tk.StringVar()
        self.date_start_var = tk.StringVar()
        self.date_end_var = tk.StringVar()
        self.pattern_var = tk.StringVar()
        self.is_folder_var = tk.BooleanVar(value=False)
        self.only_duplicates_var = tk.BooleanVar(value=False)
        self.no_row_limit_var = tk.BooleanVar(value=False)

        # Row 0: Frame Type | Object (Target) | Filter
        ttk.Label(filter_frame, text="Frame Type:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=3)
        self.type_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.type_var,
            values=["", "Light", "Dark", "Flat", "Bias", "Dark-Flat"],
            width=18,
        )
        self.type_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 15), pady=3)

        ttk.Label(filter_frame, text="Object (Target):").grid(row=0, column=2, sticky=tk.W, padx=(0, 5), pady=3)
        self.object_entry = ttk.Entry(filter_frame, textvariable=self.object_var, width=22)
        self.object_entry.grid(row=0, column=3, sticky=tk.W, padx=(0, 15), pady=3)

        ttk.Label(filter_frame, text="Filter:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5), pady=3)
        self.filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var, width=22)
        self.filter_entry.grid(row=0, column=5, sticky=tk.W, padx=(0, 15), pady=3)

        # Row 1: Exposure (s) | Focal Length (±5 mm) | Year (YYYY)
        ttk.Label(filter_frame, text="Exposure (s):").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=3)
        self.exp_entry = ttk.Entry(filter_frame, textvariable=self.exp_var, width=21)
        self.exp_entry.grid(row=1, column=1, sticky=tk.W, padx=(0, 15), pady=3)

        ttk.Label(filter_frame, text="Focal Length (±5 mm):").grid(row=1, column=2, sticky=tk.W, padx=(0, 5), pady=3)
        self.focal_entry = ttk.Entry(filter_frame, textvariable=self.focal_var, width=22)
        self.focal_entry.grid(row=1, column=3, sticky=tk.W, padx=(0, 15), pady=3)

        ttk.Label(filter_frame, text="Year (YYYY):").grid(row=1, column=4, sticky=tk.W, padx=(0, 5), pady=3)
        self.year_entry = ttk.Entry(filter_frame, textvariable=self.year_var, width=22)
        self.year_entry.grid(row=1, column=5, sticky=tk.W, padx=(0, 15), pady=3)

        # Row 2: Date Range | Name Pattern + Is Folder Toggle
        ttk.Label(filter_frame, text="Date Range:").grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=3)
        date_box = ttk.Frame(filter_frame)
        date_box.grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=3)

        self.date_start_entry = ttk.Entry(date_box, textvariable=self.date_start_var, width=11)
        self.date_start_entry.pack(side=tk.LEFT)
        ttk.Label(date_box, text=" -> ").pack(side=tk.LEFT)
        self.date_end_entry = ttk.Entry(date_box, textvariable=self.date_end_var, width=11)
        self.date_end_entry.pack(side=tk.LEFT)
        date_hint = ttk.Label(date_box, text=" (YYYY-MM-DD, empty = today)", foreground=self.palette["muted_fg"])
        date_hint.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(filter_frame, text="Name Pattern:").grid(row=2, column=4, sticky=tk.W, padx=(0, 5), pady=3)
        pattern_box = ttk.Frame(filter_frame)
        pattern_box.grid(row=2, column=5, columnspan=2, sticky=tk.W, pady=3)

        self.pattern_entry = ttk.Entry(pattern_box, textvariable=self.pattern_var, width=22)
        self.pattern_entry.pack(side=tk.LEFT)

        ttk.Checkbutton(
            pattern_box,
            text="Is Folder (ignore other filters)",
            variable=self.is_folder_var,
            command=self._on_toggle_is_folder,
        ).pack(side=tk.LEFT, padx=(10, 6))

        pattern_hint = ttk.Label(
            pattern_box,
            text="(exact or * / ?)",
            foreground=self.palette["muted_fg"],
        )
        pattern_hint.pack(side=tk.LEFT)

        self._muted_labels = (date_hint, pattern_hint)

        # Row 3: Duplicates checkbox + Row limit checkbox + Action buttons
        controls_row = ttk.Frame(filter_frame)
        controls_row.grid(row=3, column=0, columnspan=7, sticky=tk.EW, pady=(8, 0))

        self.duplicates_chk = ttk.Checkbutton(
            controls_row,
            text="Show duplicates (+ originals)",
            variable=self.only_duplicates_var,
            command=self.refresh_results,
        )
        self.duplicates_chk.pack(side=tk.LEFT, padx=(0, 15))

        self.limit_chk = ttk.Checkbutton(
            controls_row,
            text=f"Show all rows (over {self.config_manager.data['max_table_rows']:,})",
            variable=self.no_row_limit_var,
            command=self.refresh_results,
        )
        self.limit_chk.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Button(controls_row, text="Apply Filters", command=self.refresh_results).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls_row, text="Reset Filters", command=self.reset_filters).pack(side=tk.LEFT)

        self._file_only_widgets = (
            self.type_combo,
            self.object_entry,
            self.filter_entry,
            self.exp_entry,
            self.focal_entry,
            self.year_entry,
            self.date_start_entry,
            self.date_end_entry,
            self.duplicates_chk,
        )

        for widget in (
            self.type_combo,
            self.object_entry,
            self.filter_entry,
            self.exp_entry,
            self.focal_entry,
            self.year_entry,
            self.date_start_entry,
            self.date_end_entry,
            self.pattern_entry,
        ):
            widget.bind("<Return>", lambda e: self.refresh_results())
        self.type_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_results())

        # --- SECTION 3: Results Table ---
        table_frame = ttk.Frame(self.root, padding=(10, 5, 10, 10))
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("status", "object", "type", "exp", "focal", "filter", "date_obs", "size_mb", "path")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")

        headers = {
            "status": ("Status", 95),
            "object": ("Object / Name", 145),
            "type": ("Type", 80),
            "exp": ("Exp (s)", 65),
            "focal": ("Focal (mm)", 75),
            "filter": ("Filter", 95),
            "date_obs": ("Date (Header / Mod.)", 160),
            "size_mb": ("MB", 55),
            "path": ("Full Path", 480),
        }
        for col, (title, width) in headers.items():
            self.tree.heading(col, text=title, command=lambda c=col: self.sort_column(c, False))
            self.tree.column(col, width=width, anchor=tk.W if col in ("object", "path", "date_obs") else tk.CENTER)

        self.tree.bind("<Control-a>", self.select_all)
        self.tree.bind("<Control-A>", self.select_all)
        self.tree.bind("<Escape>", self.unselect_all)
        self.tree.bind("<Delete>", lambda e: self.delete_selected())

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # --- SECTION 4: Bottom Action Bar & Status ---
        bottom_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom_frame.pack(fill=tk.X)

        ttk.Button(bottom_frame, text="Select All (Ctrl+A)", command=self.select_all).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bottom_frame, text="Unselect All", command=self.unselect_all).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bottom_frame, text="Select Duplicates Only", command=self.select_duplicates_only).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(bottom_frame, text="Invert Tags", command=self.invert_tags).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(bottom_frame, text="Move Selected to Quarantine", command=self.move_selected_to_quarantine).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(bottom_frame, text="Delete Selected (Permanent)", command=self.delete_selected).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(bottom_frame, text="View Audit Log", command=self.open_log_viewer).pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bottom_frame, textvariable=self.status_var).pack(side=tk.RIGHT)

    def _load_initial_db_state(self):
        cur = self.conn.cursor()
        fits_count = cur.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
        folders_count = cur.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
        meta_time = cur.execute("SELECT value FROM app_meta WHERE key = 'last_scan_time'").fetchone()

        self.folder_var.set(self._get_startup_scan_dir())

        if fits_count > 0 or folders_count > 0:
            self.refresh_results()
            last_info = f" (last scan: {meta_time[0]})" if meta_time else ""
            self.status_var.set(
                f"Loaded from DB: {fits_count:,} FITS | {folders_count:,} folders{last_info}"
            )
        else:
            self.status_var.set("Database is empty. Select a folder and click 'Scan Folder'.")

    def open_settings(self):
        old_db_path = self.config_manager.data["db_path"]

        def on_settings_saved():
            new_cfg = self.config_manager.data
            self.logger.set_path(new_cfg["log_path"])
            self.limit_chk.configure(text=f"Show all rows (over {new_cfg['max_table_rows']:,})")
            self.apply_theme()

            if not normalize_path(new_cfg.get("last_scanned_dir", "")):
                self.folder_var.set(normalize_path(new_cfg.get("default_scan_dir", "")))

            if os.path.normcase(os.path.abspath(new_cfg["db_path"])) != os.path.normcase(os.path.abspath(old_db_path)):
                self._connect_db()
                self.sample_hash_cache.clear()
                self._load_initial_db_state()
            else:
                self.refresh_results()

        SettingsDialog(self.root, self.config_manager, on_settings_saved)

    def open_log_viewer(self):
        LogViewerDialog(
            self.root,
            Path(normalize_path(self.config_manager.data["log_path"])),
            self.palette,
        )

    def select_all(self, event=None):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def unselect_all(self, event=None):
        self.tree.selection_remove(self.tree.selection())
        self.status_var.set("Selection cleared.")
        return "break"

    def select_duplicates_only(self):
        dup_items = [
            item_id
            for item_id in self.tree.get_children()
            if "duplicate" in self.tree.item(item_id, "tags")
        ]
        self.tree.selection_set(dup_items)
        if dup_items:
            self.tree.see(dup_items[0])
            self.status_var.set(f"Selected {len(dup_items):,} duplicate(s) (originals excluded).")
        else:
            self.status_var.set("No duplicates found in the current view.")

    def invert_tags(self):
        if self.is_folder_var.get():
            return

        items = self.tree.get_children()
        if not items:
            return

        swapped_to_dup = 0
        swapped_to_orig = 0

        for item_id in items:
            current_tags = set(self.tree.item(item_id, "tags"))
            if "dup_group" not in current_tags:
                # Keep standalone files without duplicates untouched
                continue

            if "duplicate" in current_tags:
                self.tree.set(item_id, "status", "ORIGINAL")
                self.tree.item(item_id, tags=("dup_group",))
                swapped_to_orig += 1
            else:
                self.tree.set(item_id, "status", "DUPLICATE")
                self.tree.item(item_id, tags=("duplicate", "dup_group"))
                swapped_to_dup += 1

        if swapped_to_dup or swapped_to_orig:
            self.status_var.set(
                f"Tags inverted: {swapped_to_dup:,} marked as DUPLICATE | {swapped_to_orig:,} marked as ORIGINAL."
            )
        else:
            self.status_var.set("No duplicate groups in the current view to invert.")

    def _on_toggle_is_folder(self):
        state = "disabled" if self.is_folder_var.get() else "normal"
        for w in self._file_only_widgets:
            w.configure(state=state)
        self.refresh_results()

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(normalize_path(folder))

    def reset_filters(self):
        self.type_var.set("")
        self.object_var.set("")
        self.filter_var.set("")
        self.exp_var.set("")
        self.focal_var.set("")
        self.year_var.set("")
        self.date_start_var.set("")
        self.date_end_var.set("")
        self.pattern_var.set("")
        self.only_duplicates_var.set(False)
        self.is_folder_var.set(False)
        self._on_toggle_is_folder()

    # --- ASYNCHRONOUS BACKGROUND SCANNING ---
    def start_scan(self):
        if self.is_scanning:
            return

        normalized_input = normalize_path(self.folder_var.get())
        self.folder_var.set(normalized_input)
        source_dir = Path(normalized_input)

        if not normalized_input or not source_dir.exists() or not source_dir.is_dir():
            messagebox.showerror("Error", "The specified scan folder does not exist.")
            return

        # Persist hidden last_scanned_dir without altering default_scan_dir
        self.config_manager.save({"last_scanned_dir": str(source_dir)})

        cur = self.conn.cursor()
        cur.execute("DELETE FROM frames")
        cur.execute("DELETE FROM folders")
        self.conn.commit()
        self.sample_hash_cache.clear()

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.is_scanning = True
        self.scan_start_time = time.perf_counter()
        self.scan_root_active = str(source_dir)
        self.stop_event.clear()
        self.btn_scan.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set("Starting fast background scan...")

        quarantine_norm = os.path.normcase(os.path.abspath(self.config_manager.data["quarantine_dir"]))

        worker = threading.Thread(
            target=self._scan_worker,
            args=(str(source_dir), quarantine_norm),
            daemon=True,
        )
        worker.start()
        self.root.after(80, self._process_scan_queue)

    def stop_scan(self):
        if self.is_scanning:
            self.stop_event.set()
            self.status_var.set("Stopping scan...")

    def _scan_worker(self, root_str: str, quarantine_norm: str):
        """Runs in a background thread using os.scandir and fast 2880-byte FITS header parsing."""
        fits_batch = []
        folder_records = []
        direct_counts = {}
        fits_count = 0
        folders_count = 0

        dir_stack = [root_str]

        while dir_stack and not self.stop_event.is_set():
            current_dir = dir_stack.pop()
            local_files = 0
            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        if self.stop_event.is_set():
                            break

                        entry_path = normalize_path(entry.path)
                        entry_norm = os.path.normcase(os.path.abspath(entry_path))
                        if entry_norm == quarantine_norm or entry.name == "_Quarantine_Duplicates":
                            continue

                        try:
                            if entry.is_dir(follow_symlinks=False):
                                dir_stack.append(entry_path)
                                st = entry.stat(follow_symlinks=False)
                                mod_date = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                                folder_records.append((entry_path, entry.name, mod_date))
                                direct_counts[entry_path] = 0
                                folders_count += 1

                            elif entry.is_file(follow_symlinks=False):
                                local_files += 1
                                lower_name = entry.name.lower()
                                if lower_name.endswith(".fit") or lower_name.endswith(".fits"):
                                    st = entry.stat(follow_symlinks=False)
                                    size_bytes = st.st_size
                                    mtime = st.st_mtime
                                    size_mb = round(size_bytes / (1024 * 1024), 1)
                                    hdr = read_fits_header_fast(Path(entry_path))

                                    fits_batch.append((
                                        entry_path,
                                        entry.name,
                                        size_bytes,
                                        mtime,
                                        size_mb,
                                        str(hdr.get("IMAGETYP", "UNKNOWN")),
                                        str(hdr.get("OBJECT", "NO_OBJECT")),
                                        str(hdr["DATE-OBS"]) if "DATE-OBS" in hdr else None,
                                        parse_float_header(hdr.get("EXPTIME")),
                                        parse_float_header(hdr.get("FOCALLEN")),
                                        str(hdr.get("FILTER", "NoFilter")),
                                    ))
                                    fits_count += 1
                        except Exception:
                            pass

                        if len(fits_batch) >= 300:
                            self.scan_queue.put(("BATCH", fits_batch, fits_count, folders_count))
                            fits_batch = []
            except Exception:
                pass

            if current_dir in direct_counts:
                direct_counts[current_dir] += local_files

        if fits_batch:
            self.scan_queue.put(("BATCH", fits_batch, fits_count, folders_count))

        # Propagate total file counts upward from deepest folders to parent folders
        for d_path in sorted(direct_counts.keys(), key=len, reverse=True):
            parent = os.path.dirname(d_path)
            if parent in direct_counts:
                direct_counts[parent] += direct_counts[d_path]

        all_folders = [
            (p, name, mdate, direct_counts.get(p, 0))
            for (p, name, mdate) in folder_records
        ]

        self.scan_queue.put(("DONE", fits_count, folders_count, all_folders, self.stop_event.is_set()))

    def _process_scan_queue(self):
        cur = self.conn.cursor()
        finished = False

        try:
            while True:
                msg = self.scan_queue.get_nowait()
                msg_type = msg[0]

                if msg_type == "BATCH":
                    _, fits_batch, fits_count, folders_count = msg
                    if fits_batch:
                        cur.executemany("""
                            INSERT INTO frames (
                                path, filename, size_bytes, mtime, size_mb,
                                imagetyp, object_name, date_obs, exptime, focal_len, filter_name
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, fits_batch)
                    self.status_var.set(f"Indexing... {fits_count:,} FITS files | {folders_count:,} folders.")

                elif msg_type == "DONE":
                    _, fits_count, folders_count, all_folders, stopped_manually = msg
                    elapsed = time.perf_counter() - self.scan_start_time
                    scan_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    if all_folders:
                        cur.executemany("""
                            INSERT INTO folders (path, folder_name, mod_date, file_count)
                            VALUES (?, ?, ?, ?)
                        """, all_folders)

                    cur.execute("""
                        UPDATE frames
                        SET file_hash = (
                            SELECT hc.file_hash
                            FROM hash_cache hc
                            WHERE hc.path = frames.path
                              AND hc.size_bytes = frames.size_bytes
                              AND hc.mtime = frames.mtime
                        )
                        WHERE EXISTS (
                            SELECT 1
                            FROM hash_cache hc
                            WHERE hc.path = frames.path
                              AND hc.size_bytes = frames.size_bytes
                              AND hc.mtime = frames.mtime
                        )
                    """)

                    cur.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES ('last_scan_root', ?)", (self.scan_root_active,))
                    cur.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES ('last_scan_time', ?)", (scan_timestamp,))
                    self.conn.commit()

                    status_label = "STOPPED" if stopped_manually else "COMPLETED"
                    self.logger.log_event(
                        "SCAN",
                        f"Status={status_label} | Root=\"{self.scan_root_active}\" | FITS={fits_count:,} | Folders={folders_count:,} | Duration={elapsed:.2f}s",
                    )

                    self.is_scanning = False
                    self.btn_scan.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    finished = True
                    self.refresh_results()
                    if stopped_manually:
                        self.status_var.set(
                            f"Scan stopped manually ({fits_count:,} FITS, {folders_count:,} folders indexed in {elapsed:.1f}s)."
                        )
                    break
        except queue.Empty:
            pass

        if not finished:
            self.root.after(80, self._process_scan_queue)

    def _update_candidate_hashes(self, where_clause: str, params: list):
        """
        Computes blake2b content hashes ONLY for files sharing exact size and FITS metadata,
        preventing post-processed derivatives (GraXpert, StarNet, Stacked) from false-flagging.
        """
        cur = self.conn.cursor()
        sql_candidates = f"""
            WITH Groups AS (
                SELECT 
                    id, path, size_bytes, mtime, file_hash,
                    COUNT(*) OVER (
                        PARTITION BY 
                            size_bytes,
                            CASE WHEN date_obs IS NOT NULL AND TRIM(date_obs) <> '' THEN SUBSTR(date_obs, 1, 19) ELSE LOWER(filename) END,
                            COALESCE(exptime, -1),
                            COALESCE(ROUND(focal_len, 1), -1),
                            imagetyp,
                            filter_name
                    ) AS collision_count
                FROM frames
                WHERE 1=1 {where_clause}
            )
            SELECT id, path, size_bytes, mtime
            FROM Groups
            WHERE collision_count > 1 AND (file_hash IS NULL OR file_hash = '')
        """
        candidates = cur.execute(sql_candidates, params).fetchall()
        if not candidates:
            return

        updates = []
        cache_inserts = []
        sample_groups = {}

        for row_id, path_str, size_bytes, mtime in candidates:
            key = (path_str, size_bytes)
            if key not in self.sample_hash_cache:
                self.sample_hash_cache[key] = compute_file_hash(path_str, size_bytes, full=False)
            short_hash = self.sample_hash_cache[key]
            sample_groups.setdefault((size_bytes, short_hash), []).append((row_id, path_str, size_bytes, mtime))

        for (size_bytes, short_hash), items in sample_groups.items():
            if len(items) == 1:
                row_id, path_str, sz, mt = items[0]
                updates.append((short_hash, row_id))
                cache_inserts.append((path_str, sz, mt, short_hash))
            else:
                for row_id, path_str, sz, mt in items:
                    full_hash = compute_file_hash(path_str, sz, full=True)
                    updates.append((full_hash, row_id))
                    cache_inserts.append((path_str, sz, mt, full_hash))

        cur.executemany("UPDATE frames SET file_hash = ? WHERE id = ?", updates)
        cur.executemany(
            "INSERT OR REPLACE INTO hash_cache (path, size_bytes, mtime, file_hash) VALUES (?, ?, ?, ?)",
            cache_inserts,
        )
        self.conn.commit()

    def refresh_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        cur = self.conn.cursor()
        no_limit = self.no_row_limit_var.get()
        max_rows = self.config_manager.data["max_table_rows"]

        # --- MODE 1: Folder Search ---
        if self.is_folder_var.get():
            self.tree.heading("size_mb", text="Files")
            query = "SELECT folder_name, mod_date, file_count, path FROM folders WHERE 1=1"
            params = []

            pattern = self.pattern_var.get().strip()
            if pattern:
                query += " AND LOWER(folder_name) GLOB LOWER(?)"
                params.append(pattern)

            query += " ORDER BY path ASC"
            rows = cur.execute(query, params).fetchall()
            total_found = len(rows)

            display_rows = rows if no_limit else rows[:max_rows]
            for folder_name, mod_date, file_count, path_str in display_rows:
                self.tree.insert(
                    "",
                    tk.END,
                    values=("FOLDER", folder_name, "Folder", "-", "-", "-", mod_date or "-", file_count, normalize_path(path_str)),
                    tags=("folder",),
                )

            if total_found > len(display_rows):
                self.status_var.set(f"Folders found: {total_found:,} (showing first {len(display_rows):,})")
            else:
                self.status_var.set(f"Folders displayed: {total_found:,}")
            return

        # --- MODE 2: FITS File Search ---
        self.tree.heading("size_mb", text="MB")
        where_clause = ""
        params = []

        frame_type = self.type_var.get().strip()
        if frame_type:
            normalized_type = frame_type.replace("-", "").replace(" ", "")
            where_clause += " AND REPLACE(REPLACE(imagetyp, '-', ''), ' ', '') LIKE ?"
            params.append(f"%{normalized_type}%")

        obj = self.object_var.get().strip()
        if obj:
            where_clause += " AND object_name LIKE ?"
            params.append(f"%{obj}%")

        flt = self.filter_var.get().strip()
        if flt:
            where_clause += " AND filter_name LIKE ?"
            params.append(f"%{flt}%")

        exp_text = self.exp_var.get().strip().rstrip("sS")
        if exp_text:
            try:
                exp_val = float(exp_text)
                where_clause += " AND exptime IS NOT NULL AND ABS(exptime - ?) < 0.01"
                params.append(exp_val)
            except ValueError:
                messagebox.showwarning("Invalid Exposure", "Exposure value must be a number (e.g. 300).")
                return

        focal_text = self.focal_var.get().strip().lower().rstrip("m").strip()
        if focal_text:
            try:
                focal_val = float(focal_text)
                where_clause += " AND focal_len IS NOT NULL AND ABS(focal_len - ?) <= 5.0"
                params.append(focal_val)
            except ValueError:
                messagebox.showwarning("Invalid Focal Length", "Focal Length must be a number in mm (e.g. 361).")
                return

        year = self.year_var.get().strip()
        if year:
            where_clause += " AND date_obs IS NOT NULL AND SUBSTR(date_obs, 1, 4) = ?"
            params.append(year)

        date_start = self.date_start_var.get().strip()
        date_end = self.date_end_var.get().strip()

        if date_start and not date_end:
            date_end = datetime.now().strftime("%Y-%m-%d")

        if date_start:
            where_clause += " AND date_obs IS NOT NULL AND SUBSTR(date_obs, 1, 10) >= ?"
            params.append(date_start)

        if date_end:
            where_clause += " AND date_obs IS NOT NULL AND SUBSTR(date_obs, 1, 10) <= ?"
            params.append(date_end)

        pattern = self.pattern_var.get().strip()
        if pattern:
            where_clause += " AND LOWER(filename) GLOB LOWER(?)"
            params.append(pattern)

        self._update_candidate_hashes(where_clause, params)

        query = f"""
            WITH Analysis AS (
                SELECT 
                    id, path, filename, size_bytes, size_mb, imagetyp, object_name,
                    date_obs, exptime, focal_len, filter_name, file_hash,
                    CASE 
                        WHEN file_hash IS NOT NULL AND file_hash <> '' THEN
                            ROW_NUMBER() OVER (
                                PARTITION BY size_bytes, file_hash
                                ORDER BY path
                            )
                        ELSE 1
                    END AS copy_num,
                    CASE 
                        WHEN file_hash IS NOT NULL AND file_hash <> '' THEN
                            COUNT(*) OVER (
                                PARTITION BY size_bytes, file_hash
                            )
                        ELSE 1
                    END AS group_size
                FROM frames
                WHERE 1=1 {where_clause}
            )
            SELECT copy_num, group_size, object_name, imagetyp, exptime, focal_len, filter_name, date_obs, size_mb, path
            FROM Analysis
            WHERE 1=1
        """
        if self.only_duplicates_var.get():
            query += " AND group_size > 1 ORDER BY date_obs DESC, file_hash ASC, copy_num ASC"
        else:
            query += " ORDER BY date_obs DESC, path ASC"

        rows = cur.execute(query, params).fetchall()
        total_found = len(rows)
        dup_count = sum(1 for r in rows if r[0] > 1)

        display_rows = rows if no_limit else rows[:max_rows]
        for row in display_rows:
            copy_num, group_size, ob, tp, ex, focal, fl, dt, mb, path_str = row
            is_dup = copy_num > 1
            status_text = f"DUPLICATE #{copy_num}" if is_dup else "ORIGINAL"

            if is_dup:
                tags = ("duplicate", "dup_group")
            elif group_size > 1:
                tags = ("dup_group",)
            else:
                tags = ()

            if focal is not None:
                focal_str = f"{focal:.0f}" if focal.is_integer() else f"{focal:.1f}"
            else:
                focal_str = "-"

            self.tree.insert(
                "",
                tk.END,
                values=(
                    status_text,
                    ob,
                    tp,
                    ex if ex is not None else "-",
                    focal_str,
                    fl,
                    dt or "No timestamp",
                    mb,
                    normalize_path(path_str),
                ),
                tags=tags,
            )

        if total_found > len(display_rows):
            self.status_var.set(
                f"Found: {total_found:,} (showing first {len(display_rows):,}) | Duplicates: {dup_count:,}"
            )
        else:
            self.status_var.set(f"Displayed: {total_found:,} files | Duplicates in selection: {dup_count:,}")

    def sort_column(self, col: str, descending: bool):
        data = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        try:
            data.sort(key=lambda t: float(t[0]) if t[0] != "-" else -1.0, reverse=descending)
        except ValueError:
            data.sort(key=lambda t: t[0].lower(), reverse=descending)

        for index, (_, k) in enumerate(data):
            self.tree.move(k, "", index)

        self.tree.heading(col, command=lambda: self.sort_column(col, not descending))

    def _delete_path_from_db(self, cur: sqlite3.Cursor, target_path: Path, removed_files: int = 0):
        """Removes a file or directory from SQLite and decrements parent folder file counts."""
        norm_str = normalize_path(str(target_path))
        sub_prefix = norm_str + os.sep
        prefix_len = len(sub_prefix)
        for table in ("frames", "folders", "hash_cache"):
            cur.execute(
                f"DELETE FROM {table} WHERE path = ? OR SUBSTR(path, 1, ?) = ?",
                (norm_str, prefix_len, sub_prefix),
            )
        if removed_files > 0:
            cur.execute(
                """
                UPDATE folders
                SET file_count = MAX(0, file_count - ?)
                WHERE LENGTH(?) > LENGTH(path) + 1
                  AND LOWER(SUBSTR(?, 1, LENGTH(path) + 1)) = LOWER(path || ?)
                """,
                (removed_files, norm_str, norm_str, os.sep),
            )

    def move_selected_to_quarantine(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Information", "Please select one or more rows from the list first.")
            return

        quarantine_dir = Path(normalize_path(self.config_manager.data["quarantine_dir"]))
        confirm = messagebox.askyesno(
            "Confirm Move to Quarantine",
            f"Move {len(selected)} selected item(s) to:\n{quarantine_dir}?",
        )
        if not confirm:
            return

        quarantine_dir.mkdir(parents=True, exist_ok=True)
        cur = self.conn.cursor()
        moved_count = 0
        moved_bytes = 0
        log_details = []
        errors = []

        for item_id in selected:
            old_path = Path(normalize_path(self.tree.set(item_id, "path")))
            if not old_path.exists() or old_path == quarantine_dir:
                continue

            try:
                item_size, item_files = get_path_size_and_count(old_path)
                new_path = quarantine_dir / old_path.name
                if new_path.exists():
                    timestamp_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_path = quarantine_dir / f"{old_path.stem}_{timestamp_suffix}{old_path.suffix}"

                shutil.move(str(old_path), str(new_path))
                self._delete_path_from_db(cur, old_path, removed_files=item_files)

                moved_count += 1
                moved_bytes += item_size
                log_details.append(f"MOVED ({format_size(item_size)}): {old_path}  ==>  {new_path}")
            except Exception as e:
                errors.append(f"{old_path.name}: {e}")
                log_details.append(f"ERROR moving {old_path}: {e}")

        self.conn.commit()
        self.refresh_results()

        summary_text = f"Moved {moved_count} item(s) ({format_size(moved_bytes)}) to \"{quarantine_dir}\" | Errors={len(errors)}"
        self.logger.log_event("QUARANTINE", summary_text, log_details)

        dialog_msg = (
            f"Quarantine Summary:\n\n"
            f"• Items moved: {moved_count}\n"
            f"• Total size: {format_size(moved_bytes)}\n"
            f"• Destination: {quarantine_dir}\n"
            f"• Logged to: {self.config_manager.data['log_path']}"
        )
        if errors:
            dialog_msg += "\n\nErrors:\n" + "\n".join(errors[:5])
        messagebox.showinfo("Quarantine Complete", dialog_msg)

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Information", "Please select one or more rows from the list first.")
            return

        targets = []
        total_bytes = 0
        folder_count = 0
        file_count = 0

        for item_id in selected:
            target_path = Path(normalize_path(self.tree.set(item_id, "path")))
            if target_path.exists():
                is_dir = target_path.is_dir()
                sz, f_cnt = get_path_size_and_count(target_path)
                targets.append((target_path, is_dir, sz, f_cnt))
                total_bytes += sz
                if is_dir:
                    folder_count += 1
                else:
                    file_count += 1

        if not targets:
            messagebox.showinfo("Information", "None of the selected paths exist on disk anymore.")
            self.refresh_results()
            return

        confirm = messagebox.askyesno(
            "Confirm Permanent Deletion",
            f"WARNING: You are about to PERMANENTLY delete {len(targets)} item(s):\n"
            f"• Files: {file_count}\n"
            f"• Folders: {folder_count}\n"
            f"• Disk space to be freed: {format_size(total_bytes)}\n\n"
            "Deleted items bypass the Recycle Bin and CANNOT be recovered.\n"
            "All deletions will be recorded in the audit log.\n\n"
            "Proceed with permanent deletion?",
            icon="warning",
        )
        if not confirm:
            return

        cur = self.conn.cursor()
        deleted_count = 0
        freed_bytes = 0
        log_details = []
        errors = []

        for target_path, is_dir, sz, f_cnt in targets:
            kind = "FOLDER" if is_dir else "FILE"
            try:
                if target_path.exists():
                    if is_dir:
                        shutil.rmtree(target_path)
                    else:
                        target_path.unlink()

                self._delete_path_from_db(cur, target_path, removed_files=f_cnt)

                deleted_count += 1
                freed_bytes += sz
                log_details.append(f"DELETED [{kind}] ({format_size(sz)}): {target_path}")
            except Exception as e:
                errors.append(f"{target_path.name}: {e}")
                log_details.append(f"ERROR deleting [{kind}] {target_path}: {e}")

        self.conn.commit()
        self.refresh_results()

        summary_text = f"Permanently deleted {deleted_count} item(s) | Space freed: {format_size(freed_bytes)} | Errors={len(errors)}"
        self.logger.log_event("DELETE", summary_text, log_details)

        dialog_msg = (
            f"Deletion Summary:\n\n"
            f"• Permanently deleted: {deleted_count} item(s)\n"
            f"• Disk space freed: {format_size(freed_bytes)}\n"
            f"• Audit log updated: {self.config_manager.data['log_path']}"
        )
        if errors:
            dialog_msg += "\n\nErrors:\n" + "\n".join(errors[:5])
        messagebox.showinfo("Deletion Confirmed", dialog_msg)


if __name__ == "__main__":
    root = tk.Tk()
    app = AstroOrganizerApp(root)
    root.mainloop()