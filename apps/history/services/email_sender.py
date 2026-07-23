import logging
from typing import Any, List, Optional

from apps.core.smtp_service import (
    get_smtp_creds as _get_smtp_creds,
    smtp_send as _smtp_send,
    build_mime_message as _build_mime_message,
)
from apps.history.services.email_config import EmailAttachment, EmailConfig


logger = logging.getLogger(__name__)


def send_email_raw(
    to_addrs: List[str],
    subject: str,
    html_body: str,
    plain_body: str = "",
    attachment_pdf: Optional[bytes] = None,
    attachment_name: str = "reporte.pdf",
    attachments: Optional[List[tuple[bytes, str]]] = None,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> None:
    smtp_server, smtp_port, smtp_user, smtp_password = _get_smtp_creds(
        smtp_server, smtp_port, smtp_user, smtp_password
    )
    if not smtp_user or not smtp_password:
        logger.warning("SMTP not configured. Email '%s' not sent.", subject)
        return

    msg = _build_mime_message(
        html_body=html_body,
        plain_body=plain_body,
        subject=subject,
        from_addr=smtp_user,
        attachment_pdf=attachment_pdf,
        attachment_name=attachment_name,
        attachments=attachments,
    )

    from apps.sensors.sensor_config import SMTP_TIMEOUT
    _smtp_send(msg, to_addrs, smtp_server, smtp_port, smtp_user, smtp_password, SMTP_TIMEOUT)


def _send_email_smtp(config: EmailConfig) -> None:
    smtp_server, smtp_port, smtp_user, smtp_password = _get_smtp_creds(
        config.smtp_server, config.smtp_port, config.smtp_user, config.smtp_password
    )

    if not smtp_user or not smtp_password:
        logger.warning(
            "SMTP credentials not configured. No real email will be sent to %s.",
            config.recipients,
        )
        return

    attachment_bytes = None
    attachment_filename = "report.pdf"
    if config.attachment:
        config.attachment.pdf_data.seek(0)
        attachment_bytes = config.attachment.pdf_data.read()
        attachment_filename = config.attachment.filename

    body_stripped = config.body.strip()
    if body_stripped.startswith("<!DOCTYPE") or body_stripped.startswith("<html"):
        msg = _build_mime_message(
            html_body=config.body,
            plain_body="",
            subject=config.subject,
            from_addr=smtp_user,
            attachment_pdf=attachment_bytes,
            attachment_name=attachment_filename,
        )
        from apps.sensors.sensor_config import SMTP_TIMEOUT
        _smtp_send(msg, config.recipients or [], smtp_server, smtp_port, smtp_user, smtp_password, SMTP_TIMEOUT)
        logger.info("Real email sent to %s (risk %s)", config.recipients, config.risk_level)
        return

    from apps.history.services.email_templates import _CONTEXT_DEFAULT, _build_alert_html

    details = {}
    action_text = ""
    context_lines: List[str] = []
    in_details = False
    in_actions = False

    for line in config.body.strip().split("\n"):
        line_strip = line.strip()
        if not line_strip:
            continue
        if "DETALLES DEL EVENTO:" in line_strip:
            in_details, in_actions = True, False
            continue
        if "MEDIDA CORRECTIVA RECOMENDADA:" in line_strip:
            in_details, in_actions = False, True
            continue
        if line_strip.startswith("---") or line_strip.startswith("==="):
            continue

        if in_details:
            if ":" in line_strip:
                k, _, v = line_strip.partition(":")
                details[k.strip()] = v.strip()
        elif in_actions:
            if line_strip.startswith("Acción:"):
                action_text = line_strip.split(":", 1)[1].strip()
            else:
                action_text = (action_text + " " + line_strip).strip()
        else:
            context_lines.append(line_strip)

    context = " ".join(context_lines[1:]) if len(context_lines) > 1 else _CONTEXT_DEFAULT

    html_content = _build_alert_html(
        risk_level=config.risk_level,
        context=context or _CONTEXT_DEFAULT,
        details=details or None,
        action_text=action_text,
    )

    msg = _build_mime_message(
        html_body=html_content,
        plain_body=config.body,
        subject=config.subject,
        from_addr=smtp_user,
        attachment_pdf=attachment_bytes,
        attachment_name=attachment_filename,
    )

    from apps.sensors.sensor_config import SMTP_TIMEOUT
    _smtp_send(msg, config.recipients or [], smtp_server, smtp_port, smtp_user, smtp_password, SMTP_TIMEOUT)
    logger.info("Real email sent to %s (risk %s)", config.recipients, config.risk_level)


def send_email_alert(
    risk_level: str,
    subject: str,
    body: str,
    attachment_pdf: Any = None,
    attachment_name: str = "report.pdf",
    recipients: Optional[List[str]] = None,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> None:
    if recipients is None:
        from apps.history.services.email_recipients import get_building_emails
        recipients = get_building_emails()
    if not recipients:
        logger.info("No subscribers for level %s in email", risk_level)
        return

    attachment = EmailAttachment(attachment_pdf, attachment_name) if attachment_pdf else None
    config = EmailConfig(
        risk_level=risk_level,
        subject=subject,
        body=body,
        attachment=attachment,
        recipients=recipients,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
    )

    try:
        _send_email_smtp(config)
    except Exception as e:
        logger.error("Error sending email: %s", e)
