"""Templates de email — HTML + plaintext en español."""
from app.services.email_templates.invitation import (
    render_invitation_email,
)

__all__ = ['render_invitation_email']
