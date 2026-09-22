import json
import sys
from pathlib import Path, PurePosixPath

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from src.app.i18n import tr

GITHUB_URL = "https://github.com/zw87652015/ImageLayoutManager"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def _license_root() -> Path | None:
    if _is_frozen():
        return Path(sys._MEIPASS) / "licenses"
    return Path(__file__).resolve().parents[2]


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    junction = getattr(path, "is_junction", None)
    return bool(junction and junction())


def _bad_rel(rel) -> bool:
    if not isinstance(rel, str) or not rel:
        return True
    posix = PurePosixPath(rel.replace("\\", "/"))
    if posix.is_absolute() or Path(rel).is_absolute() or ".." in posix.parts:
        return True
    return any(":" in part for part in posix.parts)


def _safe_join(root: Path, rel) -> Path | None:
    if _bad_rel(rel):
        return None
    posix = PurePosixPath(rel.replace("\\", "/"))
    base = Path(root).resolve()
    node = base
    for part in posix.parts:
        node = node / part
        if _is_reparse(node):
            return None
    try:
        resolved = node.resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_file() and not _is_reparse(resolved) \
        else None


def _safe_dir(root: Path, rel) -> Path | None:
    if _bad_rel(rel):
        return None
    posix = PurePosixPath(rel.replace("\\", "/"))
    base = Path(root).resolve()
    node = base
    for part in posix.parts:
        node = node / part
        if _is_reparse(node):
            return None
    try:
        resolved = node.resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_dir() else None


def _file_count_text(n: int) -> str:
    key = "licenses_group_file" if n == 1 else "licenses_group_files"
    return tr(key).format(n=n)


def _origins_labels(root: Path):
    labels = {}
    try:
        p = _safe_join(root, "licenses/origins.json")
        if p is None:
            return labels
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return labels
        for entry in data:
            if not isinstance(entry, dict):
                continue
            file = entry.get("file")
            member = entry.get("archive_member")
            if not isinstance(file, str) or not isinstance(member, str) \
                    or _bad_rel(file):
                continue
            parts = PurePosixPath(member.replace("\\", "/")).parts
            if len(parts) < 2:
                continue
            labels["licenses/" + file] = "/".join(parts[1:])
    except (OSError, ValueError):
        pass
    return labels


def _collect_groups(root: Path, frozen: bool):
    groups = []
    archive = None
    malformed = False
    seen = set()

    def add(children, rel, p):
        if p in seen:
            return
        seen.add(p)
        children.append((rel, p))

    if frozen:
        app_children = []
        for rel in ("LICENSE", "NOTICE"):
            p = _safe_join(root, rel)
            if p:
                add(app_children, rel, p)
            else:
                malformed = True
        groups.append({"kind": "app", "comp": None,
                       "children": app_children})
        manifest = _safe_join(root, "components.json")
        manifest_ok = False
        if manifest is None:
            malformed = True
        else:
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict) \
                    and isinstance(data.get("components"), list):
                manifest_ok = True
                for comp in data["components"]:
                    if not isinstance(comp, dict):
                        malformed = True
                        continue
                    name = comp.get("name")
                    version = comp.get("version")
                    files = comp.get("license_files")
                    if not isinstance(name, str) \
                            or not isinstance(version, str) \
                            or not isinstance(files, list):
                        malformed = True
                        continue
                    children = []
                    for rel in files:
                        if not isinstance(rel, str):
                            malformed = True
                            continue
                        p = _safe_join(root, rel)
                        if p:
                            add(children, rel, p)
                        else:
                            malformed = True
                    groups.append({"kind": "component", "comp": comp,
                                   "children": children})
        if manifest is not None and not manifest_ok:
            malformed = True
        other_children = []
        if manifest is not None:
            add(other_children, "components.json", manifest)
        for sub in ("licenses", "python"):
            d = _safe_dir(root, sub)
            if d is None:
                continue
            for p in sorted(d.rglob("*")):
                if p.is_file() and not _is_reparse(p):
                    rel = p.relative_to(root.resolve()).as_posix()
                    sp = _safe_join(root, rel)
                    if sp:
                        add(other_children, rel, sp)
        versions = _safe_join(root, "installed-versions.txt")
        if versions:
            add(other_children, "installed-versions.txt", versions)
        groups.append({"kind": "other", "comp": None,
                       "children": other_children})
        for p in sorted(root.glob("*-application-source.zip")):
            rel = p.name
            if _safe_join(root, rel):
                archive = p
    else:
        app_children = []
        for rel in ("NOTICE", "LICENSE"):
            p = _safe_join(root, rel)
            if p:
                add(app_children, rel, p)
        groups.append({"kind": "app", "comp": None,
                       "children": app_children})
        other_children = []
        d = _safe_dir(root, "licenses")
        if d is not None:
            for p in sorted(d.iterdir()):
                if p.is_file() and not _is_reparse(p) \
                        and p.suffix != ".json":
                    rel = f"licenses/{p.name}"
                    sp = _safe_join(root, rel)
                    if sp:
                        add(other_children, rel, sp)
        groups.append({"kind": "other", "comp": None,
                       "children": other_children})
    return groups, archive, malformed


class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("licenses_title"))
        self.resize(800, 600)
        layout = QVBoxLayout(self)

        note = QLabel(tr("licenses_notice"))
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 12px;")
        layout.addWidget(note)

        frozen = _is_frozen()
        root = _license_root()
        self._archive = None
        missing = True
        groups = []
        if root is not None:
            if frozen:
                missing = _safe_join(root, "index.html") is None
                if not missing:
                    groups, self._archive, bad = _collect_groups(
                        root, True)
                    missing = bad
            else:
                groups, self._archive, _bad = _collect_groups(root, False)
                missing = False
        if missing:
            err = QLabel(tr("licenses_missing"))
            err.setWordWrap(True)
            layout.addWidget(err)
        else:
            labels = _origins_labels(root)
            body = QHBoxLayout()
            self._tree = QTreeWidget()
            self._tree.setHeaderHidden(True)
            self._tree.setUniformRowHeights(True)
            self._tree.setMaximumWidth(320)
            first_leaf = None
            app_item = None
            for grp in groups:
                children = grp["children"]
                if not children:
                    continue
                kind = grp["kind"]
                if kind == "app":
                    text = tr("licenses_group_app")
                elif kind == "component":
                    comp = grp["comp"]
                    text = (f"{comp['name']} {comp['version']} · "
                            + _file_count_text(len(children)))
                else:
                    text = tr("licenses_group_other")
                gitem = QTreeWidgetItem([text])
                if kind == "component":
                    gitem.setData(0, Qt.ItemDataRole.UserRole + 1,
                                  grp["comp"])
                for rel, p in children:
                    label = labels.get(rel, PurePosixPath(rel).name)
                    child = QTreeWidgetItem([label])
                    child.setData(0, Qt.ItemDataRole.UserRole, str(p))
                    child.setToolTip(0, rel)
                    gitem.addChild(child)
                    if first_leaf is None:
                        first_leaf = child
                self._tree.addTopLevelItem(gitem)
                if kind == "app":
                    app_item = gitem
            self._tree.currentItemChanged.connect(self._show_item)
            body.addWidget(self._tree)
            self._view = QTextBrowser()
            self._view.setStyleSheet("font-size: 12px;")
            body.addWidget(self._view, 1)
            layout.addLayout(body, 1)
            if app_item is not None:
                app_item.setExpanded(True)
            if first_leaf is not None:
                self._tree.setCurrentItem(first_leaf)

        btn_row = QHBoxLayout()
        self._source_btn = QPushButton(tr("licenses_app_source"))
        self._source_btn.clicked.connect(self._open_source)
        if frozen and self._archive is None:
            self._source_btn.setEnabled(False)
        btn_row.addWidget(self._source_btn)
        repo_btn = QPushButton(tr("about_repository"))
        repo_btn.setToolTip(GITHUB_URL)
        repo_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        btn_row.addWidget(repo_btn)
        btn_row.addStretch()
        close_btn = QPushButton(tr("about_close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _show_item(self, item, _previous=None):
        if item is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None:
            comp = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if isinstance(comp, dict):
                lines = [comp.get("name", ""),
                         comp.get("version", "")]
                role = comp.get("role")
                if role:
                    lines.append(str(role))
                lines.append(_file_count_text(item.childCount()))
                for url in comp.get("project_urls") or []:
                    lines.append(str(url))
                self._view.setPlainText("\n".join(lines))
            else:
                self._view.clear()
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._view.setPlainText(str(exc))
            return
        self._view.setPlainText(text)

    def _open_source(self):
        if self._archive is not None:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._archive.parent)))
            return
        if _is_frozen():
            return
        if hasattr(self, "_view"):
            self._view.setPlainText(tr("licenses_dev_source"))
