"""Copy Wispr Flow meeting notes into research/, one markdown file per meeting.

Run after each demo:
    python3 research/import_wispr.py            # every meeting not imported yet
    python3 research/import_wispr.py --folder "Produkto demos"   # only that Wispr folder

Reads a temporary COPY of Wispr Flow's local database, so the app is never touched.
Files already imported are skipped (matched by the meeting id written into each file),
so running it twice is safe and never overwrites your edits.
"""
import argparse
import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

WISPR_DB = Path.home() / "Library/Application Support/Wispr Flow/flow.sqlite"
RESEARCH = Path(__file__).resolve().parent


def text(value):
    """Wispr stores some fields as JSON; turn anything into readable text."""
    if value in (None, ""):
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if isinstance(parsed, str):
        return parsed.strip()
    return "```json\n" + json.dumps(parsed, indent=2, ensure_ascii=False) + "\n```"


def already_imported():
    ids = set()
    for f in RESEARCH.glob("*.md"):
        m = re.search(r"wispr-meeting-id: (\S+)", f.read_text(errors="ignore"))
        if m:
            ids.add(m.group(1))
    return ids


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "untitled").lower()).strip("-")[:60] or "untitled"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", help="only import meetings in this Wispr Flow folder")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        for suffix in ("", "-wal", "-shm"):
            src = WISPR_DB.with_name(WISPR_DB.name + suffix)
            if src.exists():
                shutil.copy2(src, Path(tmp) / src.name)
        db = sqlite3.connect(Path(tmp) / WISPR_DB.name)
        db.row_factory = sqlite3.Row

        sql = "SELECT m.* FROM Meetings m WHERE m.isDeleted = 0"
        params = []
        if args.folder:
            sql += (" AND m.id IN (SELECT fm.meetingId FROM FolderMeetings fm"
                    " JOIN Folders f ON f.id = fm.folderId WHERE f.name = ?)")
            params.append(args.folder)
        meetings = db.execute(sql + " ORDER BY m.createdAt", params).fetchall()

        done = already_imported()
        written = 0
        for m in meetings:
            if m["id"] in done:
                continue
            version = db.execute(
                "SELECT content FROM MeetingVersions WHERE meetingId = ? ORDER BY createdAt DESC LIMIT 1",
                (m["id"],),
            ).fetchone()
            date = str(m["createdAt"])[:10]
            title = m["title"] or "Untitled meeting"
            path = RESEARCH / f"{date}-demo-{slug(title)}.md"
            n = 2
            while path.exists():
                path = RESEARCH / f"{date}-demo-{slug(title)}-{n}.md"
                n += 1

            parts = [
                f"# {title}",
                "",
                f"- Date: {m['createdAt']}",
                f"- Participants: {text(m['participantNames']) or '—'}",
                f"- Source: Wispr Flow (imported by `import_wispr.py`)",
                f"<!-- wispr-meeting-id: {m['id']} -->",
                "",
                "## My takeaways",
                "",
                "_What they asked, what they reacted to, what they said about price ($99 / $297), next step._",
                "",
                "## Summary (Wispr)",
                "",
                text(m["summary"]) or "_none_",
                "",
                "## Notes (Wispr)",
                "",
                text(m["notes"]) or "_none_",
                "",
                "## Transcript (Wispr)",
                "",
                text(version["content"]) if version else "_none_",
                "",
            ]
            path.write_text("\n".join(parts))
            print(f"wrote {path.name}")
            written += 1

        print(f"{written} new meeting(s) imported, {len(meetings) - written} already present.")


if __name__ == "__main__":
    main()
