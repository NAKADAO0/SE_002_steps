"""Create the homework archive without credentials, runtime inputs or caches."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT.parent / "001Homework2" / "2320100622计浩晟.zip"
EXCLUDED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "runs"}


def main():
    files = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in EXCLUDED for part in relative.parts):
            continue
        if path.name == ".env.example" or path.name == ".gitignore" or path.suffix in {".py", ".md", ".txt", ".html", ".css", ".js", ".cjs", ".jpg"}:
            files.append(path)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(DESTINATION, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path(ROOT.name) / path.relative_to(ROOT))
    with ZipFile(DESTINATION) as archive:
        assert archive.testzip() is None
        assert not any(Path(name).name == ".env" or "runs" in Path(name).parts
                       for name in archive.namelist())
        assert "CodeReviewWorkflow/README.md" in archive.namelist()
        assert "CodeReviewWorkflow/Design.md" in archive.namelist()
        assert "CodeReviewWorkflow/web/static/index.html" in archive.namelist()
        assert "CodeReviewWorkflow/web/static/app.js" in archive.namelist()
    assert DESTINATION.stat().st_size < 200 * 1024 * 1024
    print(f"Archive: {DESTINATION}\nFiles: {len(files)}\nBytes: {DESTINATION.stat().st_size}")


if __name__ == "__main__":
    main()
