"""Template de invitación a tenant — bilingual HTML/plaintext en español.

Diseño deliberadamente simple:
- HTML inline-styles (los email clients odian <style> blocks y CSS externo).
- Tabla-based layout (Outlook / Gmail Web son el peor cliente CSS).
- Plaintext SIEMPRE provisto (Gmail+Apple Mail rankean spam si solo HTML).
- Idioma español (audiencia es Colombia/govtech).
- Sin imágenes externas (tracking + spam triggers).
- Sin call-to-action ambiguo: UN solo botón "Aceptar invitación".

Para iterar a templates más pro: migrar a `react-email` o `mjml` cuando
sea necesario. Por ahora con este alcanza.
"""
from __future__ import annotations

import html as _html
from dataclasses import dataclass


@dataclass(frozen=True)
class InvitationRendered:
    subject: str
    html: str
    text: str


# Mapeo de role → label en español (lo que ve el invitado).
_ROLE_LABELS: dict[str, str] = {
    'owner': 'Propietario',
    'admin': 'Administrador',
    'manager': 'Gerente',
    'agent': 'Agente',
    'viewer': 'Lector',
}


def _role_label(role: str) -> str:
    return _ROLE_LABELS.get(role, role.capitalize())


def render_invitation_email(
    *,
    invitee_email: str,
    tenant_name: str,
    role: str,
    inviter_name: str | None,
    inviter_email: str | None,
    accept_url: str,
    expires_in_days: int,
) -> InvitationRendered:
    """Renderiza el email de invitación.

    Args:
        invitee_email: a quién va el email (solo display, no auth).
        tenant_name: nombre del tenant que invita ("Clínica Norte").
        role: rol asignado (`admin` / `manager` / etc.) — se mapea a label.
        inviter_name: nombre del admin que invitó (puede ser None).
        inviter_email: email del admin (para reply_to display, opcional).
        accept_url: link absoluto que el invitee abre para aceptar.
        expires_in_days: días hasta que el link expire.

    Returns:
        InvitationRendered con subject, html, text.
    """
    role_es = _role_label(role)
    inviter_display = inviter_name or inviter_email or 'el administrador'
    # Sanitización HTML defensiva — no confiamos en tenant_name (un tenant
    # con nombre malicioso podría tratar de inyectar HTML).
    tenant_name_safe = _html.escape(tenant_name)
    inviter_display_safe = _html.escape(inviter_display)
    role_es_safe = _html.escape(role_es)
    accept_url_safe = _html.escape(accept_url, quote=True)

    subject = f'Te invitaron a {tenant_name} en CopilotoIA'

    html = _HTML_TEMPLATE.format(
        tenant_name=tenant_name_safe,
        inviter_display=inviter_display_safe,
        role_es=role_es_safe,
        accept_url=accept_url_safe,
        accept_url_display=_html.escape(accept_url),
        expires_in_days=expires_in_days,
    )

    text = _TEXT_TEMPLATE.format(
        tenant_name=tenant_name,
        inviter_display=inviter_display,
        role_es=role_es,
        accept_url=accept_url,
        expires_in_days=expires_in_days,
    )

    return InvitationRendered(subject=subject, html=html, text=text)


# ─── Templates ───────────────────────────────────────────────────────────


_HTML_TEMPLATE = """\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Invitación a CopilotoIA</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f4f5f7;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="background-color:#ffffff;border-radius:8px;border:1px solid #e5e7eb;max-width:560px;width:100%;">
          <tr>
            <td style="padding:32px 32px 16px 32px;">
              <h1 style="margin:0 0 8px 0;font-size:20px;font-weight:600;color:#111827;">
                Te invitaron a CopilotoIA
              </h1>
              <p style="margin:0;font-size:14px;color:#6b7280;">
                Una nueva organización quiere agregarte a su equipo.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:0 32px 16px 32px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f9fafb;border-radius:6px;border:1px solid #e5e7eb;">
                <tr>
                  <td style="padding:16px 20px;">
                    <p style="margin:0 0 6px 0;font-size:13px;color:#6b7280;">Organización</p>
                    <p style="margin:0 0 12px 0;font-size:16px;font-weight:600;color:#111827;">
                      {tenant_name}
                    </p>
                    <p style="margin:0 0 6px 0;font-size:13px;color:#6b7280;">Rol asignado</p>
                    <p style="margin:0 0 12px 0;font-size:16px;font-weight:600;color:#111827;">
                      {role_es}
                    </p>
                    <p style="margin:0 0 6px 0;font-size:13px;color:#6b7280;">Invitado por</p>
                    <p style="margin:0;font-size:14px;color:#374151;">
                      {inviter_display}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:8px 32px 24px 32px;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="border-radius:6px;background-color:#1f2937;">
                    <a href="{accept_url}"
                       style="display:inline-block;padding:12px 24px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:6px;">
                      Aceptar invitación
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:16px 0 0 0;font-size:12px;color:#6b7280;">
                ¿El botón no funciona? Copia este enlace en tu navegador:
              </p>
              <p style="margin:4px 0 0 0;font-size:12px;color:#374151;word-break:break-all;">
                <a href="{accept_url}" style="color:#374151;text-decoration:underline;">{accept_url_display}</a>
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 32px 24px 32px;border-top:1px solid #e5e7eb;">
              <p style="margin:0;font-size:12px;color:#6b7280;line-height:1.5;">
                Este enlace es de un solo uso y expira en {expires_in_days} días.
                Si no esperabas esta invitación, puedes ignorar este correo de forma segura.
              </p>
            </td>
          </tr>
        </table>
        <p style="margin:24px 0 0 0;font-size:11px;color:#9ca3af;">
          Enviado por CopilotoIA &middot; Si crees que esto es un error, responde a este correo.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>
"""


_TEXT_TEMPLATE = """\
Te invitaron a CopilotoIA
─────────────────────────

Una nueva organización quiere agregarte a su equipo.

Organización: {tenant_name}
Rol asignado: {role_es}
Invitado por: {inviter_display}

Para aceptar, abre este enlace:

{accept_url}

Este enlace es de un solo uso y expira en {expires_in_days} días.
Si no esperabas esta invitación, puedes ignorar este correo.

—
CopilotoIA
"""
