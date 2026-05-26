-- ============================================================================
-- Copiloto Core — Seed mínimo del core
-- ============================================================================
-- Solo inserta el dataset MÍNIMO que el core necesita para funcionar:
-- un tenant demo + activación de módulos opt-in vacía.
--
-- Productos (chatbot/influencer/gd) seedean su propio dataset en
-- `infra/postgres/modules/<modulo>.sql` cuando se instalan sobre el core.
-- ============================================================================

-- Tenant demo para development local. En producción este insert NO se
-- ejecuta (no hay un script que lo cargue automáticamente — solo el
-- bootstrap del dev environment).
insert into app.tenants (id, slug, legal_name, display_name, vertical_code, status)
values
  ('11111111-1111-1111-1111-111111111111', 'demo', 'Demo Tenant SAS', 'Demo Tenant', 'generic', 'active')
on conflict (slug) do nothing;
