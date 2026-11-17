"""Create (or reset) a DQ dashboard user. Run by an admin only:

    python scripts/create_user.py --email ana@example.com --role finance

The password is read with getpass, so it is never echoed, logged or stored in
shell history. Only its scrypt hash is written, with must_change_password=true,
so the user must choose their own password at first login.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "auth"))

from authlib.passwords import hash_password  # noqa: E402

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--email", required=True)
    ap.add_argument("--role", required=True, choices=["data", "finance", "revops"])
    ap.add_argument("--table", default="finora-dq-users")
    ap.add_argument("--profile", default="alegra-test")
    ap.add_argument("--region", default="us-west-2")
    a = ap.parse_args()
    email = a.email.strip().lower()
    if not EMAIL.match(email):
        sys.exit("not a valid email address")
    pw = getpass.getpass("Temporary password (min 12 chars, not echoed): ")
    if len(pw) < 12 or pw != getpass.getpass("Repeat it: "):
        sys.exit("passwords differ or are shorter than 12 characters; nothing written")
    import boto3
    from datetime import datetime, timezone
    session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE") or a.profile, region_name=a.region)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session.resource("dynamodb").Table(a.table).put_item(Item={
        "email": email, "password_hash": hash_password(pw), "role": a.role,
        "must_change_password": True, "created_at": now, "updated_at": now})
    print(f"user {email} ({a.role}) written to {a.table}; they must change the password at first login")


if __name__ == "__main__":
    main()
