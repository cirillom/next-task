import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.rate_limit import account_key, clear_attempts, password_change_key
from app.auth.security import hash_password, normalize_email
from app.database import SessionLocal
from app.models import User
from app.services.mail import (
    MailConfigurationError,
    MailDeliveryError,
    normalize_contact_email,
    send_email,
)


def read_password(prompt: str, from_stdin: bool) -> str:
    password = sys.stdin.readline().rstrip("\n") if from_stdin else getpass.getpass(prompt)
    if len(password) < 10:
        raise SystemExit("Password must be at least 10 characters.")
    if not from_stdin:
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")
    return password


def create_user(args: argparse.Namespace) -> None:
    email = normalize_email(args.email or input("Email: "))
    display_name = (args.display_name or input("Display name: ")).strip()
    password = read_password("Password: ", args.password_stdin)
    if not email or not display_name:
        raise SystemExit("Email and display name are required.")
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.contact_email == email)) is not None:
            raise SystemExit(f"A user with {email} already exists.")
        user = User(email=email, display_name=display_name, password_hash=hash_password(password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise SystemExit(f"A user with {email} already exists.") from error
    print(f"Created {email}.")


def reset_password(args: argparse.Namespace) -> None:
    email = normalize_email(args.email)
    password = read_password("New password: ", args.password_stdin)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            raise SystemExit(f"No user found for {email}.")
        user.password_hash = hash_password(password)
        user.sessions.clear()
        clear_attempts(db, account_key(user.id))
        clear_attempts(db, password_change_key(user.id))
        db.commit()
    print(f"Reset password for {email}; existing sessions were revoked.")


def test_email(args: argparse.Namespace) -> None:
    try:
        recipient = normalize_contact_email(args.recipient)
        send_email(
            recipient,
            "Next Task SMTP test",
            "This is a test message from your Next Task server.\n",
        )
    except (ValueError, MailConfigurationError, MailDeliveryError) as error:
        raise SystemExit(str(error)) from error
    print(f"SMTP server accepted the test message for {recipient}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(required=True)

    create = subparsers.add_parser("create-user", help="Create a user")
    create.add_argument("--email")
    create.add_argument("--display-name")
    create.add_argument("--password-stdin", action="store_true")
    create.set_defaults(handler=create_user)

    reset = subparsers.add_parser("reset-password", help="Reset a user's password")
    reset.add_argument("email")
    reset.add_argument("--password-stdin", action="store_true")
    reset.set_defaults(handler=reset_password)
    test_mail = subparsers.add_parser(
        "test-email", help="Send a test email through configured SMTP"
    )
    test_mail.add_argument("recipient")
    test_mail.set_defaults(handler=test_email)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
