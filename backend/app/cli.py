"""Server commands: python -m app.cli invite [--admin] [--email x] | openapi FILE"""

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    invite = commands.add_parser("invite", help="create an invite link")
    invite.add_argument("--admin", action="store_true", help="the new user becomes an admin")
    invite.add_argument("--email", help="only this Google email may use it")
    openapi = commands.add_parser("openapi", help="write the API description")
    openapi.add_argument("file", type=Path)
    args = parser.parse_args()

    if args.command == "invite":
        from .db import get_engine
        from .security import create_invite

        with Session(get_engine()) as db:
            _, url = create_invite(db, email=args.email, admin=args.admin)
        print(url)
    else:
        from .main import app

        args.file.write_text(json.dumps(app.openapi(), indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
