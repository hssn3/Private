"""The main window: five steps, right-hand navigation, one shared activity log."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import tkinter

import customtkinter as ctk

from core import collector, detect, icons, paths, restore, shortcuts, uploader
from core.config import ConfigStore
from core.logging_setup import log
from core.service import BackupService

from . import theme
from .widgets import AppTile, GlassCard, LogPanel, SectionTitle, StatTile

def _bundled_icon() -> Path:
    """The .ico sits next to the bundle when frozen, in build/ when not."""
    import sys

    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app.ico"
    return Path(__file__).resolve().parents[2] / "build" / "app.ico"


NAV = (
    ("apps", "🧩", "۱ · انتخاب نرم‌افزارها"),
    ("transfer", "📤", "۲ · انتقال اطلاعات"),
    ("backup", "💾", "۳ · بکاپ و زمان‌بندی"),
    ("cloud", "☁️", "۴ · فضای ابری"),
    ("restore", "♻️", "بازگردانی"),
)

INTERVAL_CHOICES = ("5", "10", "15", "30", "60", "120", "360")


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        paths.ensure_layout()
        self.store = ConfigStore()
        self.service = BackupService(self.store, on_event=self._on_event)

        self.detected: list[detect.DetectedApp] = []
        self.tiles: dict[str, AppTile] = {}
        self.selected_keys: set[str] = set(self.store.current.selected_apps)
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._active_page = ""

        self._configure_window()
        self._build_header()
        self._build_body()
        self._build_log()

        self.show_page("apps")
        self.after(200, self.refresh_apps)
        self.after(1000, self._tick)

        if self.store.current.schedule_enabled:
            self.after(1500, lambda: self.service.scheduler.start(self.store.current.interval_minutes))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------- chrome
    def _configure_window(self) -> None:
        ctk.set_appearance_mode("dark")
        self.title("Backup Suite - محافظ فولدر 0")
        self.geometry("1180x780")
        self.minsize(1020, 700)
        self.configure(fg_color=theme.BG)
        theme.pick_font_family()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Windows 11 acrylic, when the platform offers it. Everything still
        # looks right without it, so failures are silent.
        try:
            import pywinstyles

            pywinstyles.apply_style(self, "acrylic")
            pywinstyles.change_header_color(self, theme.BG)
            pywinstyles.change_title_color(self, theme.TEXT)
        except Exception:  # noqa: BLE001
            log.debug("acrylic backdrop unavailable")

        icon_file = _bundled_icon()
        if icon_file.exists():
            try:
                self.iconbitmap(str(icon_file))
            except Exception:  # noqa: BLE001
                pass

    def _build_header(self) -> None:
        header = GlassCard(self, height=78)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkLabel(
            header, text="🛡️", font=theme.font(26), width=52, height=52,
            fg_color=theme.ACCENT_2, corner_radius=14,
        )
        badge.grid(row=0, column=2, rowspan=2, padx=(14, 10), pady=13)

        ctk.CTkLabel(
            header, text="Backup Suite", font=theme.font(19, "bold"),
            text_color=theme.TEXT, anchor="e",
        ).grid(row=0, column=1, sticky="ew", pady=(14, 0))
        ctk.CTkLabel(
            header, text=theme.fa(f"فولدر کاری: {paths.root_dir()}"), font=theme.font(11),
            text_color=theme.TEXT_MUTED, anchor="e",
        ).grid(row=1, column=1, sticky="ew", pady=(0, 14))

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=0, rowspan=2, padx=14)

        self.status_pill = ctk.CTkLabel(
            actions, text=theme.fa("آماده"), font=theme.font(11, "bold"),
            text_color=theme.OK, fg_color="#0f2136", corner_radius=999,
            width=150, height=30,
        )
        self.status_pill.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            actions, text=theme.fa("♻️  بازگردانی از بکاپ"), font=theme.font(12, "bold"),
            fg_color=theme.GLASS_LIGHT, hover_color=theme.GLASS_EDGE,
            border_width=1, border_color=theme.GLASS_EDGE,
            corner_radius=theme.RADIUS_SM, height=36, width=190,
            command=lambda: self.show_page("restore"),
        ).pack(side="left")

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=18)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Right-hand navigation, because the whole interface reads right to left.
        nav = GlassCard(body, width=210)
        nav.grid(row=0, column=1, sticky="ns", padx=(12, 0))
        nav.grid_propagate(False)

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for key, icon, label in NAV:
            button = ctk.CTkButton(
                nav, text=f"{theme.fa(label)}  {icon}", font=theme.font(12, "bold"),
                anchor="e", height=44, corner_radius=theme.RADIUS_SM,
                fg_color="transparent", hover_color=theme.GLASS_LIGHT,
                text_color=theme.TEXT_MUTED,
                command=lambda k=key: self.show_page(k),
            )
            button.pack(fill="x", padx=10, pady=(10 if key == "apps" else 4, 0))
            self.nav_buttons[key] = button

        ctk.CTkLabel(
            nav, text=theme.fa("قانون چرخه فعال است:\nهمیشه آخرین N بکاپ نگه داشته می‌شود"),
            font=theme.font(10), text_color=theme.TEXT_DIM, justify="right", wraplength=180,
        ).pack(side="bottom", padx=14, pady=14)

        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.grid(row=0, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        for builder in (self._page_apps, self._page_transfer, self._page_backup,
                        self._page_cloud, self._page_restore):
            builder()

    def _build_log(self) -> None:
        wrapper = GlassCard(self, height=132)
        wrapper.grid(row=2, column=0, sticky="ew", padx=18, pady=(10, 16))
        wrapper.grid_propagate(False)
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(1, weight=1)

        row = ctk.CTkFrame(wrapper, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        ctk.CTkLabel(
            row, text=theme.fa("گزارش فعالیت"), font=theme.font(11, "bold"),
            text_color=theme.TEXT_MUTED,
        ).pack(side="right")
        ctk.CTkButton(
            row, text=theme.fa("باز کردن فولدر 0"), width=120, height=24,
            font=theme.font(10), fg_color=theme.GLASS_LIGHT, hover_color=theme.GLASS_EDGE,
            command=self._open_root,
        ).pack(side="left")

        self.log_panel = LogPanel(wrapper, height=80)
        self.log_panel.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        self.log_panel.append("info", "برنامه آماده است.")

    # -------------------------------------------------------------- pages
    def _new_page(self, key: str) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_remove()
        self._pages[key] = page
        return page

    def show_page(self, key: str) -> None:
        for name, page in self._pages.items():
            page.grid_remove() if name != key else page.grid()
        for name, button in self.nav_buttons.items():
            active = name == key
            button.configure(
                fg_color=theme.ACCENT if active else "transparent",
                text_color=theme.TEXT if active else theme.TEXT_MUTED,
            )
        self._active_page = key
        if key == "backup":
            self._refresh_archive_list()

    # ------------------------------------------------------ page 1: apps
    def _page_apps(self) -> None:
        page = self._new_page("apps")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        head = GlassCard(page)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        SectionTitle(
            head, "🧩", "نرم‌افزارهای نصب‌شده",
            "روی هر کارت بزن تا انتخاب شود. دیتای همین‌ها به فولدر Apps منتقل می‌شود.",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))

        controls = ctk.CTkFrame(head, fg_color="transparent")
        controls.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        search = ctk.CTkEntry(
            controls, textvariable=self.search_var, width=220, height=34,
            placeholder_text=theme.fa("جستجو…"), justify="right",
            fg_color="#0a0f1e", border_color=theme.GLASS_EDGE, corner_radius=theme.RADIUS_SM,
        )
        search.pack(side="right", padx=(0, 8))

        self.only_known = ctk.CTkCheckBox(
            controls, text=theme.fa("فقط برنامه‌های پشتیبانی‌شده"), font=theme.font(11),
            checkbox_width=18, checkbox_height=18, corner_radius=6,
            fg_color=theme.ACCENT, command=self._apply_filter,
        )
        self.only_known.select()
        self.only_known.pack(side="right", padx=8)

        for label, command in (
            ("انتخاب همه", lambda: self._select_all(True)),
            ("لغو انتخاب", lambda: self._select_all(False)),
            ("↻ اسکن مجدد", self.refresh_apps),
        ):
            ctk.CTkButton(
                controls, text=theme.fa(label), font=theme.font(11), height=34, width=110,
                fg_color=theme.GLASS_LIGHT, hover_color=theme.GLASS_EDGE,
                corner_radius=theme.RADIUS_SM, command=command,
            ).pack(side="left", padx=4)

        stats = ctk.CTkFrame(page, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", pady=10)
        for index in range(3):
            stats.grid_columnconfigure(index, weight=1)
        self.stat_found = StatTile(stats, "برنامهٔ پیدا شده")
        self.stat_found.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self.stat_selected = StatTile(stats, "انتخاب شده")
        self.stat_selected.grid(row=0, column=1, sticky="ew", padx=6)
        self.stat_size = StatTile(stats, "حجم تقریبی دیتا")
        self.stat_size.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.apps_scroll = ctk.CTkScrollableFrame(
            page, fg_color=theme.GLASS, corner_radius=theme.RADIUS,
            border_width=1, border_color=theme.GLASS_EDGE,
        )
        self.apps_scroll.grid(row=2, column=0, sticky="nsew")
        for index in range(3):
            self.apps_scroll.grid_columnconfigure(index, weight=1, uniform="tile")

        self.apps_hint = ctk.CTkLabel(
            self.apps_scroll, text=theme.fa("در حال اسکن سیستم…"),
            font=theme.font(13), text_color=theme.TEXT_MUTED,
        )
        self.apps_hint.grid(row=0, column=0, columnspan=3, pady=40)

    # -------------------------------------------------- page 2: transfer
    def _page_transfer(self) -> None:
        page = self._new_page("transfer")
        page.grid_columnconfigure(0, weight=1)

        card = GlassCard(page)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        SectionTitle(
            card, "📤", "انتقال اطلاعات به فولدر 0",
            "دیتا و تنظیمات برنامه‌های انتخاب‌شده در Apps کپی و شورتکاتشان ساخته می‌شود.",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 12))

        note = ctk.CTkLabel(
            card,
            text=theme.fa(
                "نکته: قبل از انتقال، مرورگرها و ادیتورها را ببند. فایل‌های قفل‌شده "
                "رد می‌شوند و ممکن است پروفایل ناقص کپی شود."
            ),
            font=theme.font(11), text_color=theme.WARN, justify="right", wraplength=760, anchor="e",
        )
        note.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        self.shortcut_check = ctk.CTkCheckBox(
            card, text=theme.fa("ساخت شورتکات برنامه‌ها در فولدر Shortcuts"),
            font=theme.font(12), fg_color=theme.ACCENT, checkbox_width=18, checkbox_height=18,
        )
        if self.store.current.make_shortcuts:
            self.shortcut_check.select()
        self.shortcut_check.grid(row=2, column=0, sticky="e", padx=16, pady=(0, 12))

        self.transfer_button = ctk.CTkButton(
            card, text=theme.fa("شروع انتقال اطلاعات"), font=theme.font(14, "bold"),
            height=48, corner_radius=theme.RADIUS_SM,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self.start_transfer,
        )
        self.transfer_button.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))

        self.transfer_progress = ctk.CTkProgressBar(
            card, height=8, corner_radius=4, progress_color=theme.ACCENT, fg_color="#0a0f1e"
        )
        self.transfer_progress.set(0)
        self.transfer_progress.grid(row=4, column=0, sticky="ew", padx=16)

        self.transfer_status = ctk.CTkLabel(
            card, text=theme.fa("هنوز اجرا نشده"), font=theme.font(11),
            text_color=theme.TEXT_MUTED, anchor="e",
        )
        self.transfer_status.grid(row=5, column=0, sticky="ew", padx=16, pady=(6, 16))

        results = GlassCard(page)
        results.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        page.grid_rowconfigure(1, weight=1)
        results.grid_columnconfigure(0, weight=1)
        results.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            results, text=theme.fa("نتیجهٔ آخرین انتقال"), font=theme.font(12, "bold"),
            text_color=theme.TEXT_MUTED, anchor="e",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        self.transfer_results = ctk.CTkScrollableFrame(results, fg_color="transparent")
        self.transfer_results.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))
        self.transfer_results.grid_columnconfigure(0, weight=1)

    # ---------------------------------------------------- page 3: backup
    def _page_backup(self) -> None:
        page = self._new_page("backup")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        card = GlassCard(page)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        SectionTitle(
            card, "💾", "بکاپ و زمان‌بندی",
            "کل فولدر 0 فشرده و روی مقصد ذخیره می‌شود؛ قانون چرخه قدیمی‌ترین را حذف می‌کند.",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 12))

        config = self.store.current

        destination_row = ctk.CTkFrame(card, fg_color="transparent")
        destination_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        destination_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            destination_row, text=theme.fa("مقصد بکاپ:"), font=theme.font(12),
            text_color=theme.TEXT_MUTED, width=90, anchor="e",
        ).grid(row=0, column=2, padx=(0, 8))
        self.backup_dir_var = ctk.StringVar(value=config.backup_dir)
        ctk.CTkEntry(
            destination_row, textvariable=self.backup_dir_var, height=36, justify="left",
            fg_color="#0a0f1e", border_color=theme.GLASS_EDGE, corner_radius=theme.RADIUS_SM,
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(
            destination_row, text=theme.fa("انتخاب…"), width=90, height=36, font=theme.font(11),
            fg_color=theme.GLASS_LIGHT, hover_color=theme.GLASS_EDGE,
            corner_radius=theme.RADIUS_SM, command=self._choose_backup_dir,
        ).grid(row=0, column=0, padx=(8, 0))

        options = ctk.CTkFrame(card, fg_color="transparent")
        options.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))

        ctk.CTkLabel(
            options, text=theme.fa("تعداد نگهداری (قانون چرخه):"), font=theme.font(12),
            text_color=theme.TEXT_MUTED,
        ).pack(side="right", padx=(0, 8))
        self.keep_var = ctk.StringVar(value=str(config.keep_count))
        ctk.CTkEntry(
            options, textvariable=self.keep_var, width=64, height=34, justify="center",
            fg_color="#0a0f1e", border_color=theme.GLASS_EDGE, corner_radius=theme.RADIUS_SM,
        ).pack(side="right")

        ctk.CTkLabel(
            options, text=theme.fa("هر چند دقیقه:"), font=theme.font(12),
            text_color=theme.TEXT_MUTED,
        ).pack(side="right", padx=(24, 8))
        self.interval_var = ctk.StringVar(value=str(config.interval_minutes))
        ctk.CTkComboBox(
            options, values=list(INTERVAL_CHOICES), variable=self.interval_var,
            width=90, height=34, justify="center",
            fg_color="#0a0f1e", border_color=theme.GLASS_EDGE, button_color=theme.GLASS_LIGHT,
            corner_radius=theme.RADIUS_SM,
        ).pack(side="right")

        self.skip_unchanged_check = ctk.CTkCheckBox(
            options, text=theme.fa("اگر چیزی تغییر نکرده، بکاپ نگیر"), font=theme.font(11),
            fg_color=theme.ACCENT, checkbox_width=18, checkbox_height=18,
        )
        if config.skip_unchanged:
            self.skip_unchanged_check.select()
        self.skip_unchanged_check.pack(side="left")

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 10))
        buttons.grid_columnconfigure((0, 1), weight=1)

        self.backup_button = ctk.CTkButton(
            buttons, text=theme.fa("💾  بکاپ بگیر (همین حالا)"), font=theme.font(14, "bold"),
            height=48, corner_radius=theme.RADIUS_SM,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self.start_backup,
        )
        self.backup_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.schedule_button = ctk.CTkButton(
            buttons, text=theme.fa("⏱  فعال‌سازی زمان‌بندی"), font=theme.font(14, "bold"),
            height=48, corner_radius=theme.RADIUS_SM,
            fg_color=theme.GLASS_LIGHT, hover_color=theme.GLASS_EDGE,
            border_width=1, border_color=theme.ACCENT,
            command=self.toggle_schedule,
        )
        self.schedule_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.backup_progress = ctk.CTkProgressBar(
            card, height=8, corner_radius=4, progress_color=theme.OK, fg_color="#0a0f1e"
        )
        self.backup_progress.set(0)
        self.backup_progress.grid(row=4, column=0, sticky="ew", padx=16)
        self.backup_status = ctk.CTkLabel(
            card, text=theme.fa("زمان‌بندی خاموش است"), font=theme.font(11),
            text_color=theme.TEXT_MUTED, anchor="e",
        )
        self.backup_status.grid(row=5, column=0, sticky="ew", padx=16, pady=(6, 16))

        archives = GlassCard(page)
        archives.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        archives.grid_columnconfigure(0, weight=1)
        archives.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            archives, text=theme.fa("بکاپ‌های موجود روی مقصد"), font=theme.font(12, "bold"),
            text_color=theme.TEXT_MUTED, anchor="e",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        self.archive_list = ctk.CTkScrollableFrame(archives, fg_color="transparent")
        self.archive_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))
        self.archive_list.grid_columnconfigure(0, weight=1)

    # ----------------------------------------------------- page 4: cloud
    def _page_cloud(self) -> None:
        page = self._new_page("cloud")
        page.grid_columnconfigure(0, weight=1)

        card = GlassCard(page)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        SectionTitle(
            card, "☁️", "مقصد ابری (Railway)",
            "آدرس سرویس فایل‌منیجر و توکنش را وارد کن تا هر بکاپ آنجا هم آپلود شود.",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 12))

        config = self.store.current

        for row_index, (label, variable_name, value, secret) in enumerate(
            (
                ("آدرس سرویس", "cloud_url_var", config.cloud_url, False),
                ("توکن", "cloud_token_var", config.cloud_token, True),
            ),
            start=1,
        ):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.grid(row=row_index, column=0, sticky="ew", padx=16, pady=(0, 10))
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row, text=theme.fa(f"{label}:"), font=theme.font(12),
                text_color=theme.TEXT_MUTED, width=90, anchor="e",
            ).grid(row=0, column=1, padx=(0, 8))
            variable = ctk.StringVar(value=value)
            setattr(self, variable_name, variable)
            entry = ctk.CTkEntry(
                row, textvariable=variable, height=36, justify="left",
                fg_color="#0a0f1e", border_color=theme.GLASS_EDGE, corner_radius=theme.RADIUS_SM,
                placeholder_text="https://your-app.up.railway.app" if not secret else "",
            )
            if secret:
                entry.configure(show="•")
            entry.grid(row=0, column=0, sticky="ew")

        self.cloud_enabled_check = ctk.CTkCheckBox(
            card, text=theme.fa("بعد از هر بکاپ، فایل روی فضای ابری آپلود شود"),
            font=theme.font(12), fg_color=theme.ACCENT, checkbox_width=18, checkbox_height=18,
        )
        if config.cloud_enabled:
            self.cloud_enabled_check.select()
        self.cloud_enabled_check.grid(row=3, column=0, sticky="e", padx=16, pady=(2, 12))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))
        buttons.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(
            buttons, text=theme.fa("ذخیره تنظیمات"), height=42, font=theme.font(13, "bold"),
            corner_radius=theme.RADIUS_SM, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self.save_cloud_settings,
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ctk.CTkButton(
            buttons, text=theme.fa("تست اتصال"), height=42, font=theme.font(13),
            corner_radius=theme.RADIUS_SM, fg_color=theme.GLASS_LIGHT, hover_color=theme.GLASS_EDGE,
            command=self.test_cloud,
        ).grid(row=0, column=1, sticky="ew", padx=6)
        ctk.CTkButton(
            buttons, text=theme.fa("باز کردن فایل‌منیجر"), height=42, font=theme.font(13),
            corner_radius=theme.RADIUS_SM, fg_color=theme.GLASS_LIGHT, hover_color=theme.GLASS_EDGE,
            command=self.open_cloud,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.cloud_status = ctk.CTkLabel(
            card, text="", font=theme.font(11), text_color=theme.TEXT_MUTED, anchor="e"
        )
        self.cloud_status.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 16))

        guide = GlassCard(page)
        guide.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkLabel(
            guide,
            text=theme.fa(
                "مهم: روی Railway حتماً یک Volume به سرویس وصل کن و متغیر DATA_DIR را "
                "روی مسیر همان Volume (مثلاً /data) بگذار. بدون Volume، با هر بار "
                "دیپلوی مجدد تمام بکاپ‌های آپلودشده پاک می‌شوند."
            ),
            font=theme.font(11), text_color=theme.WARN, justify="right", wraplength=780, anchor="e",
        ).pack(fill="x", padx=16, pady=14)

    # --------------------------------------------------- page 5: restore
    def _page_restore(self) -> None:
        page = self._new_page("restore")
        page.grid_columnconfigure(0, weight=1)

        card = GlassCard(page)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        SectionTitle(
            card, "♻️", "بازگردانی از فایل بکاپ",
            "فایل zip را انتخاب کن، در مسیر دلخواه استخراج شود و در صورت نیاز دیتا سر جایش برگردد.",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 12))

        archive_row = ctk.CTkFrame(card, fg_color="transparent")
        archive_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        archive_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            archive_row, text=theme.fa("فایل بکاپ:"), font=theme.font(12),
            text_color=theme.TEXT_MUTED, width=90, anchor="e",
        ).grid(row=0, column=1, padx=(0, 8))
        self.restore_file_var = ctk.StringVar()
        ctk.CTkEntry(
            archive_row, textvariable=self.restore_file_var, height=36, justify="left",
            fg_color="#0a0f1e", border_color=theme.GLASS_EDGE, corner_radius=theme.RADIUS_SM,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            archive_row, text=theme.fa("انتخاب فایل zip"), width=130, height=36, font=theme.font(11),
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            corner_radius=theme.RADIUS_SM, command=self._choose_restore_file,
        ).grid(row=0, column=2, padx=(8, 0))

        target_row = ctk.CTkFrame(card, fg_color="transparent")
        target_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        target_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            target_row, text=theme.fa("مقصد استخراج:"), font=theme.font(12),
            text_color=theme.TEXT_MUTED, width=90, anchor="e",
        ).grid(row=0, column=1, padx=(0, 8))
        self.restore_target_var = ctk.StringVar(value=str(paths.root_dir().parent / "restored"))
        ctk.CTkEntry(
            target_row, textvariable=self.restore_target_var, height=36, justify="left",
            fg_color="#0a0f1e", border_color=theme.GLASS_EDGE, corner_radius=theme.RADIUS_SM,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            target_row, text=theme.fa("انتخاب…"), width=90, height=36, font=theme.font(11),
            fg_color=theme.GLASS_LIGHT, hover_color=theme.GLASS_EDGE,
            corner_radius=theme.RADIUS_SM, command=self._choose_restore_target,
        ).grid(row=0, column=2, padx=(8, 0))

        self.push_back_check = ctk.CTkCheckBox(
            card,
            text=theme.fa("بعد از استخراج، دیتای برنامه‌ها به مسیر اصلی ویندوز برگردانده شود"),
            font=theme.font(12), fg_color=theme.WARN, checkbox_width=18, checkbox_height=18,
        )
        self.push_back_check.grid(row=3, column=0, sticky="e", padx=16, pady=(0, 12))

        self.restore_button = ctk.CTkButton(
            card, text=theme.fa("شروع بازگردانی"), font=theme.font(14, "bold"),
            height=48, corner_radius=theme.RADIUS_SM,
            fg_color=theme.OK, hover_color="#28b487", text_color="#04140f",
            command=self.start_restore,
        )
        self.restore_button.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))

        self.restore_progress = ctk.CTkProgressBar(
            card, height=8, corner_radius=4, progress_color=theme.OK, fg_color="#0a0f1e"
        )
        self.restore_progress.set(0)
        self.restore_progress.grid(row=5, column=0, sticky="ew", padx=16)
        self.restore_status = ctk.CTkLabel(
            card, text=theme.fa("فایلی انتخاب نشده"), font=theme.font(11),
            text_color=theme.TEXT_MUTED, anchor="e",
        )
        self.restore_status.grid(row=6, column=0, sticky="ew", padx=16, pady=(6, 16))

    # ------------------------------------------------------------ actions
    def refresh_apps(self) -> None:
        self.apps_hint.configure(text=theme.fa("در حال اسکن سیستم…"))
        self._set_status("در حال اسکن…", theme.WARN)

        def worker() -> None:
            found = detect.scan(include_registry=True)
            for app in found:
                app.icon_path = icons.extract(app.exe_path)
                if app.data_paths:
                    detect.estimate_size(app)
            self._ui(lambda: self._render_apps(found))

        threading.Thread(target=worker, name="app-scan", daemon=True).start()

    def _render_apps(self, found: list[detect.DetectedApp]) -> None:
        self.detected = found
        for tile in self.tiles.values():
            tile.destroy()
        self.tiles.clear()
        self.apps_hint.grid_remove()

        for app in found:
            tile = AppTile(self.apps_scroll, app, self._on_tile_toggle)
            if app.est_size:
                tile.set_size_hint(f"{app.note or app.category} · {theme.human_size(app.est_size)}")
            self.tiles[app.key] = tile
            if app.key in self.selected_keys:
                tile.set_selected(True, notify=False)

        self.stat_found.set(str(len(found)))
        self._apply_filter()
        self._update_selection_stats()
        self._set_status("آماده", theme.OK)
        self.log_panel.append("ok", f"{len(found)} برنامه پیدا شد")

    def _apply_filter(self) -> None:
        query = self.search_var.get().strip().lower()
        known_only = bool(self.only_known.get())
        row = column = 0
        for app in self.detected:
            tile = self.tiles.get(app.key)
            if tile is None:
                continue
            visible = (not known_only or app.known) and (not query or query in app.name.lower())
            if visible:
                tile.grid(row=row, column=column, sticky="ew", padx=6, pady=6)
                column += 1
                if column == 3:
                    column = 0
                    row += 1
            else:
                tile.grid_remove()
        if row == 0 and column == 0:
            self.apps_hint.configure(text=theme.fa("چیزی با این فیلتر پیدا نشد"))
            self.apps_hint.grid()
        else:
            self.apps_hint.grid_remove()

    def _select_all(self, selected: bool) -> None:
        for app in self.detected:
            tile = self.tiles.get(app.key)
            if tile is None or not tile.winfo_ismapped():
                continue
            tile.set_selected(selected, notify=False)
            if selected:
                self.selected_keys.add(app.key)
            else:
                self.selected_keys.discard(app.key)
        self._persist_selection()
        self._update_selection_stats()

    def _on_tile_toggle(self, app, selected: bool) -> None:
        if selected:
            self.selected_keys.add(app.key)
        else:
            self.selected_keys.discard(app.key)
        self._persist_selection()
        self._update_selection_stats()

    def _persist_selection(self) -> None:
        self.store.update(selected_apps=sorted(self.selected_keys))

    def _selected_apps(self) -> list[detect.DetectedApp]:
        return [app for app in self.detected if app.key in self.selected_keys]

    def _update_selection_stats(self) -> None:
        chosen = self._selected_apps()
        self.stat_selected.set(str(len(chosen)))
        total = sum(app.est_size for app in chosen)
        self.stat_size.set(theme.human_size(total) if total else "—",
                           theme.WARN if total > 5 * 1024**3 else None)

    # ------------------------------------------------------------ step 2
    def start_transfer(self) -> None:
        chosen = self._selected_apps()
        if not chosen:
            messagebox.showwarning("Backup Suite", theme.fa("اول حداقل یک برنامه را انتخاب کن."))
            return

        self.transfer_button.configure(state="disabled")
        self._set_status("در حال انتقال…", theme.WARN)
        self.store.update(make_shortcuts=bool(self.shortcut_check.get()))

        def progress(message: str, fraction: float) -> None:
            self._ui(lambda: (
                self.transfer_progress.set(fraction),
                self.transfer_status.configure(text=theme.fa(message)),
            ))

        def worker() -> None:
            results = collector.collect(chosen, progress=progress)
            shortcut_count = 0
            if self.store.current.make_shortcuts:
                shortcut_count, _errors = shortcuts.create_all(chosen)
            self._ui(lambda: self._transfer_done(results, shortcut_count))

        threading.Thread(target=worker, name="transfer", daemon=True).start()

    def _transfer_done(self, results, shortcut_count: int) -> None:
        for child in self.transfer_results.winfo_children():
            child.destroy()

        total = 0
        for index, result in enumerate(results):
            total += result.bytes_copied
            row = GlassCard(self.transfer_results, corner_radius=theme.RADIUS_SM)
            row.grid(row=index, column=0, sticky="ew", pady=3, padx=4)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row, text="✅" if result.ok else "⚠️", font=theme.font(14), width=30
            ).grid(row=0, column=2, padx=(10, 4), pady=8)
            ctk.CTkLabel(
                row, text=result.app_name, font=theme.font(12, "bold"),
                text_color=theme.TEXT, anchor="e",
            ).grid(row=0, column=1, sticky="ew", pady=8)
            ctk.CTkLabel(
                row,
                text=theme.human_size(result.bytes_copied) if result.bytes_copied else theme.fa(result.message),
                font=theme.font(11), text_color=theme.TEXT_MUTED,
            ).grid(row=0, column=0, padx=12, pady=8)

        self.transfer_progress.set(1)
        self.transfer_status.configure(
            text=theme.fa(f"انتقال کامل شد - {theme.human_size(total)} · {shortcut_count} شورتکات"),
            text_color=theme.OK,
        )
        self.transfer_button.configure(state="normal")
        self.log_panel.append("ok", f"انتقال کامل شد: {theme.human_size(total)}")
        self._set_status("آماده", theme.OK)

    # ------------------------------------------------------------ step 3
    def _read_backup_settings(self) -> None:
        try:
            keep = max(1, int(self.keep_var.get()))
        except ValueError:
            keep = 10
            self.keep_var.set("10")
        try:
            interval = max(1, int(self.interval_var.get()))
        except ValueError:
            interval = 10
            self.interval_var.set("10")
        self.store.update(
            backup_dir=self.backup_dir_var.get().strip() or "D:\\",
            keep_count=keep,
            interval_minutes=interval,
            skip_unchanged=bool(self.skip_unchanged_check.get()),
        )

    def start_backup(self) -> None:
        self._read_backup_settings()
        self.backup_button.configure(state="disabled")
        self._set_status("در حال بکاپ…", theme.WARN)

        def progress(message: str, fraction: float) -> None:
            self._ui(lambda: (
                self.backup_progress.set(fraction),
                self.backup_status.configure(text=theme.fa(message), text_color=theme.TEXT_MUTED),
            ))

        def done(summary) -> None:
            self._ui(lambda: self._backup_done(summary))

        self.service.run_in_background(progress=progress, done=done)

    def _backup_done(self, summary) -> None:
        self.backup_button.configure(state="normal")
        self.backup_progress.set(1 if summary.ok else 0)
        self.backup_status.configure(
            text=theme.fa(summary.message),
            text_color=theme.OK if summary.ok else theme.BAD,
        )
        self._refresh_archive_list()
        self._set_status("آماده", theme.OK)

    def toggle_schedule(self) -> None:
        self._read_backup_settings()
        if self.service.scheduler.is_running:
            self.service.stop_schedule()
            self.schedule_button.configure(
                text=theme.fa("⏱  فعال‌سازی زمان‌بندی"),
                fg_color=theme.GLASS_LIGHT, border_color=theme.ACCENT,
            )
        else:
            self.service.start_schedule(self.store.current.interval_minutes)
            self.schedule_button.configure(
                text=theme.fa("⏹  توقف زمان‌بندی"),
                fg_color="#3b1f2b", border_color=theme.BAD,
            )

    def _refresh_archive_list(self) -> None:
        for child in self.archive_list.winfo_children():
            child.destroy()
        archives = self.service.archives_on_disk()
        if not archives:
            ctk.CTkLabel(
                self.archive_list, text=theme.fa("هنوز بکاپی ساخته نشده است"),
                font=theme.font(12), text_color=theme.TEXT_MUTED,
            ).grid(row=0, column=0, pady=24)
            return

        keep = self.store.current.keep_count
        for index, archive in enumerate(archives):
            try:
                size = archive.stat().st_size
            except OSError:
                continue
            row = GlassCard(self.archive_list, corner_radius=theme.RADIUS_SM)
            row.grid(row=index, column=0, sticky="ew", pady=3, padx=4)
            row.grid_columnconfigure(1, weight=1)
            newest = index == 0
            ctk.CTkLabel(row, text="📦", font=theme.font(15), width=30).grid(
                row=0, column=2, padx=(10, 4), pady=8
            )
            ctk.CTkLabel(
                row, text=archive.name, font=theme.font(12, "bold"),
                text_color=theme.OK if newest else theme.TEXT, anchor="e",
            ).grid(row=0, column=1, sticky="ew", pady=8)
            label = theme.human_size(size)
            if index >= keep:
                label = theme.fa("خارج از چرخه") + " · " + label
            ctk.CTkLabel(
                row, text=label, font=theme.font(11), text_color=theme.TEXT_MUTED
            ).grid(row=0, column=0, padx=12, pady=8)

    # ------------------------------------------------------------ step 4
    def save_cloud_settings(self) -> None:
        self.store.update(
            cloud_url=self.cloud_url_var.get().strip(),
            cloud_token=self.cloud_token_var.get().strip(),
            cloud_enabled=bool(self.cloud_enabled_check.get()),
        )
        self.cloud_status.configure(text=theme.fa("تنظیمات ذخیره شد"), text_color=theme.OK)
        self.log_panel.append("ok", "تنظیمات فضای ابری ذخیره شد")

    def test_cloud(self) -> None:
        url = self.cloud_url_var.get().strip()
        token = self.cloud_token_var.get().strip()
        self.cloud_status.configure(text=theme.fa("در حال تست…"), text_color=theme.TEXT_MUTED)

        def worker() -> None:
            ok, message = uploader.test_connection(url, token)
            self._ui(lambda: self.cloud_status.configure(
                text=theme.fa(message), text_color=theme.OK if ok else theme.BAD
            ))
            self._ui(lambda: self.log_panel.append("ok" if ok else "error", message))

        threading.Thread(target=worker, name="cloud-test", daemon=True).start()

    def open_cloud(self) -> None:
        url = self.cloud_url_var.get().strip()
        if url:
            webbrowser.open(url if url.startswith("http") else f"https://{url}")

    # ------------------------------------------------------------ step 5
    def _choose_restore_file(self) -> None:
        chosen = filedialog.askopenfilename(
            title="انتخاب فایل بکاپ", filetypes=[("Zip archive", "*.zip"), ("All files", "*.*")]
        )
        if not chosen:
            return
        self.restore_file_var.set(chosen)
        ok, message, count, size = restore.inspect(chosen)
        self.restore_status.configure(
            text=theme.fa(f"{message} - {count:,} فایل، {theme.human_size(size)}")
            if ok else theme.fa(message),
            text_color=theme.OK if ok else theme.BAD,
        )

    def _choose_restore_target(self) -> None:
        chosen = filedialog.askdirectory(title="مقصد استخراج")
        if chosen:
            self.restore_target_var.set(chosen)

    def start_restore(self) -> None:
        archive = self.restore_file_var.get().strip()
        target = self.restore_target_var.get().strip()
        if not archive or not Path(archive).exists():
            messagebox.showwarning("Backup Suite", theme.fa("اول فایل بکاپ را انتخاب کن."))
            return

        push_back = bool(self.push_back_check.get())
        if push_back and not messagebox.askyesno(
            "Backup Suite",
            theme.fa(
                "دیتای برنامه‌ها روی مسیرهای اصلی ویندوز بازنویسی می‌شود.\n"
                "قبل از ادامه همهٔ آن برنامه‌ها را ببند. ادامه می‌دهی؟"
            ),
        ):
            return

        self.restore_button.configure(state="disabled")
        self._set_status("در حال بازگردانی…", theme.WARN)

        def progress(message: str, fraction: float) -> None:
            self._ui(lambda: (
                self.restore_progress.set(fraction),
                self.restore_status.configure(text=theme.fa(message), text_color=theme.TEXT_MUTED),
            ))

        def worker() -> None:
            result = restore.extract(archive, target, progress)
            report: list[str] = []
            if result.ok and push_back:
                extracted_root = Path(target) / "0"
                if not extracted_root.exists():
                    extracted_root = Path(target)
                report = restore.push_back(extracted_root, progress)
            self._ui(lambda: self._restore_done(result, report))

        threading.Thread(target=worker, name="restore", daemon=True).start()

    def _restore_done(self, result, report: list[str]) -> None:
        self.restore_button.configure(state="normal")
        self.restore_progress.set(1 if result.ok else 0)
        self.restore_status.configure(
            text=theme.fa(result.message), text_color=theme.OK if result.ok else theme.BAD
        )
        self.log_panel.append("ok" if result.ok else "error", result.message)
        for line in report:
            self.log_panel.append("info", line)
        self._set_status("آماده", theme.OK)

    # ------------------------------------------------------------- misc
    def _choose_backup_dir(self) -> None:
        chosen = filedialog.askdirectory(title="مقصد بکاپ")
        if chosen:
            self.backup_dir_var.set(chosen)
            self._read_backup_settings()
            self._refresh_archive_list()

    def _open_root(self) -> None:
        import subprocess
        import sys as _sys

        target = str(paths.root_dir())
        try:
            if _sys.platform == "win32":
                subprocess.Popen(["explorer", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except OSError as exc:
            self.log_panel.append("warn", f"باز کردن فولدر ممکن نشد: {exc}")

    def _ui(self, action) -> None:
        """Run ``action`` on the Tk thread, tolerating a closed window.

        Worker threads outlive the window when the user quits mid-run; without
        this guard Tk raises from the thread and the traceback lands in the log
        instead of being ignored as the harmless race it is.
        """
        try:
            self.after(0, action)
        except (RuntimeError, tkinter.TclError):
            log.debug("dropped a UI update - window is gone")

    def _set_status(self, text: str, color: str) -> None:
        self.status_pill.configure(text=theme.fa(text), text_color=color)

    def _on_event(self, level: str, message: str) -> None:
        self._ui(lambda: self.log_panel.append(level, message))

    def _tick(self) -> None:
        """Once a second: keep the schedule countdown honest."""
        if self.service.scheduler.is_running:
            remaining = int(self.service.scheduler.seconds_until_next)
            minutes, seconds = divmod(max(0, remaining), 60)
            state = "در حال اجرا" if self.service.scheduler.job_in_progress else "بکاپ بعدی"
            self.backup_status.configure(
                text=theme.fa(f"{state}: {minutes:02d}:{seconds:02d}"), text_color=theme.ACCENT
            )
        self.after(1000, self._tick)

    def _on_close(self) -> None:
        if self.service.is_busy and not messagebox.askyesno(
            "Backup Suite", theme.fa("یک بکاپ در حال اجراست. بستن برنامه آن را نیمه‌کاره می‌گذارد. ببندم؟")
        ):
            return
        self.service.shutdown()
        self.store.save()
        self.destroy()
