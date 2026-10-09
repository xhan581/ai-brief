"""Desktop app for the AI build-out brief.

Run it:     python app.py          (from the ai_brief folder, with the .venv active)
Build .exe: build_app.bat          (puts "AI Brief.exe" in dist/; keep the exe inside ai_brief/)

The app is a front end over the same scripts the GitHub Action runs:
run_brief.py (fetch -> Claude writes -> render). It never edits those scripts.
Settings (token, python path, SEC contact) are stored by the OS for your user
account, never in the repo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

def find_root() -> Path:
    """The project folder: the nearest folder at or above this file/exe that holds run_brief.py."""
    start = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    for p in (start, *start.parents):
        if (p / "run_brief.py").exists():
            return p
    return start


ROOT = find_root()
settings = QSettings("ai-brief", "desktop")

MODELS = ["(default)", "claude-opus-5-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"]

STYLE = """
* { font-family: "IBM Plex Sans", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow, QWidget { background: #141615; color: #e8e9e6; }
QLabel, QCheckBox { background: transparent; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #4a4f4c; border-radius: 3px; background: #0f1110; }
QCheckBox::indicator:checked { background: #1d5fbf; border-color: #1d5fbf; }
QScrollBar:vertical { background: transparent; width: 10px; } QScrollBar::handle:vertical { background: #343836; border-radius: 5px; min-height: 30px; } QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
#sidebar { background: #0f1110; border-right: 1px solid #262927; }
#sidebar::item { padding: 11px 18px; border: none; color: #a9ada9; }
#sidebar::item:selected { background: #1d2120; color: #ffffff; border-left: 3px solid #7fb0f0; }
#sidebar::item:hover:!selected { background: #171a19; }
#title { font-size: 18px; font-weight: 600; color: #ffffff; }
#subtitle { color: #8d918c; }
#h2 { font-size: 11px; font-weight: 600; letter-spacing: 1px; color: #8d918c; margin-top: 8px; }
QPushButton { background: #22262418; border: 1px solid #343836; border-radius: 6px; padding: 7px 14px; color: #e8e9e6; }
QPushButton:hover { background: #262a28; border-color: #4a4f4c; }
QPushButton:pressed { background: #1b1e1d; }
QPushButton:disabled { color: #5c605e; border-color: #262927; }
QPushButton#primary { background: #1d5fbf; border-color: #1d5fbf; color: white; font-weight: 600; padding: 10px 22px; font-size: 14px; }
QPushButton#primary:hover { background: #2a6fd6; }
QPushButton#primary:disabled { background: #22312f; border-color: #22312f; color: #6a7370; }
QPushButton#danger { border-color: #7a2f2f; color: #e66767; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit { background: #0f1110; border: 1px solid #343836; border-radius: 6px; padding: 6px 8px; color: #e8e9e6; selection-background-color: #1d5fbf; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #7fb0f0; }
QPlainTextEdit#log { font-family: "IBM Plex Mono", Consolas, monospace; font-size: 12px; color: #c3c2b7; }
QPlainTextEdit#editor { font-family: "IBM Plex Mono", Consolas, monospace; font-size: 12.5px; line-height: 1.5; }
QListWidget#issues { background: #0f1110; border: 1px solid #262927; border-radius: 6px; }
QListWidget#issues::item { padding: 10px 12px; border-bottom: 1px solid #1d2120; }
QListWidget#issues::item:selected { background: #1d2120; color: white; }
QFrame#card { background: #0f1110; border: 1px solid #262927; border-radius: 8px; }
QLabel#ok { color: #35c235; } QLabel#warn { color: #fab219; } QLabel#bad { color: #e66767; }
QLabel#step { color: #8d918c; } QLabel#step_on { color: #ffffff; font-weight: 600; } QLabel#step_done { color: #35c235; }
"""


def h2(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setObjectName("h2")
    return lab


def card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    return f, lay


def python_path() -> str:
    saved = settings.value("python", "")
    if saved and Path(saved).exists():
        return saved
    cand = ROOT / ".venv" / "Scripts" / "python.exe"
    if cand.exists():
        return str(cand)
    cand = ROOT / ".venv" / "bin" / "python"
    if cand.exists():
        return str(cand)
    return sys.executable if not getattr(sys, "frozen", False) else "python"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class RunPage(QWidget):
    def __init__(self, window: "Main"):
        super().__init__()
        self.window = window
        self.proc: QProcess | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)

        t = QLabel("Run this week's brief")
        t.setObjectName("title")
        lay.addWidget(t)
        s = QLabel("Pulls the numbers, has Claude read the week and write the brief, then renders the page.")
        s.setObjectName("subtitle")
        lay.addWidget(s)

        box, bl = card()
        row = QHBoxLayout()
        row.setSpacing(18)
        self.date = QLineEdit()
        self.date.setPlaceholderText("today")
        self.date.setFixedWidth(110)
        self.model = QComboBox()
        self.model.addItems(MODELS)
        self.model.setCurrentText(settings.value("model", "(default)"))
        self.turns = QSpinBox()
        self.turns.setRange(10, 300)
        self.turns.setValue(int(settings.value("max_turns", 80)))
        self.no_agent = QCheckBox("Numbers and charts only (skip Claude)")
        for label, w in (("Issue date", self.date), ("Model", self.model), ("Max turns", self.turns)):
            col = QVBoxLayout()
            col.setSpacing(3)
            col.addWidget(h2(label))
            col.addWidget(w)
            row.addLayout(col)
        row.addStretch()
        bl.addLayout(row)
        bl.addWidget(self.no_agent)
        lay.addWidget(box)

        btns = QHBoxLayout()
        self.start = QPushButton("Start")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.run)
        self.stop = QPushButton("Stop")
        self.stop.setObjectName("danger")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.kill)
        self.open_btn = QPushButton("Open the brief")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(lambda: open_path(ROOT / "site" / "index.html"))
        btns.addWidget(self.start)
        btns.addWidget(self.stop)
        btns.addStretch()
        btns.addWidget(self.open_btn)
        lay.addLayout(btns)

        steps = QHBoxLayout()
        steps.setSpacing(24)
        self.step_labels = []
        for i, name in enumerate(("1  Fetch data", "2  Claude writes", "3  Render"), 1):
            l = QLabel(name)
            l.setObjectName("step")
            self.step_labels.append(l)
            steps.addWidget(l)
        steps.addStretch()
        self.status = QLabel("")
        steps.addWidget(self.status)
        lay.addLayout(steps)

        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        lay.addWidget(self.log, 1)

    def set_step(self, n: int, done: bool = False):
        for i, l in enumerate(self.step_labels, 1):
            l.setObjectName("step_done" if i < n or (done and i <= n) else "step_on" if i == n else "step")
            l.style().unpolish(l)
            l.style().polish(l)

    def run(self):
        if self.proc:
            return
        settings.setValue("model", self.model.currentText())
        settings.setValue("max_turns", self.turns.value())
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        token = settings.value("token", "")
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        if settings.value("sec_ua", ""):
            env["SEC_USER_AGENT"] = settings.value("sec_ua")
        if self.model.currentText() != "(default)":
            env["BRIEF_MODEL"] = self.model.currentText()
        env["BRIEF_MAX_TURNS"] = str(self.turns.value())
        if self.date.text().strip():
            env["BRIEF_DATE"] = self.date.text().strip()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        args = ["run_brief.py"] + (["--no-agent"] if self.no_agent.isChecked() else [])
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(ROOT))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        pe = self.proc.processEnvironment()
        pe.clear()
        for k, v in env.items():
            pe.insert(k, v)
        self.proc.setProcessEnvironment(pe)
        self.proc.readyReadStandardOutput.connect(self.on_output)
        self.proc.finished.connect(self.on_done)
        self.log.clear()
        self.append(f"$ {python_path()} {' '.join(args)}\n")
        self.start.setEnabled(False)
        self.stop.setEnabled(True)
        self.open_btn.setEnabled(False)
        self.status.setText("running")
        self.set_step(1)
        self.proc.start(python_path(), args)
        if not self.proc.waitForStarted(5000):
            self.append("Could not start Python. Check the interpreter path in Settings.")
            self.on_done(-1, QProcess.CrashExit)

    def append(self, text: str):
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.End)

    def on_output(self):
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.append(data)
        for line in data.splitlines():
            if line.startswith("=== 2/3"):
                self.set_step(2)
            elif line.startswith("=== 3/3"):
                self.set_step(3)

    def on_done(self, code: int, _status):
        self.proc = None
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        if code == 0:
            self.set_step(3, done=True)
            self.status.setText("done")
            self.status.setObjectName("ok")
            self.open_btn.setEnabled(True)
            self.window.issues.refresh()
            self.window.thesis.refresh_suggestions()
        else:
            self.status.setText(f"failed (exit {code})")
            self.status.setObjectName("bad")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def kill(self):
        if self.proc:
            self.proc.kill()


class IssuesPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        t = QLabel("Past issues")
        t.setObjectName("title")
        lay.addWidget(t)
        self.list = QListWidget()
        self.list.setObjectName("issues")
        self.list.itemDoubleClicked.connect(lambda _: self.open_page())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        b1 = QPushButton("Open page")
        b1.clicked.connect(self.open_page)
        b2 = QPushButton("Open markdown")
        b2.clicked.connect(lambda: open_path(ROOT / "LATEST.md"))
        b3 = QPushButton("Open data tables")
        b3.clicked.connect(lambda: open_path(ROOT / "data" / "summary.md"))
        b4 = QPushButton("Show folder")
        b4.clicked.connect(lambda: open_path(ROOT / "briefs"))
        for b in (b1, b2, b3, b4):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for p in sorted((ROOT / "briefs").glob("*.json"), reverse=True):
            try:
                b = json.loads(p.read_text(encoding="utf-8"))
                text = f"{b.get('issue_date', p.stem)}    {b.get('headline', '')}"
            except Exception:  # noqa: BLE001
                text = f"{p.stem}    (could not read)"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, p.stem)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def open_page(self):
        item = self.list.currentItem()
        if not item:
            return
        page = ROOT / "site" / item.data(Qt.UserRole) / "index.html"
        open_path(page if page.exists() else ROOT / "site" / "index.html")


class EditorPage(QWidget):
    def __init__(self, title: str, subtitle: str, path: Path, side: bool = False):
        super().__init__()
        self.path = path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        t = QLabel(title)
        t.setObjectName("title")
        lay.addWidget(t)
        s = QLabel(subtitle)
        s.setObjectName("subtitle")
        s.setWordWrap(True)
        lay.addWidget(s)
        body = QHBoxLayout()
        body.setSpacing(16)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("editor")
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setPlainText(path.read_text(encoding="utf-8") if path.exists() else "")
        self.editor.textChanged.connect(lambda: self.save_btn.setEnabled(True))
        body.addWidget(self.editor, 3)
        self.side = None
        if side:
            box, bl = card()
            bl.addWidget(h2("Suggested edits (latest brief)"))
            self.side = QLabel("")
            self.side.setWordWrap(True)
            self.side.setAlignment(Qt.AlignTop)
            bl.addWidget(self.side, 1)
            box.setFixedWidth(360)
            body.addWidget(box, 1)
        lay.addLayout(body, 1)
        row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        reload = QPushButton("Reload from disk")
        reload.clicked.connect(self.reload)
        self.saved = QLabel("")
        row.addWidget(self.save_btn)
        row.addWidget(reload)
        row.addWidget(self.saved)
        row.addStretch()
        lay.addLayout(row)
        self.refresh_suggestions()

    def save(self):
        self.path.write_text(self.editor.toPlainText(), encoding="utf-8")
        self.save_btn.setEnabled(False)
        self.saved.setText("saved")
        QTimer.singleShot(2500, lambda: self.saved.setText(""))

    def reload(self):
        self.editor.setPlainText(self.path.read_text(encoding="utf-8"))
        self.save_btn.setEnabled(False)

    def refresh_suggestions(self):
        if self.side is None:
            return
        briefs = sorted((ROOT / "briefs").glob("*.json"))
        if not briefs:
            self.side.setText("No briefs yet.")
            return
        try:
            b = json.loads(briefs[-1].read_text(encoding="utf-8"))
            sugg = b.get("thesis_suggestions") or []
            self.side.setText(("From " + b.get("issue_date", briefs[-1].stem) + ":\n\n" + "\n\n".join("• " + s for s in sugg))
                              if sugg else f"The {b.get('issue_date', '')} brief suggested no changes.")
        except Exception as e:  # noqa: BLE001
            self.side.setText(f"Could not read the latest brief: {e}")


class PublishPage(QWidget):
    def __init__(self):
        super().__init__()
        self.proc: QProcess | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        t = QLabel("Publish to GitHub")
        t.setObjectName("title")
        lay.addWidget(t)
        s = QLabel("Commits everything in the folder (except ignored files) and pushes it. Check the status first.")
        s.setObjectName("subtitle")
        lay.addWidget(s)
        row = QHBoxLayout()
        self.msg = QLineEdit()
        self.msg.setPlaceholderText("Commit message (optional)")
        self.check = QPushButton("Check status")
        self.check.clicked.connect(lambda: self.git(["status", "--short"]))
        self.push = QPushButton("Commit and push")
        self.push.setObjectName("primary")
        self.push.clicked.connect(self.commit_push)
        self.pull = QPushButton("Pull latest")
        self.pull.clicked.connect(lambda: self.git(["pull", "--rebase"]))
        row.addWidget(self.msg, 1)
        row.addWidget(self.check)
        row.addWidget(self.pull)
        row.addWidget(self.push)
        lay.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        lay.addWidget(self.log, 1)
        self.queue: list[list[str]] = []

    def git(self, args: list[str], then: list[list[str]] | None = None):
        if self.proc:
            self.queue.append(args)
            return
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(ROOT))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(
            lambda: self.log.appendPlainText(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace").rstrip()))
        self.proc.finished.connect(self.next)
        self.log.appendPlainText("$ git " + " ".join(args))
        self.proc.start("git", args)
        if then:
            self.queue.extend(then)

    def next(self, code: int, _s):
        self.proc = None
        if code != 0:
            self.log.appendPlainText(f"(exit {code}; stopping)")
            self.queue.clear()
            return
        if self.queue:
            self.git(self.queue.pop(0))
        else:
            self.log.appendPlainText("done")

    def commit_push(self):
        from datetime import date

        msg = self.msg.text().strip() or f"Brief {date.today().isoformat()}"
        self.log.clear()
        self.git(["add", "-A"], then=[["commit", "-m", msg], ["push"]])


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        t = QLabel("Settings")
        t.setObjectName("title")
        lay.addWidget(t)
        s = QLabel("Stored on this computer for your user account only. Nothing here goes into the repo.")
        s.setObjectName("subtitle")
        lay.addWidget(s)

        box, bl = card()
        bl.addWidget(h2("Claude subscription token"))
        hint = QLabel("From `claude setup-token`. Leave empty to use the `claude` login on this machine.")
        hint.setObjectName("subtitle")
        bl.addWidget(hint)
        self.token = QLineEdit(settings.value("token", ""))
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("sk-ant-oat01-…")
        row = QHBoxLayout()
        row.addWidget(self.token, 1)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(lambda on: self.token.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        row.addWidget(show)
        bl.addLayout(row)
        self.token_status = QLabel("")
        bl.addWidget(self.token_status)
        lay.addWidget(box)

        box2, bl2 = card()
        bl2.addWidget(h2("Python interpreter"))
        hint2 = QLabel("The Python that has the project's packages installed (normally .venv inside this folder).")
        hint2.setObjectName("subtitle")
        bl2.addWidget(hint2)
        row2 = QHBoxLayout()
        self.python = QLineEdit(python_path())
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse)
        row2.addWidget(self.python, 1)
        row2.addWidget(browse)
        bl2.addLayout(row2)
        bl2.addWidget(h2("SEC contact (name and email, required by the SEC for automated requests)"))
        self.sec = QLineEdit(settings.value("sec_ua", ""))
        self.sec.setPlaceholderText("Jane Doe jane@example.com")
        bl2.addWidget(self.sec)
        lay.addWidget(box2)

        row3 = QHBoxLayout()
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        self.saved = QLabel("")
        row3.addWidget(save)
        row3.addWidget(self.saved)
        row3.addStretch()
        lay.addLayout(row3)
        lay.addStretch()
        self.update_status()

    def browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose python.exe", str(ROOT), "Python (python.exe python);;All files (*)")
        if p:
            self.python.setText(p)

    def save(self):
        settings.setValue("token", self.token.text().strip())
        settings.setValue("python", self.python.text().strip())
        settings.setValue("sec_ua", self.sec.text().strip())
        self.saved.setText("saved")
        QTimer.singleShot(2500, lambda: self.saved.setText(""))
        self.update_status()

    def update_status(self):
        if self.token.text().strip():
            self.token_status.setText("Token set: runs will use your subscription.")
            self.token_status.setObjectName("ok")
        elif os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            self.token_status.setText("Token found in the environment.")
            self.token_status.setObjectName("ok")
        else:
            self.token_status.setText("No token: runs rely on an existing `claude` login. Run `claude setup-token` if that fails.")
            self.token_status.setObjectName("warn")
        self.token_status.style().unpolish(self.token_status)
        self.token_status.style().polish(self.token_status)


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------


def open_path(p: Path):
    if not p.exists():
        QMessageBox.information(None, "Not found", f"{p.name} doesn't exist yet. Run the brief first.")
        return
    if sys.platform.startswith("win"):
        os.startfile(str(p))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        webbrowser.open(p.as_uri())


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Build-out Brief")
        self.resize(1100, 720)
        self.setMinimumSize(860, 560)
        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.setFixedWidth(190)
        self.nav.setFrameShape(QFrame.NoFrame)
        self.pages = QStackedWidget()

        self.run = RunPage(self)
        self.issues = IssuesPage()
        self.thesis = EditorPage("Your thesis", "The brief judges each week against this file and only suggests edits; it never changes it. "
                                 "Keep the tripwires concrete and checkable.", ROOT / "THESIS.md", side=True)
        self.brief = EditorPage("Instructions for Claude", "What the agent reads every week: the sections, what to research, the rules, "
                                "and the output format. Change a section here when it isn't useful.", ROOT / "BRIEF.md")
        self.publish = PublishPage()
        self.settings = SettingsPage()
        for name, page in (("Run", self.run), ("Issues", self.issues), ("Thesis", self.thesis),
                           ("Instructions", self.brief), ("Publish", self.publish), ("Settings", self.settings)):
            self.nav.addItem(name)
            self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        lay.addWidget(self.nav)
        lay.addWidget(self.pages, 1)

    def closeEvent(self, ev):
        for page in (self.thesis, self.brief):
            if page.save_btn.isEnabled():
                r = QMessageBox.question(self, "Unsaved changes", f"Save changes to {page.path.name}?",
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                if r == QMessageBox.Cancel:
                    ev.ignore()
                    return
                if r == QMessageBox.Yes:
                    page.save()
        if self.run.proc:
            self.run.proc.kill()
        ev.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 10))
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
