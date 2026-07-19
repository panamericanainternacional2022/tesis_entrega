import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import List, Optional


logger = logging.getLogger(__name__)


def get_smtp_creds(
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> tuple[str, int, str, str]:
    from apps.sensors.sensor_config import SMTP_TIMEOUT as _  # noqa: F401 - ensure available
    return (
        smtp_server or os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port or int(os.environ.get("SMTP_PORT", 587)),
        smtp_user or os.environ.get("SMTP_USER", ""),
        smtp_password or os.environ.get("SMTP_PASSWORD", ""),
    )


def smtp_send(
    msg: MIMEMultipart,
    recipients: List[str],
    server: str,
    port: int,
    user: str,
    password: str,
    timeout: int = 15,
) -> None:
    if not user or not password:
        logger.warning("SMTP credentials not configured. Email not sent to %s.", recipients)
        return
    conn = smtplib.SMTP(server, port, timeout=timeout)
    conn.starttls()
    conn.login(user, password)
    for rec in recipients:
        if "To" in msg:
            del msg["To"]
        msg["To"] = rec
        conn.send_message(msg)
    conn.quit()


def build_mime_message(
    html_body: str,
    plain_body: str,
    subject: str,
    from_addr: str,
    attachment_pdf: Optional[bytes] = None,
    attachment_name: str = "reporte.pdf",
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed" if attachment_pdf else "alternative")
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_body or html_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    if attachment_pdf is not None:
        part = MIMEApplication(attachment_pdf, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=attachment_name)
        msg.attach(part)

    msg["From"] = from_addr
    msg["Subject"] = subject
    return msg
