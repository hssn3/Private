"""Reusable pieces of the interface."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image

from . import theme


class GlassCard(ctk.CTkFrame):
    """A frosted panel. Tk cannot really blur, so the illusion comes from a
    translucent-looking fill, a hairline border and a generous corner radius
    sitting on top of the window's own acrylic backdrop."""

    def __init__(self, master, raised: bool = False, **kwargs):
        kwargs.setdefault("fg_color", theme.GLASS_LIGHT if raised else theme.GLASS)
        kwargs.setdefault("corner_radius", theme.RADIUS)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.GLASS_EDGE)
        super().__init__(master, **kwargs)


class SectionTitle(ctk.CTkFrame):
    def __init__(self, master, icon: str, title: str, subtitle: str = "", **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text=icon, font=theme.font(22)).pack(side="right", padx=(0, 10))
        text_column = ctk.CTkFrame(row, fg_color="transparent")
        text_column.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(
            text_column, text=theme.fa(title), font=theme.font(17, "bold"),
            text_color=theme.TEXT, anchor="e",
        ).pack(fill="x")
        if subtitle:
            ctk.CTkLabel(
                text_column, text=theme.fa(subtitle), font=theme.font(12),
                text_color=theme.TEXT_MUTED, anchor="e",
            ).pack(fill="x", pady=(2, 0))


class StatTile(GlassCard):
    def __init__(self, master, label: str, value: str = "—", **kwargs):
        super().__init__(master, corner_radius=theme.RADIUS_SM, **kwargs)
        ctk.CTkLabel(
            self, text=theme.fa(label), font=theme.font(11),
            text_color=theme.TEXT_MUTED, anchor="e",
        ).pack(fill="x", padx=14, pady=(12, 0))
        self._value = ctk.CTkLabel(
            self, text=value, font=theme.font(18, "bold"), text_color=theme.TEXT, anchor="e"
        )
        self._value.pack(fill="x", padx=14, pady=(2, 12))

    def set(self, value: str, color: str | None = None) -> None:
        self._value.configure(text=value, text_color=color or theme.TEXT)


class AppTile(ctk.CTkFrame):
    """One selectable app in the picker grid."""

    def __init__(self, master, app, on_toggle: Callable[[object, bool], None], **kwargs):
        kwargs.setdefault("fg_color", theme.GLASS)
        kwargs.setdefault("corner_radius", theme.RADIUS_SM)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.GLASS_EDGE)
        super().__init__(master, **kwargs)
        self.app = app
        self._on_toggle = on_toggle
        self.selected = False
        self._image = None

        self.grid_columnconfigure(1, weight=1)

        # Icon: the real exe icon when we could extract one, else the emoji.
        icon_holder = ctk.CTkFrame(self, fg_color="transparent", width=46, height=46)
        icon_holder.grid(row=0, column=2, rowspan=2, padx=(12, 6), pady=12)
        icon_holder.grid_propagate(False)
        self._icon_label = ctk.CTkLabel(icon_holder, text="", width=46, height=46)
        self._icon_label.pack(expand=True)
        self._set_icon(app)

        self._name = ctk.CTkLabel(
            self, text=theme.fa(app.name) if _has_persian(app.name) else app.name,
            font=theme.font(13, "bold"), text_color=theme.TEXT, anchor="e",
        )
        self._name.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=(12, 0))

        detail = app.note or app.category
        self._detail = ctk.CTkLabel(
            self, text=theme.fa(detail), font=theme.font(10),
            text_color=theme.TEXT_DIM, anchor="e",
        )
        self._detail.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 0 if app.warning else 12))

        # Say up front what this app will NOT bring back, rather than letting
        # someone find out on the day they need it.
        self._warning = None
        if app.warning:
            self._warning = ctk.CTkLabel(
                self, text=theme.fa("⚠ " + app.warning), font=theme.font(9),
                text_color=theme.WARN, anchor="e", justify="right", wraplength=230,
            )
            self._warning.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(2, 10))

        self._check = ctk.CTkLabel(self, text="○", font=theme.font(17), text_color=theme.TEXT_DIM)
        self._check.grid(row=0, column=0, rowspan=2, padx=(12, 4))

        clickable = [self, self._name, self._detail, self._check, self._icon_label, icon_holder]
        if self._warning is not None:
            clickable.append(self._warning)
        for widget in clickable:
            widget.bind("<Button-1>", self._clicked)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def _set_icon(self, app) -> None:
        if app.icon_path and Path(app.icon_path).exists():
            try:
                image = Image.open(app.icon_path)
                self._image = ctk.CTkImage(light_image=image, dark_image=image, size=(36, 36))
                self._icon_label.configure(image=self._image, text="")
                return
            except Exception:  # noqa: BLE001 - fall through to the emoji
                pass
        self._icon_label.configure(text=app.emoji, font=theme.font(24), image=None)

    def set_size_hint(self, text: str) -> None:
        self._detail.configure(text=theme.fa(text))

    def set_selected(self, selected: bool, notify: bool = True) -> None:
        self.selected = selected
        self.configure(
            border_color=theme.ACCENT if selected else theme.GLASS_EDGE,
            fg_color=theme.GLASS_LIGHT if selected else theme.GLASS,
        )
        self._check.configure(
            text="●" if selected else "○",
            text_color=theme.ACCENT if selected else theme.TEXT_DIM,
        )
        if notify:
            self._on_toggle(self.app, selected)

    def _clicked(self, _event=None) -> None:
        self.set_selected(not self.selected)

    def _enter(self, _event=None) -> None:
        if not self.selected:
            self.configure(fg_color=theme.GLASS_LIGHT)

    def _leave(self, _event=None) -> None:
        if not self.selected:
            self.configure(fg_color=theme.GLASS)


class LogPanel(ctk.CTkTextbox):
    """Append-only activity log with colour per severity."""

    COLORS = {
        "info": theme.TEXT_MUTED,
        "ok": theme.OK,
        "warn": theme.WARN,
        "error": theme.BAD,
    }

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", "#0a0f1e")
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.GLASS_EDGE)
        kwargs.setdefault("corner_radius", theme.RADIUS_SM)
        kwargs.setdefault("font", theme.font(11))
        kwargs.setdefault("wrap", "word")
        super().__init__(master, **kwargs)
        # CTkTextbox delegates tag_config to the inner Text widget; reach the
        # widget directly if this build does not expose it.
        tag_config = getattr(self, "tag_config", None) or self._textbox.tag_config
        for level, color in self.COLORS.items():
            tag_config(level, foreground=color)
        self.configure(state="disabled")

    def append(self, level: str, message: str) -> None:
        from datetime import datetime

        stamp = datetime.now().strftime("%H:%M:%S")
        body = theme.fa(message) if _has_persian(message) else message
        self.configure(state="normal")
        self.insert("end", f"{stamp}  {body}\n", level if level in self.COLORS else "info")
        self.see("end")
        self.configure(state="disabled")


def _has_persian(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)
