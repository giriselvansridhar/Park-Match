"""Build the files Vercel deploys: a clean demo database, its spot images, and collected static files.

Run from the project root before deploying:

    python deploy/build.py

It never touches your local db.sqlite3 or media/. The demo database holds only the Chennai spots and demo accounts.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
DB = DEPLOY / "demo.sqlite3"
MEDIA = DEPLOY / "media"


def manage(*args, **env):
    print("->", "manage.py", *args, flush=True)
    subprocess.run([sys.executable, "manage.py", *args], cwd=ROOT, check=True,
                   env={**os.environ, "DJANGO_DEBUG": "1", **env})


def main():
    DB.unlink(missing_ok=True)
    shutil.rmtree(MEDIA, ignore_errors=True)
    env = {"PARKMATCH_DB": str(DB), "PARKMATCH_MEDIA_ROOT": str(MEDIA)}
    os.environ.pop("DATABASE_URL", None)

    manage("migrate", "--noinput", "-v", "0", **env)
    manage("seed_chennai", **env)
    manage("seed_demo", **env)
    manage("generate_spot_images", **env)
    manage("collectstatic", "--noinput", "--clear", "-v", "0")

    # Run the test suite so a broken build never ships, and record the count for the landing page.
    print("-> pytest", flush=True)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                            capture_output=True, text=True, env={**os.environ, "DJANGO_DEBUG": "1"})
    summary = (result.stdout.strip().splitlines() or ["no output"])[-1]
    print("  ", summary)
    if result.returncode != 0:
        sys.exit("Tests failed, so the bundle wasn't finished. Run `python -m pytest` to see why.")
    passed = re.search(r"(\d+) passed", summary)
    (DEPLOY / "test_count.txt").write_text(passed.group(1) if passed else "0")

    size = DB.stat().st_size / 1024
    images = len(list((MEDIA / "spot_photos").glob("*")))
    print(f"\nDone: deploy/demo.sqlite3 ({size:.0f} KB), {images} spot images, static files in staticfiles/.")


if __name__ == "__main__":
    main()
