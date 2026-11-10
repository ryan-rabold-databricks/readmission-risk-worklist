"""Run the SQL checks in a .sql file and write the evidence text next to it.

Usage: python3 evidence/phase7/run_sql.py evidence/phase7/<name>.sql [--profile P] [--warehouse ID]

Each check in the file starts with a comment line `-- ### <title>`; the statement
follows until the next title. Output: <name>.raw.txt with, per check, the title,
the SQL, the state, and the result as CSV. Read-only checks only.
"""
import argparse
import datetime
import pathlib
import re
import subprocess

ap = argparse.ArgumentParser()
ap.add_argument("sql_file")
ap.add_argument("--profile", default="fevm-classic-stable")
ap.add_argument("--warehouse", default="b2f6ee775c2fa42c")
args = ap.parse_args()

src = pathlib.Path(args.sql_file)
parts = re.split(r"^-- ### (.+)$", src.read_text(), flags=re.M)
header, checks = parts[0], list(zip(parts[1::2], parts[2::2]))

user = subprocess.run(
    ["databricks", "current-user", "me", "--profile", args.profile, "-o", "json"],
    capture_output=True, text=True, check=True,
).stdout
user = re.search(r'"userName":\s*"([^"]+)"', user).group(1)

out = [
    header.strip(),
    f"# Run {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ} as {user}, "
    f"profile {args.profile}, warehouse {args.warehouse}",
    "",
]
for title, sql in checks:
    sql = sql.strip().rstrip(";")
    r = subprocess.run(
        ["databricks", "experimental", "aitools", "tools", "query", sql,
         "--profile", args.profile, "--warehouse", args.warehouse, "-o", "csv"],
        capture_output=True, text=True,
    )
    state = "SUCCEEDED" if r.returncode == 0 else f"FAILED (exit {r.returncode})"
    body = r.stdout.strip() if r.returncode == 0 else (r.stderr.strip() or r.stdout.strip())
    out += [f"### {title.strip()}", sql, state, body, ""]
    print(f"{state:10} {title.strip()}")

dest = src.with_suffix(".raw.txt")
dest.write_text("\n".join(out) + "\n")
print(f"wrote {dest}")
