import logging
import time
from typing import Dict, Optional


logger = logging.getLogger(__name__)

_BRAND_NAME      = "INES"
_BRAND_SUBTITLE  = "Sistema inteligente en monitoreo"
_ALERT_H1        = "Anomalía detectada en la infraestructura"
_ALERT_TAG_LABEL = "Severidad"
_ACTION_LABEL    = "Medida correctiva recomendada"
_DETAILS_LABEL   = "Detalles del evento"
_FOOTER_TEXT     = (
    "Este mensaje ha sido generado automáticamente por INES — Sistema inteligente en monitoreo.<br>"
    "Por favor, no responda a este correo."
)
_CONTEXT_DEFAULT = (
    "El sistema ha registrado una lectura fuera de los rangos operativos "
    "establecidos para el presente edificio. A continuación se detallan "
    "los parámetros del evento y la medida correctiva recomendada."
)
_ACCENT          = "#2563eb"
_INK             = "#0a0a0a"
_BG              = "#f5f5f5"
_SURFACE         = "#ffffff"
_TEXT_PRIMARY    = "#0a0a0a"
_TEXT_SECONDARY  = "#5f5f5f"
_TEXT_MUTED      = "#9e9e9e"
_ACCENT_BG       = "#eff6ff"
_BORDER_LIGHT    = "#f3f4f6"


def _get_email_colors(risk_level: str) -> Dict[str, str]:
    from apps.sensors.sensor_config import RISK_COLORS
    return RISK_COLORS.get(risk_level, {}).get("email", {"bg": "#f1f5f9", "border": "#cbd5e1", "text": "#475569"})


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
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: {_SURFACE}; border: 3px solid {_INK}; border-collapse: separate; box-shadow: 4px 4px 0px {_INK}; max-width: 600px;">
          <tr>
            <td style="background-color: {_ACCENT}; height: 5px; padding: 0; font-size: 0; line-height: 0;">&nbsp;</td>
          </tr>
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
          <tr>
            <td style="padding: 20px 28px; border-top: 0; border-bottom: 3px solid {_INK}; background-color: {_ACCENT_BG}; border-left: 5px solid {_ACCENT};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_ACCENT}; display: block; margin-bottom: 6px; text-transform: uppercase;">Acceso al sistema</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: {_TEXT_PRIMARY};">Activación de su cuenta</h1>
            </td>
          </tr>

          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">Estimado/a usuario/a:</p>
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">Su cuenta ha sido registrada en el <strong style="color: {_TEXT_PRIMARY};">INES — Sistema inteligente en monitoreo</strong>. Para completar el proceso de registro y acceder a todas las funciones de la plataforma, es necesario que establezca su nombre de usuario y contraseña.</p>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">Para ello, haga clic en el botón que figura a continuación:</p>

              <div style="margin: 0 0 28px 0; text-align: left;">
                <a href="{link}" target="_blank"
                   style="background-color: {_ACCENT}; color: {_SURFACE}; text-decoration: none; padding: 12px 28px; font-size: 13px; font-weight: 700; letter-spacing: 0.05em; display: inline-block; border: 2px solid {_INK}; border-radius: 0; box-shadow: 4px 4px 0px {_INK};">
                  Activar cuenta
                </a>
              </div>

              <div style="padding: 16px 20px; background-color: {_ACCENT_BG}; border: 2px solid {_INK}; border-left: 5px solid {_ACCENT}; border-radius: 0; margin-bottom: 24px;">
                <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_ACCENT}; display: block; margin-bottom: 6px; text-transform: uppercase;">Información de seguridad</span>
                <p style="margin: 0 0 6px 0; font-size: 13px; color: {_TEXT_SECONDARY};">• Este enlace es válido durante las próximas <strong style="color: {_TEXT_PRIMARY};">24 horas</strong>.</p>
                <p style="margin: 0; font-size: 13px; color: {_TEXT_SECONDARY};">• Si usted no ha solicitado este registro, puede ignorar el presente correo sin que ello implique ninguna consecuencia.</p>
              </div>

              <p style="margin: 0; font-size: 12px; color: {_TEXT_MUTED};">Si el botón no funciona correctamente, copie y pegue la siguiente dirección en su navegador:<br>
              <a href="{link}" style="color: {_ACCENT}; text-decoration: underline; word-break: break-all;">{link}</a></p>
            </td>
          </tr>"""

    return _build_email_shell(inner_html)


def build_report_email_html(edificio: str = "", contexto: str = "") -> str:
    ctx = contexto or (
        f"Se adjunta el informe en formato PDF con el estado actual de los "
        f"sensores de infraestructura{' de ' + edificio if edificio else ''}. "
        f"El documento incluye las lecturas más recientes, las estadísticas de "
        f"operación y un resumen del nivel de riesgo de cada parámetro monitoreado."
    )
    inner_html = f"""
          <tr>
            <td style="padding: 20px 28px; border-top: 0; border-bottom: 3px solid {_INK}; background-color: {_ACCENT_BG}; border-left: 5px solid {_ACCENT};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_ACCENT}; display: block; margin-bottom: 6px; text-transform: uppercase;">Reporte de monitoreo</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: {_TEXT_PRIMARY};">Estado actual del sistema de infraestructura</h1>
            </td>
          </tr>

          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">{ctx}</p>
              <p style="margin: 0; font-size: 13px; color: {_TEXT_MUTED};">El informe PDF se encuentra adjunto al presente correo.</p>
            </td>
          </tr>"""
    return _build_email_shell(inner_html)


def build_compound_alert_email_html(
    fault_name: str,
    risk_level: str,
    affected_vars: dict,
    action: str = "",
    building_name: str = "",
) -> str:
    colors = _get_email_colors(risk_level)

    banner = f"""
          <tr>
            <td style="padding: 20px 28px; border-top: 0; border-bottom: 3px solid {_INK}; background-color: {colors['bg']}; border-left: 5px solid {colors['text']};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {colors['text']}; display: block; margin-bottom: 6px; text-transform: uppercase;">{_ALERT_TAG_LABEL}: {risk_level}</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: {_TEXT_PRIMARY};">Falla detectada: {fault_name}</h1>
            </td>
          </tr>"""

    num_vars = len(affected_vars)
    contexto = (
        f"Se ha detectado una <strong style='color: {_TEXT_PRIMARY};'>{fault_name}</strong> "
        f"que afecta <strong style='color: {_TEXT_PRIMARY};'>{num_vars} sensor(es)</strong>. "
        f"A continuación se detallan las lecturas de cada parámetro comprometido."
    )
    inner = f'<p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">{contexto}</p>'

    if building_name:
        inner += f'<p style="margin: 0 0 16px 0; font-size: 13px; color: {_TEXT_SECONDARY};"><strong style="color: {_TEXT_PRIMARY};">Edificio:</strong> {building_name}</p>'

    var_rows = ""
    for var_name, info in affected_vars.items():
        display_name = info.get("display_name", var_name)
        value = info.get("value", "N/A")
        unit = info.get("unit", "")
        var_risk = info.get("risk", risk_level)
        var_colors = _get_email_colors(var_risk)
        value_str = f"{value} {unit}".strip()
        var_rows += f"""
          <tr>
            <td style="padding: 10px 12px; border-bottom: 1px solid {_BORDER_LIGHT}; font-size: 13px; font-weight: 700; color: {_TEXT_PRIMARY};">{display_name}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid {_BORDER_LIGHT}; font-size: 13px; color: {_TEXT_PRIMARY}; text-align: right;">{value_str}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid {_BORDER_LIGHT}; font-size: 12px; font-weight: 700; color: {var_colors['text']}; text-align: right;">{var_risk}</td>
          </tr>"""

    inner += f"""
        <p style="margin: 20px 0 8px 0; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: {_TEXT_SECONDARY}; text-transform: uppercase;">{_DETAILS_LABEL}</p>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; border: 2px solid {_INK}; margin-bottom: 24px;">
          <tr style="background-color: {_BG};">
            <td style="padding: 8px 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.05em; color: {_TEXT_SECONDARY}; text-transform: uppercase;">Parámetro</td>
            <td style="padding: 8px 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.05em; color: {_TEXT_SECONDARY}; text-transform: uppercase; text-align: right;">Lectura</td>
            <td style="padding: 8px 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.05em; color: {_TEXT_SECONDARY}; text-transform: uppercase; text-align: right;">Severidad</td>
          </tr>
          {var_rows}
        </table>"""

    if action:
        inner += _build_action_box(action, colors)

    timestamp = time.strftime("%d/%m/%Y %H:%M:%S")
    inner += f'<p style="margin: 16px 0 0 0; font-size: 11px; color: {_TEXT_MUTED};">Fecha y hora del evento: {timestamp}</p>'

    body_row = f"""
          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: {_TEXT_SECONDARY};">
              {inner}
            </td>
          </tr>"""

    return _build_email_shell(banner + body_row)
