/**
 * AuthCard — the shared chrome for every signed-out / first-run screen.
 */
export default function AuthCard({ title, subtitle, children, footer }) {
  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-card-header">
          <div className="auth-card-title">{title}</div>
          {subtitle && <div className="auth-card-subtitle">{subtitle}</div>}
        </div>
        <div className="auth-card-body">{children}</div>
        {footer && <div className="auth-card-footer">{footer}</div>}
      </div>
    </div>
  );
}
