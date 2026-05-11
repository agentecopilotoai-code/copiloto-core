insert into app.tenants (id, slug, legal_name, display_name, vertical_code, status)
values
  ('11111111-1111-1111-1111-111111111111', 'demo-taller', 'Demo Taller SAS', 'Demo Taller', 'field_service', 'active'),
  ('22222222-2222-2222-2222-222222222222', 'demo-barberia', 'Demo Barberia SAS', 'Demo Barbería', 'beauty', 'active'),
  ('33333333-3333-3333-3333-333333333333', 'demo-mascotas', 'Demo Mascotas SAS', 'Demo Mascotas', 'pet_grooming', 'active')
on conflict (slug) do nothing;

insert into app.tenant_settings (tenant_id, max_bot_turns, business_hours, escalation_policy)
select id,
  10,
  '{"mon-fri":[{"start":"08:00","end":"18:00"}],"sat":[{"start":"09:00","end":"13:00"}]}'::jsonb,
  '{
    "handoff_message": "En este momento te voy a conectar con uno de nuestros asesores. En breve te atienden 😊",
    "triggers": {
      "keywords": ["humano", "asesor", "agente", "persona", "queja", "reclamo", "urgente"]
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
select id, vertical_code,
  case vertical_code when 'field_service' then 'technician' when 'beauty' then 'chair' else 'groomer' end,
  'default', 'Recurso principal', '{"default":true}'::jsonb
from app.tenants
on conflict (tenant_id, code) do nothing;
