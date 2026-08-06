/**
 * Header — sticky top bar with branding and step progress indicator.
 */
export default function Header({ shortlisterStatus, linkedinStatus, onReset }) {
  function stepClass(status) {
    if (status === 'done') return 'step--done';
    if (status === 'running') return 'step--active';
    return '';
  }

  return (
    <header className="header">
      <div className="header-brand">
        <span className="header-title">Agent Pipeline</span>
        <span className="header-subtitle">Shortlister + LinkedIn Finder</span>
      </div>

      <div className="header-right">
        <nav className="steps" aria-label="Pipeline progress">
          <div className={`step ${stepClass(shortlisterStatus)}`}>
            <span className="step-num">1</span>
            <span>Shortlister</span>
          </div>
          <span className="step-arrow" aria-hidden="true">&#8594;</span>
          <div className={`step ${stepClass(linkedinStatus)}`}>
            <span className="step-num">2</span>
            <span>LinkedIn Finder</span>
          </div>
        </nav>

        <button
          id="btn-reset-all"
          className="btn btn-ghost"
          onClick={onReset}
          title="Reset both agents to idle state"
        >
          Reset All
        </button>
      </div>
    </header>
  );
}
