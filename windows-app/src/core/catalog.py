"""What we know about the apps worth rescuing.

Installed programs cannot be "backed up" in any meaningful way - a Windows
install is glued to the registry and to system DLLs. What actually hurts to
lose is the *data*: browser profiles, editor settings, extensions, agent
histories, SSH keys, git config. So for every known app we record where that
data lives, and we copy those trees into 0\\Apps.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DataSource:
    src: str          # path with environment variables, e.g. %APPDATA%\Cursor
    dest: str         # sub-path under 0\Apps\<app>\
    optional: bool = True


@dataclass(frozen=True)
class KnownApp:
    key: str
    name: str
    category: str
    emoji: str
    exe_candidates: tuple[str, ...] = ()
    registry_names: tuple[str, ...] = ()
    data: tuple[DataSource, ...] = ()
    excludes: tuple[str, ...] = ()
    note: str = ""
    warning: str = ""   # shown in amber on the card - what will NOT come back


# Directories that are pure cache. Copying them wastes minutes and gigabytes
# and restoring them is worthless - every one of these is rebuilt on launch.
CHROMIUM_EXCLUDES = (
    "Cache", "Code Cache", "GPUCache", "GrShaderCache", "ShaderCache",
    "Service Worker/CacheStorage", "Service Worker/ScriptCache",
    "component_crx_cache", "extensions_crx_cache", "Crashpad",
    "CacheStorage", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
    "optimization_guide_model_store", "Safe Browsing", "PnaclTranslationCache",
)

ELECTRON_EXCLUDES = (
    "Cache", "Code Cache", "GPUCache", "CachedData", "CachedExtensions",
    "Crashpad", "logs", "ShaderCache", "DawnCache", "blob_storage",
)

# Chromium and Firefox seal cookies and saved passwords with a key that
# Windows ties to the machine and user account. The files copy fine; they just
# will not decrypt anywhere else. Better to say so on the card than to let
# someone discover it on the day their drive died.
DPAPI_WARNING = (
    "کوکی و پسورد روی ویندوز جدید باز نمی‌شوند (رمزگذاری DPAPI) - "
    "بوکمارک، تاریخچه و اکستنشن‌ها برمی‌گردند"
)

CATALOG: tuple[KnownApp, ...] = (
    # ---------------------------------------------------------- browsers
    KnownApp(
        key="chrome",
        name="Google Chrome",
        category="مرورگر",
        emoji="🌐",
        exe_candidates=(
            r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
            r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        ),
        registry_names=("Google Chrome",),
        data=(DataSource(r"%LOCALAPPDATA%\Google\Chrome\User Data", "UserData"),),
        excludes=CHROMIUM_EXCLUDES,
        note="پروفایل، بوکمارک، تاریخچه، اکستنشن‌ها",
        warning=DPAPI_WARNING,
    ),
    KnownApp(
        key="edge",
        name="Microsoft Edge",
        category="مرورگر",
        emoji="🌊",
        exe_candidates=(
            r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
            r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
        ),
        registry_names=("Microsoft Edge",),
        data=(DataSource(r"%LOCALAPPDATA%\Microsoft\Edge\User Data", "UserData"),),
        excludes=CHROMIUM_EXCLUDES,
        warning=DPAPI_WARNING,
    ),
    KnownApp(
        key="brave",
        name="Brave",
        category="مرورگر",
        emoji="🦁",
        exe_candidates=(
            r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
        ),
        registry_names=("Brave",),
        data=(DataSource(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data", "UserData"),),
        excludes=CHROMIUM_EXCLUDES,
        warning=DPAPI_WARNING,
    ),
    KnownApp(
        key="firefox",
        name="Mozilla Firefox",
        category="مرورگر",
        emoji="🦊",
        exe_candidates=(
            r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe",
            r"%PROGRAMFILES(X86)%\Mozilla Firefox\firefox.exe",
        ),
        registry_names=("Mozilla Firefox",),
        data=(DataSource(r"%APPDATA%\Mozilla\Firefox", "Profiles"),),
        excludes=("cache2", "startupCache", "thumbnails", "shader-cache"),
        warning=DPAPI_WARNING,
    ),

    # ------------------------------------------------------ editors / IDEs
    KnownApp(
        key="cursor",
        name="Cursor",
        category="ادیتور",
        emoji="🖱️",
        exe_candidates=(
            r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe",
            r"%PROGRAMFILES%\Cursor\Cursor.exe",
        ),
        registry_names=("Cursor",),
        data=(
            DataSource(r"%APPDATA%\Cursor\User", "User"),
            DataSource(r"%USERPROFILE%\.cursor", "dot-cursor"),
        ),
        excludes=ELECTRON_EXCLUDES + ("workspaceStorage/*/state.vscdb.backup",),
        note="تنظیمات، کی‌بایندینگ، اکستنشن‌ها، چت‌ها",
        warning="لاگین خود Cursor در Credential Manager ویندوز است و منتقل نمی‌شود",
    ),
    KnownApp(
        key="vscode",
        name="Visual Studio Code",
        category="ادیتور",
        emoji="🧩",
        exe_candidates=(
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
            r"%PROGRAMFILES%\Microsoft VS Code\Code.exe",
        ),
        registry_names=("Microsoft Visual Studio Code",),
        data=(
            DataSource(r"%APPDATA%\Code\User", "User"),
            DataSource(r"%USERPROFILE%\.vscode\extensions", "extensions"),
        ),
        excludes=ELECTRON_EXCLUDES,
    ),
    KnownApp(
        key="windsurf",
        name="Windsurf",
        category="ادیتور",
        emoji="🏄",
        exe_candidates=(r"%LOCALAPPDATA%\Programs\Windsurf\Windsurf.exe",),
        registry_names=("Windsurf",),
        data=(
            DataSource(r"%APPDATA%\Windsurf\User", "User"),
            DataSource(r"%USERPROFILE%\.codeium", "dot-codeium"),
        ),
        excludes=ELECTRON_EXCLUDES,
    ),
    KnownApp(
        key="sublime",
        name="Sublime Text",
        category="ادیتور",
        emoji="📝",
        exe_candidates=(r"%PROGRAMFILES%\Sublime Text\sublime_text.exe",),
        registry_names=("Sublime Text",),
        data=(DataSource(r"%APPDATA%\Sublime Text\Packages\User", "User"),),
    ),
    KnownApp(
        key="notepadpp",
        name="Notepad++",
        category="ادیتور",
        emoji="🗒️",
        exe_candidates=(
            r"%PROGRAMFILES%\Notepad++\notepad++.exe",
            r"%PROGRAMFILES(X86)%\Notepad++\notepad++.exe",
        ),
        registry_names=("Notepad++",),
        data=(DataSource(r"%APPDATA%\Notepad++", "config"),),
    ),

    # ------------------------------------------------------- AI / agents
    KnownApp(
        key="claude-desktop",
        name="Claude",
        category="هوش مصنوعی",
        emoji="🤖",
        exe_candidates=(r"%LOCALAPPDATA%\AnthropicClaude\claude.exe",),
        registry_names=("Claude",),
        data=(DataSource(r"%APPDATA%\Claude", "AppData"),),
        excludes=ELECTRON_EXCLUDES,
        note="تنظیمات و MCP serverها",
    ),
    KnownApp(
        key="claude-code",
        name="Claude Code (CLI)",
        category="هوش مصنوعی",
        emoji="⌨️",
        exe_candidates=(
            r"%APPDATA%\npm\claude.cmd",
            r"%LOCALAPPDATA%\Programs\claude\claude.exe",
        ),
        data=(
            DataSource(r"%USERPROFILE%\.claude", "dot-claude"),
            DataSource(r"%USERPROFILE%\.claude.json", "claude.json"),
        ),
        excludes=("shell-snapshots", "statsig", "todos"),
        note="تاریخچهٔ گفتگوها، CLAUDE.md، اسکیل‌ها",
    ),
    KnownApp(
        key="opencode",
        name="OpenCode",
        category="هوش مصنوعی",
        emoji="🧠",
        exe_candidates=(
            r"%APPDATA%\npm\opencode.cmd",
            r"%LOCALAPPDATA%\Programs\opencode\opencode.exe",
            r"%USERPROFILE%\.opencode\bin\opencode.exe",
        ),
        data=(
            DataSource(r"%USERPROFILE%\.config\opencode", "config"),
            DataSource(r"%LOCALAPPDATA%\opencode", "local-data"),
            DataSource(r"%USERPROFILE%\.local\share\opencode", "share"),
        ),
        excludes=("cache", "log", "bin"),
    ),
    KnownApp(
        key="ollama",
        name="Ollama",
        category="هوش مصنوعی",
        emoji="🦙",
        exe_candidates=(r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe",),
        registry_names=("Ollama",),
        data=(DataSource(r"%USERPROFILE%\.ollama", "dot-ollama"),),
        excludes=("models",),
        note="مدل‌ها به‌خاطر حجم کپی نمی‌شوند",
    ),

    # --------------------------------------------------------- dev tools
    KnownApp(
        key="git",
        name="Git",
        category="ابزار توسعه",
        emoji="🌿",
        exe_candidates=(
            r"%PROGRAMFILES%\Git\bin\git.exe",
            r"%PROGRAMFILES%\Git\cmd\git.exe",
        ),
        registry_names=("Git",),
        data=(
            DataSource(r"%USERPROFILE%\.gitconfig", "gitconfig"),
            DataSource(r"%USERPROFILE%\.ssh", "ssh"),
        ),
        note="کلیدهای SSH و تنظیمات گیت",
    ),
    KnownApp(
        key="windows-terminal",
        name="Windows Terminal",
        category="ابزار توسعه",
        emoji="🖥️",
        exe_candidates=(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe",),
        data=(
            DataSource(
                r"%LOCALAPPDATA%\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState",
                "settings",
            ),
        ),
    ),
    KnownApp(
        key="powershell",
        name="PowerShell Profile",
        category="ابزار توسعه",
        emoji="⚡",
        exe_candidates=(r"%SYSTEMROOT%\System32\WindowsPowerShell\v1.0\powershell.exe",),
        data=(
            DataSource(r"%USERPROFILE%\Documents\WindowsPowerShell", "WindowsPowerShell"),
            DataSource(r"%USERPROFILE%\Documents\PowerShell", "PowerShell"),
        ),
    ),
    KnownApp(
        key="nodejs",
        name="Node.js / npm",
        category="ابزار توسعه",
        emoji="📦",
        exe_candidates=(r"%PROGRAMFILES%\nodejs\node.exe",),
        registry_names=("Node.js",),
        data=(
            DataSource(r"%USERPROFILE%\.npmrc", "npmrc"),
            DataSource(r"%APPDATA%\npm-cache\_logs", "npm-logs"),
        ),
        excludes=("npm-logs",),
    ),
    KnownApp(
        key="python",
        name="Python",
        category="ابزار توسعه",
        emoji="🐍",
        exe_candidates=(
            r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe",
            r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe",
        ),
        registry_names=("Python 3",),
        data=(DataSource(r"%APPDATA%\pip\pip.ini", "pip.ini"),),
    ),
    KnownApp(
        key="docker",
        name="Docker Desktop",
        category="ابزار توسعه",
        emoji="🐳",
        exe_candidates=(r"%PROGRAMFILES%\Docker\Docker\Docker Desktop.exe",),
        registry_names=("Docker Desktop",),
        data=(DataSource(r"%USERPROFILE%\.docker", "dot-docker"),),
        excludes=("cache", "desktop"),
    ),
    KnownApp(
        key="postman",
        name="Postman",
        category="ابزار توسعه",
        emoji="📮",
        exe_candidates=(r"%LOCALAPPDATA%\Postman\Postman.exe",),
        registry_names=("Postman",),
        data=(DataSource(r"%APPDATA%\Postman", "AppData"),),
        excludes=ELECTRON_EXCLUDES + ("files",),
    ),

    KnownApp(
        key="dev-credentials",
        name="توکن‌ها و کلیدهای توسعه",
        category="ابزار توسعه",
        emoji="🔑",
        data=(
            DataSource(r"%USERPROFILE%\.netrc", "netrc"),
            DataSource(r"%USERPROFILE%\.config\gh", "github-cli"),
            DataSource(r"%USERPROFILE%\.aws", "aws"),
            DataSource(r"%USERPROFILE%\.kube\config", "kube-config"),
            DataSource(r"%USERPROFILE%\.pypirc", "pypirc"),
            DataSource(r"%USERPROFILE%\.cargo\credentials.toml", "cargo-credentials"),
            DataSource(r"%USERPROFILE%\.gradle\gradle.properties", "gradle-properties"),
        ),
        note="این‌ها فایل ساده‌اند و روی ویندوز جدید کار می‌کنند",
        warning="داخل بکاپ به‌صورت رمزنشده هستند - فایل zip را جایی نفرست",
    ),

    # ---------------------------------------------------------- messaging
    KnownApp(
        key="telegram",
        name="Telegram Desktop",
        category="ارتباطات",
        emoji="✈️",
        exe_candidates=(r"%APPDATA%\Telegram Desktop\Telegram.exe",),
        registry_names=("Telegram Desktop",),
        data=(DataSource(r"%APPDATA%\Telegram Desktop\tdata", "tdata"),),
        excludes=("user_data/cache", "emoji"),
    ),
    KnownApp(
        key="discord",
        name="Discord",
        category="ارتباطات",
        emoji="💬",
        exe_candidates=(r"%LOCALAPPDATA%\Discord\Update.exe",),
        registry_names=("Discord",),
        data=(DataSource(r"%APPDATA%\discord", "AppData"),),
        excludes=ELECTRON_EXCLUDES,
    ),
)


BY_KEY: dict[str, KnownApp] = {app.key: app for app in CATALOG}


def categories() -> list[str]:
    seen: list[str] = []
    for app in CATALOG:
        if app.category not in seen:
            seen.append(app.category)
    return seen
