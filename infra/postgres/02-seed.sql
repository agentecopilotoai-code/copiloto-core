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

-- TASK-0050: cada tenant arranca con una sede "Principal" para que el flujo
-- multi-sede sea retro-compatible (1 branch ⇒ se salta el paso de selección).
insert into app.branches (tenant_id, name, code, country, timezone, is_active, sort_order)
select id, 'Principal', 'principal', country_code, timezone, true, 0
from app.tenants
on conflict (tenant_id, code) do nothing;

insert into app.resources (tenant_id, vertical_code, resource_type, code, name, capabilities, branch_id)
select t.id, t.vertical_code, 'staff', 'default', 'Recurso principal', '{"default":true}'::jsonb, b.id
from app.tenants t
left join app.branches b on b.tenant_id = t.id and b.code = 'principal'
on conflict (tenant_id, code) do nothing;

-- Preconstructed retention/reactivation segments seeded per tenant.  The
-- application layer also seeds these on tenant creation; the SQL seed makes
-- the demo tenants ready for E2E flows without bootstrapping through the API.
insert into app.contact_segments (tenant_id, name, description, kind, rules, is_system)
select t.id, s.name, s.description, 'dynamic', s.rules::jsonb, true
from app.tenants t
cross join (values
  ('Sin visita en 60+ días',
   'Contactos cuya última cita fue hace más de 60 días.',
   '{"all_of":[{"field":"last_appointment_at","op":"lt_days_ago","value":60}]}'),
  ('Clientes recurrentes (3+ citas)',
   'Han completado 3 o más citas.',
   '{"all_of":[{"field":"total_appointments_completed","op":"gte","value":3}]}'),
  ('VIP (gasto > $500.000)',
   'Han gastado más de $500.000 en servicios completados.',
   '{"all_of":[{"field":"total_spent","op":"gt","value":500000}]}'),
  ('Primer contacto sin agendar',
   'No registran citas completadas todavía.',
   '{"all_of":[{"field":"total_appointments_completed","op":"eq","value":0},{"field":"last_appointment_at","op":"is_null"}]}'),
  ('No-show reciente (30 días)',
   'Tuvieron al menos un no-show en los últimos 30 días.',
   '{"all_of":[{"field":"total_appointments_no_show","op":"in_window_days","value":30}]}')
) as s(name, description, rules)
on conflict (tenant_id, name) do nothing;
