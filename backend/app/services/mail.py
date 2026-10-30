"""Provider-neutral outbound account email over TLS SMTP."""

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit

from app.config import get_settings

logger = logging.getLogger(__name__)
LOCAL_PART = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+\Z")
DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\Z")


class MailConfigurationError(ValueError):
    pass


class MailDeliveryError(RuntimeError):
    pass


def normalize_contact_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or email.count("@") != 1 or any(ord(char) > 127 for char in email):
        raise ValueError("Enter a valid email address")
    local, domain = email.split("@")
    if (
        not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or not LOCAL_PART.fullmatch(local)
        or len(domain) > 253
        or "." not in domain
        or any(not DOMAIN_LABEL.fullmatch(label) or len(label) > 63 for label in domain.split("."))
    ):
        raise ValueError("Enter a valid email address")
    return email


def public_app_url() -> str:
    value = get_settings().public_app_url.strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path
    ):
        raise MailConfigurationError("NEXT_TASK_PUBLIC_APP_URL must be a public HTTPS origin")
    try:
        if parsed.port is not None and parsed.port < 1:
            raise ValueError("invalid port")
    except ValueError as error:
        raise MailConfigurationError("NEXT_TASK_PUBLIC_APP_URL has an invalid port") from error
    return value


def send_email(recipient: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host.strip() or not 1 <= settings.smtp_port <= 65535:
        raise MailConfigurationError("SMTP host and port must be configured")
    try:
        sender = normalize_contact_email(settings.smtp_from_email)
        recipient = normalize_contact_email(recipient)
    except ValueError as error:
        raise MailConfigurationError("SMTP sender or recipient is invalid") from error
    password = settings.smtp_password.get_secret_value()
    if bool(settings.smtp_username) != bool(password):
        raise MailConfigurationError("SMTP username and password must be configured together")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    try:
        if settings.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=15, context=context
            )
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        with client as smtp:
            if settings.smtp_security == "starttls":
                smtp.starttls(context=context)
            if settings.smtp_username:
                smtp.login(settings.smtp_username, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        logger.error("SMTP delivery failed (%s)", type(error).__name__)
        raise MailDeliveryError("Email could not be sent. Try again later.") from error
