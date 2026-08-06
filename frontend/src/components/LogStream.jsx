import { useState, useEffect, useRef } from 'react';
import TimerBadge from './TimerBadge';

/**
 * LogStream — connects to an SSE endpoint and renders a terminal-style log console.
 *
 * Props:
 *   url       {string}   SSE endpoint URL.
 *   active    {boolean}  Mount/unmount the SSE connection.
 *   onDone    {function} Called when the stream signals completion.
 *   label     {string}   Console header label.
 */
export default function LogStream({ url, active, onDone, label }) {
  const [lines, setLines] = useState([]);
  const [streamStatus, setStreamStatus] = useState('connecting');
  const bottomRef = useRef(null);
  const esRef = useRef(null);

  useEffect(() => {
    if (!active) return;

    setLines([]);
    setStreamStatus('connecting');

    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener('log', (e) => {
      const data = e.data ?? '';
      setStreamStatus('running');
      setLines(prev => [...prev, data]);
    });

    es.addEventListener('done', (e) => {
      const finalStatus = e.data === 'done' ? 'done' : 'error';
      setStreamStatus(finalStatus);
      es.close();
      esRef.current = null;
      onDone?.(finalStatus);
    });

    // Keepalive pings — ignore
    es.addEventListener('ping', () => {});

    es.onerror = () => {
      // Only treat as error if not gracefully closed
      if (es.readyState !== EventSource.CLOSED) {
        setStreamStatus('error');
      }
      es.close();
      esRef.current = null;
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [url, active]);

  // Auto-scroll to bottom on new lines
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [lines]);

  const statusLabels = {
    connecting: 'Connecting',
    running: 'Running',
    done: 'Completed',
    error: 'Error',
  };

  return (
    <div className="log-stream-wrapper">
      <div className="log-console-header">
        <span className="log-console-label">{label}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <TimerBadge status={streamStatus === 'connecting' ? 'running' : streamStatus} />
          <span className={`log-console-status log-console-status--${streamStatus}`}>
            {streamStatus === 'running' && (
              <span className="status-dot status-dot--running" style={{ marginRight: 6 }} />
            )}
            {statusLabels[streamStatus] ?? streamStatus}
          </span>
        </div>
      </div>

      <div className="log-console-body" role="log" aria-live="polite" aria-label={label}>
        {lines.length === 0 && (
          <span className="log-empty">Waiting for output...</span>
        )}
        {lines.map((line, i) => (
          <LogLine key={i} text={line} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

/**
 * Renders a single log line with optional visual classification.
 */
function LogLine({ text }) {
  const isSeparator = /^─{10,}/.test(text);
  const isProcessing = /^\s*Processing:/.test(text);

  let cls = 'log-line';
  if (isSeparator) cls += ' log-line--separator';
  else if (isProcessing) cls += ' log-line--company';

  return (
    <div className={cls}>
      {text || '\u00A0' /* non-breaking space for blank lines */}
    </div>
  );
}
