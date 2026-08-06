import { useState, useEffect, useRef } from 'react';

/**
 * TimerBadge — displays a live stopwatch timer when status is 'running',
 * and freezes the final elapsed time when status becomes 'done' or 'error'.
 *
 * Props:
 *   status  {string}  'idle' | 'running' | 'done' | 'error'
 *   label   {string}  Optional prefix text (e.g. "Time:", "Elapsed:")
 *   style   {object}  Optional inline style overrides
 */
export default function TimerBadge({ status, label = '', style = {} }) {
  const [elapsed, setElapsed] = useState(0);
  const startTimeRef = useRef(null);

  useEffect(() => {
    if (status === 'idle') {
      setElapsed(0);
      startTimeRef.current = null;
      return;
    }

    if (status === 'running') {
      if (!startTimeRef.current) {
        startTimeRef.current = Date.now();
      }
      const interval = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [status]);

  if (status === 'idle' && elapsed === 0) {
    return null;
  }

  const isRunning = status === 'running';

  return (
    <span
      className={`timer-badge ${isRunning ? 'timer-badge--running' : 'timer-badge--stopped'}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        padding: '3px 8px',
        fontSize: '12px',
        fontWeight: 500,
        fontFamily: 'var(--font-mono, monospace)',
        background: isRunning ? '#eff6ff' : '#f8fafc',
        color: isRunning ? '#1d4ed8' : '#475569',
        border: `1px solid ${isRunning ? '#93c5fd' : '#cbd5e1'}`,
        letterSpacing: '0.02em',
        ...style,
      }}
      title={isRunning ? 'Execution in progress' : 'Total execution time'}
    >
      <span style={{ fontSize: '11px' }}>⏱️</span>
      {label && <span style={{ opacity: 0.8, fontSize: '11px' }}>{label}</span>}
      <span>{formatTime(elapsed)}</span>
      {isRunning && (
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: '#2563eb',
            animation: 'timer-pulse 1.2s infinite ease-in-out',
            marginLeft: '2px',
          }}
        />
      )}
    </span>
  );
}

export function formatTime(totalSeconds) {
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}
