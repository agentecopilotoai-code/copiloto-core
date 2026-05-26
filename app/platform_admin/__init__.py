"""Platform Admin — endpoints transversales del platform_owner.

Este paquete vive en el CORE. Contiene endpoints expuestos bajo
``/v1/platform/*`` que solo el ``platform_owner`` con MFA puede llamar:

- ``/v1/platform/ai-providers/*`` — config cross-modalidad de proveedores IA
   (LLM, image, video, TTS, STT). Recurso transversal — cualquier módulo
   (GD, influencer, chatbot, futuros) lo consume vía ``app.ai.registry``.
- ``/v1/platform/tenant-modules/*`` — activar/desactivar módulos opt-in
   por tenant (``app.tenant_modules``).

Antes vivían en ``app/influencer/admin_routes.py`` por razón histórica
(el módulo influencer fue el primero en necesitarlos). Al separar el core,
se promueven al paquete ``app/platform_admin/`` para reflejar que NO
pertenecen al producto influencer.
"""
