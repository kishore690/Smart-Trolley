export default function StateMessage({ icon, title, tone = 'neutral', children, action, pulse = false }) {
  return (
    <section className="state">
      <div className={`state-icon tone-${tone}${pulse ? ' pulse' : ''}`} aria-hidden="true">{icon}</div>
      <h1 className="state-title">{title}</h1>
      <div className="state-body">{children}</div>
      {action}
    </section>
  );
}
