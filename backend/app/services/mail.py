"""Provider-neutral outbound account email over TLS SMTP."""

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit

from app.config import get_settings
from app.i18n import localized

logger = logging.getLogger(__name__)
LOCAL_PART = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+\Z")
DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\Z")


class MailConfigurationError(ValueError):
    pass


class MailDeliveryError(RuntimeError):
    pass


def normalize_email_address(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or email.count("@") != 1 or any(ord(char) > 127 for char in email):
        raise ValueError(localized("api.enterAValidEmailAddress"))
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
        raise ValueError(localized("api.enterAValidEmailAddress"))
    return email


def public_app_url() -> str:
    value = get_settings().public_app_url.strip().rstrip("/")
    parsed = urlsplit(value)
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        (parsed.scheme != "https" and not local_http)
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path
    ):
        raise MailConfigurationError(localized("api.nextTaskPublicAppUrlMustBeAnHttps"))
    try:
        if parsed.port is not None and parsed.port < 1:
            raise ValueError(localized("api.invalidPort"))
    except ValueError as error:
        raise MailConfigurationError(
            localized("api.nextTaskPublicAppUrlHasAnInvalidPort")
        ) from error
    return value


def send_email(recipient: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host.strip() or not 1 <= settings.smtp_port <= 65535:
        raise MailConfigurationError(localized("api.smtpHostAndPortMustBeConfigured"))
    try:
        sender = normalize_email_address(settings.smtp_from_email)
        recipient = normalize_email_address(recipient)
    except ValueError as error:
        raise MailConfigurationError(localized("api.smtpSenderOrRecipientIsInvalid")) from error
    password = settings.smtp_password.get_secret_value()
    if bool(settings.smtp_username) != bool(password):
        raise MailConfigurationError(
            localized("api.smtpUsernameAndPasswordMustBeConfiguredTogether")
        )

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
        raise MailDeliveryError(localized("api.emailCouldNotBeSentTryAgainLater")) from error
