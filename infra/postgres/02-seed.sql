insert into app.tenants (id, slug, legal_name, display_name, vertical_code, business_type_label, status)
values
  ('11111111-1111-1111-1111-111111111111', 'demo-taller', 'Demo Taller SAS', 'Demo Taller', 'taller_mecanico', 'Taller mecánico', 'active'),
  ('22222222-2222-2222-2222-222222222222', 'demo-barberia', 'Demo Barberia SAS', 'Demo Barbería', 'barberia', 'Barbería', 'active'),
  ('33333333-3333-3333-3333-333333333333', 'demo-mascotas', 'Demo Mascotas SAS', 'Demo Mascotas', 'veterinaria', 'Veterinaria', 'active')
on conflict (slug) do nothing;

insert into app.tenant_settings (tenant_id, business_hours, escalation_policy)
select id,
  '{"weekly_schedule":{"mon":[{"start":"08:00","end":"18:00"}],"tue":[{"start":"08:00","end":"18:00"}],"wed":[{"start":"08:00","end":"18:00"}],"thu":[{"start":"08:00","end":"18:00"}],"fri":[{"start":"08:00","end":"18:00"}],"sat":[{"start":"09:00","end":"13:00"}],"sun":[]}}'::jsonb,
  '{
    "enabled": true,
    "queue": "default-support",
    "priority": "normal",
    "handoff_message": "En este momento te voy a conectar con uno de nuestros asesores. En breve te atienden 😊",
    "triggers": {
      "keywords": ["humano", "asesor", "agente", "persona", "queja", "reclamo", "urgente"],
      "after_bot_turns": 10,
      "confidence_below": 0.55
    }
  }'::jsonb
from app.tenants
on conflict (tenant_id) do nothing;

insert into app.tenant_channels (tenant_id, provider, business_id, waba_id, phone_number_id, token_ref, app_secret_ref, account_mode, status)
select id, 'whatsapp_cloud_api', 'demo-business-id', 'demo-waba-id', 'demo-phone-' || slug,
  'secrets/tenants/' || id || '/meta_access_token',
  'secrets/tenants/' || id || '/whatsapp_app_secret',
  'mock', 'active'
from app.tenants
on conflict (tenant_id, provider) do nothing;

insert into app.resources (tenant_id, vertical_code, resource_type, code, name, capabilities)
select id, vertical_code, 'staff', 'default', 'Recurso principal', '{"default":true}'::jsonb
from app.tenants
on conflict (tenant_id, code) do nothing;
