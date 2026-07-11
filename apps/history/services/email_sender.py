import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Any, Dict, List, Optional

from apps.core.auth_decorators import ADMIN_ROLES


logger = logging.getLogger(__name__)


_BRAND_NAME      = "INES"
_BRAND_SUBTITLE  = "Sistema inteligente de automatización"
_ALERT_H1        = "Anomalía detectada en la infraestructura"
_ALERT_TAG_LABEL = "Severidad"
_ACTION_LABEL    = "Medida correctiva recomendada"
_DETAILS_LABEL   = "Detalles del evento"
_FOOTER_TEXT     = (
    "Este mensaje ha sido generado automáticamente por el Sistema de Monitoreo INES.<br>"
    "Por favor, no responda a este correo."
)
_CONTEXT_DEFAULT = (
    "El sistema ha registrado una lectura fuera de los rangos operativos "
    "establecidos para el presente edificio. A continuación se detallan "
    "los parámetros del evento y la medida correctiva recomendada."
)

# ─── Design tokens del correo (alineados con static/css/styles.css) ───────────
_ACCENT          = "#2563eb"   # --color-accent
_INK             = "#0a0a0a"   # --color-ink (bordes brutales)
_BG              = "#f5f5f5"   # --color-bg
_SURFACE         = "#ffffff"   # --color-surface
_TEXT_PRIMARY    = "#0a0a0a"   # --color-text-primary
_TEXT_SECONDARY  = "#5f5f5f"   # --color-text-secondary (= PDF gray 95,95,95)
_TEXT_MUTED      = "#9e9e9e"   # --color-text-placeholder
_ACCENT_BG       = "#eff6ff"   # fondo azul claro para emails informativos
_BORDER_LIGHT    = "#f3f4f6"   # borde suave para tablas de detalles
# ────────────────────────────────────────────────────────────────────────────────


def get_unit(variable: str) -> str:
    from apps.sensors.sensor_config import UNITS
    return UNITS.get(variable, "")


def get_building_emails(edificio_id: Optional[int] = None) -> List[str]:
    try:
        from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
    except Exception:
        return []
    try:
        if edificio_id is None:
            equipo = MonitoringEquipment.objects.first()
            if equipo and equipo.building:
                edificio_id = equipo.building.id
            else:
                first_edf = Building.objects.first()
                if first_edf:
                    edificio_id = first_edf.id
                else:
                    return []
            logger.warning(
                "get_building_emails llamado sin edificio_id — usando fallback edificio %s. "
                "Los eventos del simulador deberían pasar siempre un edificio_id explícito.",
                edificio_id,
            )

        users = UserBuilding.objects.filter(
            building_id=edificio_id,
            user__registered=True,
        ).exclude(
            user__rol__in=ADMIN_ROLES,
        ).select_related("user__id_persona")
        emails: List[str] = []
        for u in users:
            if u.user and u.user.id_persona and u.user.id_persona.email:
                email = u.user.id_persona.email.strip()
                if email and email not in emails:
                    emails.append(email)
        return emails
    except Exception as e:
        logger.error("Error retrieving emails for building %s: %s", edificio_id, e)
        return []


class EmailAttachment:
    def __init__(self, pdf_data: Any, filename: str = "report.pdf") -> None:
        if isinstance(pdf_data, bytes):
            from io import BytesIO
            pdf_data = BytesIO(pdf_data)
        self.pdf_data = pdf_data
        self.filename = filename


class EmailConfig:
    def __init__(
        self,
        risk_level: str,
        subject: str,
        body: str,
        attachment: Optional[EmailAttachment] = None,
        recipients: Optional[List[str]] = None,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
    ) -> None:
        self.risk_level = risk_level
        self.subject = subject
        self.body = body
        self.attachment = attachment
        self.recipients = recipients
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password


def _smtp_send(
    msg: Any,
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


def _get_smtp_creds(
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> tuple[str, int, str, str]:
    return (
        smtp_server or os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port or int(os.environ.get("SMTP_PORT", 587)),
        smtp_user or os.environ.get("SMTP_USER", ""),
        smtp_password or os.environ.get("SMTP_PASSWORD", ""),
    )


def _get_email_colors(risk_level: str) -> Dict[str, str]:
    from apps.sensors.sensor_config import EMAIL_COLOR_PALETTE, EMAIL_FALLBACK_COLORS
    return EMAIL_COLOR_PALETTE.get(risk_level, EMAIL_FALLBACK_COLORS)


def _build_email_shell(inner_html: str) -> str:


    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: {_BG}; font-family: 'DM Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: {_TEXT_PRIMARY};">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: {_BG}; padding: 32px 16px;">
    <tr>
      <td align="center">
        <!-- Contenedor principal: borde brutal 3px negro + sombra plana -->
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: {_SURFACE}; border: 3px solid {_INK}; border-collapse: separate; box-shadow: 4px 4px 0px {_INK}; max-width: 600px;">

          <!-- Barra de acento azul superior (5px, igual que ::before de la página) -->
          <tr>
            <td style="background-color: {_ACCENT}; height: 5px; padding: 0; font-size: 0; line-height: 0;">&nbsp;</td>
          </tr>

          <!-- Header con wordmark INES -->
          <tr>
            <td style="padding: 18px 28px; background-color: {_SURFACE}; border-bottom: 3px solid {_INK};">
              <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="border-left: 5px solid {_ACCENT}; padding-left: 12px;">
                    <span style="font-size: 16px; font-weight: 700; letter-spacing: 0.06em; color: {_TEXT_PRIMARY}; display: block; line-height: 1.2; text-transform: uppercase;">{_BRAND_NAME}</span>
                    <span style="font-size: 11px; font-weight: 500; color: {_TEXT_SECONDARY}; display: block; margin-top: 2px; letter-spacing: 0.03em;">{_BRAND_SUBTITLE}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          {inner_html}

          <!-- Footer -->
          <tr>
            <td style="padding: 16px 28px; border-top: 3px solid {_INK}; background-color: {_BG}; font-size: 11px; color: {_TEXT_MUTED}; text-align: center; line-height: 1.6; letter-spacing: 0.01em;">
              {_FOOTER_TEXT}
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_details_table(details: Dict[str, str]) -> str:


    rows = "".join(f"""
          <tr>
            <td style="padding: 10px 0; border-bottom: 1px solid {_BORDER_LIGHT}; font-size: 12px; font-weight: 700; width: 38%; color: {_TEXT_PRIMARY}; vertical-align: top; letter-spacing: 0.01em;">{k}</td>
            <td style="padding: 10px 0; border-bottom: 1px solid {_BORDER_LIGHT}; font-size: 13px; color: {_TEXT_PRIMARY}; vertical-align: top;">{v}</td>
          </tr>""" for k, v in details.items())
    return f"""
        <p style="margin: 20px 0 8px 0; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: {_TEXT_SECONDARY}; text-transform: uppercase;">{_DETAILS_LABEL}</p>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; border-top: 2px solid {_INK}; margin-bottom: 24px;">
          {rows}
        </table>"""


def _build_action_box(action_text: str, colors: Dict[str, str]) -> str:


    return f"""
        <div style="margin: 20px 0 0 0; padding: 16px 20px; background-color: {colors['bg']}; border: 2px solid {_INK}; border-left: 5px solid {colors['text']}; border-radius: 0;">
          <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {colors['text']}; display: block; margin-bottom: 6px; text-transform: uppercase;">{_ACTION_LABEL}</span>
          <p style="margin: 0; font-size: 13px; font-weight: 500; color: {_TEXT_PRIMARY}; line-height: 1.6;">{action_text}</p>
        </div>"""


def _build_alert_html(
    risk_level: str,
    context: str = _CONTEXT_DEFAULT,
    details: Optional[Dict[str, str]] = None,
    action_text: str = "",
) -> str:


    colors = _get_email_colors(risk_level)

    banner = f"""
          <tr>
            <td style="padding: 20px 28px; border-top: 0; border-bottom: 3px solid {_INK}; background-color: {colors['bg']}; border-left: 5px solid {colors['text']};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {colors['text']}; display: block; margin-bottom: 6px; text-transform: uppercase;">{_ALERT_TAG_LABEL}: {risk_level}</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: {_TEXT_PRIMARY};">{_ALERT_H1}</h1>
            </td>
          </tr>"""

    inner = f'<p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">{context}</p>'

    if details:
        inner += _build_details_table(details)

    if action_text:
        inner += _build_action_box(action_text, colors)

    body_row = f"""
          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">
              {inner}
            </td>
          </tr>"""

    return _build_email_shell(banner + body_row)


def build_activation_email_html(link: str) -> str:


    inner_html = f"""
          <!-- Banner de cabecera -->
          <tr>
            <td style="padding: 20px 28px; border-top: 0; border-bottom: 3px solid {_INK}; background-color: {_ACCENT_BG}; border-left: 5px solid {_ACCENT};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_ACCENT}; display: block; margin-bottom: 6px; text-transform: uppercase;">Acceso al sistema</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: {_TEXT_PRIMARY};">Activación de su cuenta</h1>
            </td>
          </tr>

          <!-- Cuerpo -->
          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">Estimado/a usuario/a:</p>
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">Su cuenta ha sido registrada en el <strong style="color: {_TEXT_PRIMARY};">Sistema de Monitoreo INES</strong>. Para completar el proceso de registro y acceder a todas las funciones de la plataforma, es necesario que establezca su nombre de usuario y contraseña.</p>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">Para ello, haga clic en el botón que figura a continuación:</p>

              <!-- Botón CTA: estilo brutal (borde negro + sombra plana) -->
              <div style="margin: 0 0 28px 0; text-align: left;">
                <a href="{link}" target="_blank"
                   style="background-color: {_ACCENT}; color: {_SURFACE}; text-decoration: none; padding: 12px 28px; font-size: 13px; font-weight: 700; letter-spacing: 0.05em; display: inline-block; border: 2px solid {_INK}; border-radius: 0; box-shadow: 4px 4px 0px {_INK};">
                  Completar registro
                </a>
              </div>

              <!-- Caja de información de seguridad -->
              <div style="padding: 16px 20px; background-color: {_ACCENT_BG}; border: 2px solid {_INK}; border-left: 5px solid {_ACCENT}; border-radius: 0; margin-bottom: 24px;">
                <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_ACCENT}; display: block; margin-bottom: 6px; text-transform: uppercase;">Información de seguridad</span>
                <p style="margin: 0 0 6px 0; font-size: 13px; color: {_TEXT_SECONDARY};">• Este enlace es válido durante las próximas <strong style="color: {_TEXT_PRIMARY};">24 horas</strong>.</p>
                <p style="margin: 0; font-size: 13px; color: {_TEXT_SECONDARY};">• Si usted no ha solicitado este registro, puede ignorar el presente correo sin que ello implique ninguna consecuencia.</p>
              </div>

              <!-- Enlace de respaldo -->
              <p style="margin: 0; font-size: 12px; color: {_TEXT_MUTED};">Si el botón no funciona correctamente, copie y pegue la siguiente dirección en su navegador:<br>
              <a href="{link}" style="color: {_ACCENT}; text-decoration: underline; word-break: break-all;">{link}</a></p>
            </td>
          </tr>"""

    return _build_email_shell(inner_html)


_RESOLUTION_H1 = "Alerta resuelta"
_RESOLUTION_CONTEXT = (
    "Una alerta previamente activa ha sido marcada como resuelta "
    "por un administrador del sistema."
)


def build_resolution_email_html(
    variable: str,
    value: str,
    original_risk: str,
    building_name: str,
    action: str,
) -> str:
    from apps.sensors.sensor_config import RISK_RESUELTA
    import datetime as _dt

    colors = _get_email_colors(RISK_RESUELTA)
    now_str = _dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    value_display = f"{value}" if value else "N/A"

    banner = f"""
          <tr>
            <td style="padding: 20px 28px; border-top: 0; border-bottom: 3px solid {_INK}; background-color: {colors['bg']}; border-left: 5px solid {colors['text']};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {colors['text']}; display: block; margin-bottom: 6px; text-transform: uppercase;">{_ALERT_TAG_LABEL}: Resuelta</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: {_TEXT_PRIMARY};">{_RESOLUTION_H1}</h1>
            </td>
          </tr>"""

    details = {
        "Fecha y hora": now_str,
        "Edificio": building_name or "N/A",
        "Parámetro": variable,
        "Lectura": value_display,
        "Severidad original": original_risk,
        "Estado": "Resuelta",
    }

    inner = f'<p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">{_RESOLUTION_CONTEXT}</p>'
    inner += _build_details_table(details)

    if action:
        inner += _build_action_box(action, colors)

    body_row = f"""
          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">
              {inner}
            </td>
          </tr>"""

    return _build_email_shell(banner + body_row)


def build_report_email_html(edificio: str = "", contexto: str = "") -> str:


    ctx = contexto or (
        f"Se adjunta el informe en formato PDF con el estado actual de los "
        f"sensores de infraestructura{' de ' + edificio if edificio else ''}. "
        f"El documento incluye las lecturas más recientes, las estadísticas de "
        f"operación y un resumen del nivel de riesgo de cada parámetro monitoreado."
    )
    inner_html = f"""
          <!-- Banner de cabecera (reporte de estado) -->
          <tr>
            <td style="padding: 20px 28px; border-top: 0; border-bottom: 3px solid {_INK}; background-color: {_ACCENT_BG}; border-left: 5px solid {_ACCENT};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_ACCENT}; display: block; margin-bottom: 6px; text-transform: uppercase;">Reporte de monitoreo</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: {_TEXT_PRIMARY};">Estado actual del sistema de infraestructura</h1>
            </td>
          </tr>

          <!-- Cuerpo -->
          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">{ctx}</p>
              <p style="margin: 0; font-size: 13px; color: {_TEXT_MUTED};">El informe PDF se encuentra adjunto al presente correo.</p>
            </td>
          </tr>"""
    return _build_email_shell(inner_html)


def build_standard_email_body(
    titulo: str,
    detalles: Optional[Dict[str, str]] = None,
    accion: str = "",
    contexto: str = "",
) -> str:


    lines = [titulo, ""]
    if contexto:
        lines.append(contexto)
        lines.append("")
    if detalles:
        lines.append("DETALLES DEL EVENTO:")
        lines.append("-" * 44)
        for k, v in detalles.items():
            lines.append(f"{k}:{' ' * max(1, 18 - len(k))}{v}")
        lines.append("")
    if accion:
        lines.append("MEDIDA CORRECTIVA RECOMENDADA:")
        lines.append("-" * 44)
        lines.append(f"Acción: {accion}")
        lines.append("")
    return "\n".join(lines)


def _build_mime_message(
    html_body: str,
    plain_body: str,
    subject: str,
    from_addr: str,
    attachment_pdf: Optional[bytes] = None,
    attachment_name: str = "reporte.pdf",
):
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


def send_email_raw(
    to_addrs: List[str],
    subject: str,
    html_body: str,
    plain_body: str = "",
    attachment_pdf: Optional[bytes] = None,
    attachment_name: str = "reporte.pdf",
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

    details: Dict[str, str] = {}
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

    attachment_bytes = None
    attachment_filename = "report.pdf"
    if config.attachment:
        config.attachment.pdf_data.seek(0)
        attachment_bytes = config.attachment.pdf_data.read()
        attachment_filename = config.attachment.filename

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
