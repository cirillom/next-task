import argparse
import getpass
import sys

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.security import hash_password, normalize_email, replace_password
from app.database import SessionLocal
from app.models import Invitation, User
from app.services.invitations import send_invitation
from app.services.mail import (
    MailConfigurationError,
    MailDeliveryError,
    normalize_email_address,
    send_email,
)
from app.services.onboarding import add_onboarding_data


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
    try:
        email = normalize_email_address(args.email or input("Email: "))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    display_name = (args.display_name or input("Display name: ")).strip()
    password = read_password("Password: ", args.password_stdin)
    if not display_name:
        raise SystemExit("Display name is required.")
    with SessionLocal() as db:
        user = User(email=email, display_name=display_name, password_hash=hash_password(password))
        db.add(user)
        try:
            add_onboarding_data(db, user)
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
        replace_password(db, user, password)
        db.commit()
    print(f"Reset password for {email}; existing sessions were revoked.")


def test_email(args: argparse.Namespace) -> None:
    try:
        recipient = normalize_email_address(args.recipient)
        send_email(
            recipient,
            "Next Task SMTP test",
            "This is a test message from your Next Task server.\n",
        )
    except (ValueError, MailConfigurationError, MailDeliveryError) as error:
        raise SystemExit(str(error)) from error
    print(f"SMTP server accepted the test message for {recipient}.")


def invite_user(args: argparse.Namespace) -> None:
    try:
        send_invitation(args.email)
    except (ValueError, MailDeliveryError) as error:
        raise SystemExit(str(error)) from error
    except SQLAlchemyError as error:
        raise SystemExit("Invitation could not be saved. Check the database and retry.") from error
    print("SMTP server accepted the invitation. The link expires in 24 hours.")


def revoke_invite(args: argparse.Namespace) -> None:
    try:
        email = normalize_email_address(args.email)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    with SessionLocal() as db:
        db.execute(delete(Invitation).where(Invitation.email == email))
        db.commit()
    print("Invitation revoked. Previously sent links can no longer create an account.")


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
    invite = subparsers.add_parser("invite-user", help="Send or replace a 24-hour email invitation")
    invite.add_argument("email")
    invite.set_defaults(handler=invite_user)
    revoke = subparsers.add_parser("revoke-invite", help="Revoke an outstanding invitation")
    revoke.add_argument("email")
    revoke.set_defaults(handler=revoke_invite)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
