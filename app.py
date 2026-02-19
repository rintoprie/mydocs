import re
import io
import zipfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

from flask import Flask, abort, redirect, render_template, request, url_for, send_file
import markdown as md

APP_ROOT = Path(__file__).resolve().parent
DOCS_ROOT = (APP_ROOT / "docs").resolve()
ALLOWED_EXTS = {".md", ".markdown"}

app = Flask(__name__)


@dataclass
class TreeNode:
    name: str
    rel_path: str
    is_dir: bool
    children: list["TreeNode"] = field(default_factory=list)


def safe_resolve_doc(rel_path: str) -> Path:
    if rel_path is None:
        raise ValueError("rel_path is None")

    rel_path = rel_path.replace("\\", "/").lstrip("/")
    if rel_path.startswith("..") or "/../" in rel_path or rel_path == "..":
        raise ValueError("Path traversal attempt")

    full = (DOCS_ROOT / rel_path).resolve()
    if DOCS_ROOT not in full.parents and full != DOCS_ROOT:
        raise ValueError("Escaped DOCS_ROOT")
    return full


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def render_markdown(text: str) -> str:
    return md.markdown(
        text,
        extensions=[
            "fenced_code",
            "tables",
            "toc",
            "sane_lists",
            "attr_list",
            "md_in_html",
            "footnotes",
            "codehilite",
            "pymdownx.superfences",
            "pymdownx.tasklist",
            "pymdownx.tilde",
            "pymdownx.magiclink",
            "pymdownx.emoji",
        ],
        extension_configs={
            "codehilite": {"guess_lang": False, "noclasses": False},
            "pymdownx.tasklist": {"clickable_checkbox": False},
            "toc": {"permalink": "#"},
        },
        output_format="html5",
    )


def snippet(text: str, q: str, limit: int = 240) -> str:
    import re as _re
    m = _re.search(_re.escape(q), text, flags=_re.IGNORECASE)
    if not m:
        return ""
    start = max(0, m.start() - limit // 2)
    end = min(len(text), start + limit)
    s = text[start:end].replace("\n", " ")
    return ("..." if start > 0 else "") + s + ("..." if end < len(text) else "")


def walk_docs() -> List[str]:
    out: List[str] = []
    if not DOCS_ROOT.exists():
        return out
    for p in DOCS_ROOT.rglob("*"):
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTS:
            out.append(p.relative_to(DOCS_ROOT).as_posix())
    return sorted(out)


def build_tree() -> TreeNode:
    def node_for_dir(dir_path: Path) -> TreeNode:
        rel = "" if dir_path == DOCS_ROOT else dir_path.relative_to(DOCS_ROOT).as_posix()
        n = TreeNode(name=(dir_path.name if rel else "docs"), rel_path=rel, is_dir=True)

        dirs, files = [], []
        for child in dir_path.iterdir():
            if child.is_dir():
                dirs.append(child)
            elif child.is_file() and child.suffix.lower() in ALLOWED_EXTS:
                files.append(child)

        for d in sorted(dirs, key=lambda p: p.name.lower()):
            n.children.append(node_for_dir(d))

        for f in sorted(files, key=lambda p: p.name.lower()):
            relf = f.relative_to(DOCS_ROOT).as_posix()
            n.children.append(TreeNode(name=f.name, rel_path=relf, is_dir=False))

        return n

    if not DOCS_ROOT.exists():
        return TreeNode(name="docs", rel_path="", is_dir=True, children=[])
    return node_for_dir(DOCS_ROOT)


TREE_CACHE: Optional[TreeNode] = None


def get_tree() -> TreeNode:
    global TREE_CACHE
    if TREE_CACHE is None:
        TREE_CACHE = build_tree()
    return TREE_CACHE


def layout_context(*, browse_path: str = "", active_path: str = "") -> dict:
    return {
        "tree": get_tree(),
        "active_path": active_path,
        "browse_path": browse_path,
    }


def find_readme_in_dir(dir_rel: str) -> str | None:
    base = safe_resolve_doc(dir_rel)
    if not base.exists() or not base.is_dir():
        return None

    for name in ("README.md", "readme.md", "README.markdown", "readme.markdown"):
        candidate = base / name
        if candidate.exists() and candidate.is_file():
            return candidate.relative_to(DOCS_ROOT).as_posix()
    return None


@app.get("/")
def home():
    if not DOCS_ROOT.exists():
        return render_template(
            "browse.html",
            title="My Docs",
            folder="/",
            parent_link=None,
            message=f"Create docs folder at: {DOCS_ROOT}",
            q="",
            **layout_context(browse_path=""),
        )
    return redirect(url_for("browse", subpath=""))


@app.get("/browse/")
@app.get("/browse/<path:subpath>")
def browse(subpath: str = ""):
    try:
        p = safe_resolve_doc(subpath)
    except ValueError:
        abort(404)

    if not p.exists() or not p.is_dir():
        abort(404)

    rel = p.relative_to(DOCS_ROOT).as_posix() if p != DOCS_ROOT else ""

    readme_rel = find_readme_in_dir(rel)
    if readme_rel:
        return redirect(url_for("view_doc", docpath=readme_rel))

    parent_rel = str(Path(rel).parent).replace("\\", "/")
    if parent_rel == ".":
        parent_rel = ""
    parent_link = url_for("browse", subpath=parent_rel) if rel else None

    return render_template(
        "browse.html",
        title=f"Browse /{rel}",
        folder=f"/{rel}",
        parent_link=parent_link,
        message="Pick a folder or markdown file from the sidebar.",
        q="",
        **layout_context(browse_path=rel),
    )


@app.get("/view/<path:docpath>")
def view_doc(docpath: str):
    try:
        p = safe_resolve_doc(docpath)
    except ValueError:
        abort(404)

    if not p.exists() or not p.is_file() or p.suffix.lower() not in ALLOWED_EXTS:
        abort(404)

    raw = read_text(p)
    html = render_markdown(raw)

    rel = p.relative_to(DOCS_ROOT).as_posix()
    folder_rel = str(Path(rel).parent).replace("\\", "/")
    if folder_rel == ".":
        folder_rel = ""

    return render_template(
        "view.html",
        title=rel,
        doc_rel=rel,
        doc_title=p.stem,
        folder_rel=folder_rel,
        html=html,
        q="",
        **layout_context(browse_path=folder_rel, active_path=rel),
    )


@app.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return redirect(url_for("browse", subpath=""))

    results: List[Tuple[str, str]] = []
    for rel in walk_docs():
        try:
            p = safe_resolve_doc(rel)
        except ValueError:
            continue
        text = read_text(p)
        if re.search(re.escape(q), rel, flags=re.IGNORECASE) or re.search(re.escape(q), text, flags=re.IGNORECASE):
            results.append((rel, snippet(text, q)))
        if len(results) >= 50:
            break

    return render_template(
        "search.html",
        title=f"Search: {q}",
        q=q,
        results=results,
        **layout_context(browse_path=""),
    )


@app.get("/download", endpoint="download_all_md")

def download_all_md():
    """
    Download all Markdown files under ./docs as a single zip.
    Keeps folder structure relative to DOCS_ROOT.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        if DOCS_ROOT.exists():
            for p in DOCS_ROOT.rglob("*"):
                if p.is_file() and p.suffix.lower() in ALLOWED_EXTS:
                    arcname = p.relative_to(DOCS_ROOT).as_posix()
                    z.write(p, arcname)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="my_docs_markdown.zip",
        mimetype="application/zip",
        max_age=0,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
