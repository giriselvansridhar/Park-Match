"""Build the files Vercel deploys: a clean demo database, its spot images, and collected static files.

Run from the project root before deploying:

    python deploy/build.py

It never touches your local db.sqlite3 or media/. The demo database holds only the Chennai spots and demo accounts.
"""
import os
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

    size = DB.stat().st_size / 1024
    images = len(list((MEDIA / "spot_photos").glob("*")))
    print(f"\nDone: deploy/demo.sqlite3 ({size:.0f} KB), {images} spot images, static files in staticfiles/.")


if __name__ == "__main__":
    main()
