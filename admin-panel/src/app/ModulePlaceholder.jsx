export function ModulePlaceholder({ module, tenant }) {
  return (
    <section className="module-card">
      <p className="eyebrow">Placeholder MVP</p>
      <h2>{module.label}</h2>
      <p>{module.summary}</p>

      <dl className="context-grid">
        <div>
          <dt>Tenant seleccionado</dt>
          <dd>{tenant?.label}</dd>
        </div>
        <div>
          <dt>Estado</dt>
          <dd>Placeholder navegable</dd>
        </div>
      </dl>

      <h3>Alcance previsto</h3>
      <ul>
        {module.scope.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
