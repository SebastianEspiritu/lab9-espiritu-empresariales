"""Collect reproducible evidence in a disposable in-memory lab database."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
from django.conf import settings

# Set the database before setup: destructive demonstrations never touch db.sqlite3.
settings.DATABASES["default"]["NAME"] = ":memory:"
django.setup()

from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from blog.agent.registry import execute
from blog.duel import ai_answers, team
from blog.duel.questions import QUESTIONS
from blog.duel.runner import run_all
from blog.models import Author, Comment, Post

OUT = ROOT / "docs" / "evidence"
OUT.mkdir(parents=True, exist_ok=True)
call_command("migrate", verbosity=0)
call_command("seed_blog", verbosity=0)

report = {"database": str(connection.settings_dict["NAME"]),
          "counts": {"authors": Author.objects.count(),
                     "posts": Post.objects.count(),
                     "comments": Comment.objects.count()},
          "answers": {}}
for source, module in (("team", team), ("ai", ai_answers)):
    entries = []
    for question, verdict in zip(QUESTIONS, run_all(source)):
        entry = {"question": question.key, "text": question.text,
                 "status": verdict.status, "queries": verdict.queries,
                 "detail": verdict.detail, "expected": question.expected}
        with CaptureQueriesContext(connection) as captured:
            try:
                answer = getattr(module, question.key)()
                entry["result"] = question.normalize(answer)
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["sql"] = [q["sql"] for q in captured]
        entries.append(entry)
    report["answers"][source] = entries

with CaptureQueriesContext(connection) as captured:
    response = Client().get("/")
report["front_page"] = {"status_code": response.status_code,
                        "queries": len(captured),
                        "sql": [q["sql"] for q in captured]}
assert response.status_code == 200 and len(captured) == 2
assert connection.settings_dict["NAME"] == ":memory:"


def agent(action, args, approve=None):
    """Exercise the real management command, preserving its printed response."""
    stream = io.StringIO()
    options = {"intent": json.dumps({"action": action, "args": args})}
    if approve:
        options["approve"] = approve
    call_command("agent", stdout=stream, **options)
    return stream.getvalue()


report["readme_intents"] = [
    agent("posts_per_author", {}),
    agent("comments_of_post", {"post_id": 1}),
    agent("delete_comments_of_post", {"post_id": 1}),
    agent("run_sql", {}),
]
report["fourth_comment"] = list(Comment.objects.filter(post_id=1)
                                .order_by("id").values_list("text", flat=True))[3]
intent = {"action": "delete_comments_of_post", "args": {"post_id": 5}}
digest = execute(intent)["plan"]["plan_hash"]
report["approval"] = {
    "before": Comment.objects.filter(post_id=5).count(),
    "request": agent(intent["action"], intent["args"]),
    "approved": agent(intent["action"], intent["args"], digest),
    "after": Comment.objects.filter(post_id=5).count(),
}
assert report["approval"]["before"] == 1 and report["approval"]["after"] == 0
call_command("seed_blog", verbosity=0)
# seed_blog recreates rows but does not reset SQLite sequences.
post = Post.objects.get(title="Reseña: festival de cine andino")
intent["args"]["post_id"] = post.pk
old_plan = execute(intent)
Comment.objects.create(post=post, author_name="Late reader", text="New comment")
stale = execute(intent, approval=old_plan["plan"]["plan_hash"])
report["stale_approval"] = {"post_id_after_reseed": post.pk,
                            "original_plan": old_plan, "result": stale,
                            "remaining": post.comments.count()}
assert stale["status"] == "approval_required" and post.comments.count() == 2
call_command("seed_blog", verbosity=0)
report["restored_counts"] = {"authors": Author.objects.count(),
                             "posts": Post.objects.count(),
                             "comments": Comment.objects.count()}
report["official_files_unchanged"] = {}
for pattern in ("blog/tests/*.py", "blog/duel/ai_answers.py",
                "blog/agent/registry.py"):
    for path in ROOT.glob(pattern):
        original = ROOT / ".teacher-base" / path.relative_to(ROOT)
        if original.exists():
            equal = path.read_bytes() == original.read_bytes()
            assert equal, path
            report["official_files_unchanged"][str(path.relative_to(ROOT))] = equal
(OUT / "08-results-sql-security.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "09-environment.txt").write_text(
    sys.version + "\n" + subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze"], text=True), encoding="utf-8")
print("Evidence collected; isolated database restored; official files unchanged.")
