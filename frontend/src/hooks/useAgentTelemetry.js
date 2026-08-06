import { useCallback, useEffect, useReducer, useRef } from 'react';

const PHASES = [
  ['query_formulator', 'Formulating query'],
  ['screener_fetch', 'Screening market'],
  ['yfinance_enricher', 'Enriching companies'],
  ['cleaner', 'Cleaning shortlist'],
  ['linkedin_verifier', 'LinkedIn research'],
  ['excel_exporter_node', 'Exporting report'],
];

const MAX_EVENTS = 400;
const MAX_COMPANY_EVENTS = 80;

const emptyPhases = () => PHASES.map(([id, label]) => ({
  id,
  label,
  status: 'pending',
  startedAt: null,
  endedAt: null,
  durationMs: null,
  summary: null,
}));

export const createInitialTelemetryState = () => ({
  connection: 'connecting',
  run: null,
  phases: emptyPhases(),
  companies: {},
  events: [],
  telemetryIntegrity: null,
});

const initialState = createInitialTelemetryState();

const eventTime = (event) => event.timestamp || new Date().toISOString();
const toMs = (timestamp) => timestamp ? new Date(timestamp).getTime() : null;
const eventCompany = (event) => event.company || event.data?.company || event.data?.company_name || null;
const eventBranch = (event) => event.branch || event.data?.branch || null;
const eventExecution = (event) => event.execution_id || event.data?.execution_id || event.run_id;

function durationBetween(startedAt, endedAt) {
  const start = toMs(startedAt);
  const end = toMs(endedAt);
  return start !== null && end !== null ? Math.max(0, end - start) : null;
}

function beginRun(state, runId, timestamp, query = '') {
  return {
    ...createInitialTelemetryState(),
    connection: state.connection,
    phases: emptyPhases(),
    run: {
      id: runId,
      status: 'running',
      startedAt: timestamp || new Date().toISOString(),
      endedAt: null,
      query,
      error: null,
      metrics: {},
    },
  };
}

function updateCompany(state, name, updater) {
  const current = state.companies[name] || {
    name,
    status: 'running',
    startedAt: null,
    endedAt: null,
    durationMs: null,
    currentNode: null,
    currentBranch: null,
    currentExecutionId: null,
    rootExecutionId: null,
    rootTerminalReceived: false,
    executions: {},
    nodes: [],
    activeTools: {},
    toolCount: 0,
    llmCount: 0,
    contacts: [],
    snapshotCount: null,
    snapshotReceivedAt: null,
    eventCount: 0,
    lastMessage: null,
    error: null,
    events: [],
  };
  return {
    ...state,
    companies: {
      ...state.companies,
      [name]: updater(current),
    },
  };
}

function appendEvent(state, event) {
  const entry = {
    id: event.event_id || `${event.run_id}-${event.sequence || Date.now()}`,
    timestamp: eventTime(event),
    level: event.level || 'INFO',
    eventType: event.event_type,
    agent: event.agent,
    component: event.component,
    company: eventCompany(event),
    branch: eventBranch(event),
    executionId: eventExecution(event),
    parentExecutionId: event.parent_execution_id || event.data?.parent_execution_id || null,
    data: event.data || {},
  };
  return { ...state, events: [...state.events, entry].slice(-MAX_EVENTS) };
}

function telemetryIntegrity(state) {
  const lanes = Object.values(state.companies || {}).filter((lane) => lane.rootExecutionId);
  const expectedCompanies = lanes.map((lane) => lane.name).sort();
  const completedCompanies = lanes
    .filter((lane) => lane.rootTerminalReceived)
    .map((lane) => lane.name)
    .sort();
  const receivedSnapshots = lanes
    .filter((lane) => lane.snapshotReceivedAt)
    .map((lane) => lane.name)
    .sort();
  const missingTerminalEvents = expectedCompanies.filter((name) => !completedCompanies.includes(name));
  const missingSnapshots = expectedCompanies.filter((name) => !receivedSnapshots.includes(name));
  const mismatches = [
    ...missingTerminalEvents.map((name) => `Missing company_research terminal event: ${name}`),
    ...missingSnapshots.map((name) => `Missing company contact snapshot: ${name}`),
  ];

  return {
    expectedCompanies,
    completedCompanies,
    receivedSnapshots,
    missingTerminalEvents,
    missingSnapshots,
    mismatches,
    isValid: mismatches.length === 0,
  };
}

function snapshotContacts(data, existingContacts) {
  const contacts = Array.isArray(data.contacts) ? data.contacts : [];
  return contacts.map((contact, index) => {
    const name = String(contact?.name || '').trim();
    const role = String(contact?.role || contact?.position || '').trim();
    const existing = existingContacts.find((candidate) => (
      candidate.name.trim().toLowerCase() === name.toLowerCase()
      && candidate.role.trim().toLowerCase() === role.toLowerCase()
    ));
    return {
      key: `snapshot:${name}:${role}:${index}`,
      name: name || 'Unknown contact',
      role,
      url: existing?.url || '',
    };
  });
}

export function reduceStructuredEvent(inputState, event) {
  let state = inputState;
  const timestamp = eventTime(event);
  const data = event.data || {};
  const company = eventCompany(event);
  const branch = eventBranch(event);
  const executionId = eventExecution(event);
  const eventType = event.event_type;

  if (!state.run || (event.run_id && !event.parent_run_id && event.run_id !== state.run.id && eventType === 'pipeline_start')) {
    state = beginRun(state, event.run_id, timestamp, data.user_query || '');
  }

  state = appendEvent(state, event);

  if (eventType === 'pipeline_start') {
    return {
      ...state,
      run: {
        ...(state.run || {}),
        id: event.run_id,
        status: 'running',
        startedAt: timestamp,
        query: data.user_query || state.run?.query || '',
      },
    };
  }

  if (eventType === 'pipeline_end' || eventType === 'pipeline_error') {
    const integrity = eventType === 'pipeline_end' ? telemetryIntegrity(state) : state.telemetryIntegrity;
    return {
      ...state,
      telemetryIntegrity: integrity,
      run: {
        ...(state.run || {}),
        status: eventType === 'pipeline_end' ? 'done' : 'error',
        endedAt: timestamp,
        error: data.error || null,
        metrics: eventType === 'pipeline_end'
          ? { ...data, telemetry_integrity: integrity }
          : state.run?.metrics || {},
        telemetryIntegrity: integrity,
      },
    };
  }

  const isMainPhase = !company && event.component === 'graph.shortlister' && data.node_name;
  if (isMainPhase && eventType === 'node_enter') {
    return {
      ...state,
      phases: state.phases.map((phase) => phase.id === data.node_name
        ? { ...phase, status: 'running', startedAt: timestamp, endedAt: null, durationMs: null }
        : phase),
    };
  }

  if (isMainPhase && eventType === 'node_exit') {
    return {
      ...state,
      phases: state.phases.map((phase) => phase.id === data.node_name
        ? {
            ...phase,
            status: 'done',
            endedAt: timestamp,
            durationMs: data.duration_ms ?? durationBetween(phase.startedAt, timestamp),
            summary: data.output_summary || null,
          }
        : phase),
    };
  }

  if (!company) return state;

  return updateCompany(state, company, (lane) => {
    const laneEvent = state.events[state.events.length - 1];
    let next = {
      ...lane,
      eventCount: lane.eventCount + 1,
      currentBranch: branch || lane.currentBranch,
      events: [...lane.events, laneEvent].slice(-MAX_COMPANY_EVENTS),
    };

    if (eventType === 'subagent_start') {
      const isCompanyRoot = branch === 'company_research' || data.branch === 'company_research';
      const execution = {
        id: executionId,
        parentExecutionId: event.parent_execution_id || data.parent_execution_id || null,
        branch: branch || data.branch || 'sub-agent',
        status: 'running',
        startedAt: timestamp,
        endedAt: null,
        error: null,
      };
      next = {
        ...next,
        status: 'running',
        startedAt: isCompanyRoot ? (lane.startedAt || timestamp) : lane.startedAt,
        currentBranch: branch || data.branch || lane.currentBranch,
        currentExecutionId: executionId,
        rootExecutionId: isCompanyRoot ? executionId : lane.rootExecutionId,
        executions: { ...next.executions, [executionId]: execution },
        lastMessage: `Started ${branch || data.branch || 'sub-agent'}`,
      };
    }

    if (eventType === 'subagent_end') {
      const isCompanyRoot = branch === 'company_research' || data.branch === 'company_research';
      const terminalStatus = data.status || 'completed';
      const existingExecution = next.executions[executionId] || {
        id: executionId,
        parentExecutionId: event.parent_execution_id || data.parent_execution_id || null,
        branch: branch || data.branch || 'sub-agent',
        startedAt: null,
      };
      const executions = {
        ...next.executions,
        [executionId]: {
          ...existingExecution,
          status: terminalStatus,
          endedAt: timestamp,
          error: data.error || existingExecution.error || null,
        },
      };
      const completesCompany = isCompanyRoot && next.rootExecutionId === executionId;
      const runningExecutions = Object.values(executions).filter((execution) => (
        execution.status === 'running' && execution.id !== executionId
      ));
      const otherRunningExecution = runningExecutions.find((execution) => (
        execution.id !== next.rootExecutionId
      )) || runningExecutions[0];
      next = {
        ...next,
        executions,
        status: completesCompany ? (terminalStatus === 'completed' ? 'done' : 'error') : lane.status,
        rootTerminalReceived: completesCompany || lane.rootTerminalReceived,
        endedAt: completesCompany ? timestamp : lane.endedAt,
        durationMs: completesCompany ? durationBetween(lane.startedAt, timestamp) : lane.durationMs,
        currentBranch: completesCompany ? null : (otherRunningExecution?.branch || null),
        currentExecutionId: completesCompany ? null : (otherRunningExecution?.id || null),
        currentNode: completesCompany ? null : next.currentNode,
        error: data.error || next.error,
        lastMessage: `Finished ${branch || data.branch || 'sub-agent'}`,
      };
    }

    if (eventType === 'subagent_error') {
      const existingExecution = next.executions[executionId] || {};
      next = {
        ...next,
        error: data.error || 'Sub-agent failed',
        executions: {
          ...next.executions,
          [executionId]: {
            ...existingExecution,
            id: executionId,
            branch: branch || data.branch || existingExecution.branch,
            status: data.status || 'error',
            error: data.error || 'Sub-agent failed',
          },
        },
      };
    }

    if (eventType === 'node_enter') {
      const nodeName = data.node_name || data.metadata?.langgraph_node || 'unknown';
      next = {
        ...next,
        currentNode: nodeName,
        lastMessage: data.description || `Entered ${nodeName}`,
        nodes: [...next.nodes, {
          id: `${executionId}:${nodeName}:${event.event_id || event.sequence || timestamp}`,
          executionId,
          branch,
          name: nodeName,
          status: 'running',
          startedAt: timestamp,
          endedAt: null,
          durationMs: null,
        }].slice(-50),
      };
    }

    if (eventType === 'node_exit') {
      const nodeName = data.node_name || 'unknown';
      const nodes = [...next.nodes];
      const index = nodes.findLastIndex((node) => (
        node.name === nodeName
        && node.status === 'running'
        && node.executionId === executionId
      ));
      if (index >= 0) {
        nodes[index] = {
          ...nodes[index],
          status: 'done',
          endedAt: timestamp,
          durationMs: data.duration_ms ?? durationBetween(nodes[index].startedAt, timestamp),
        };
      }
      next = {
        ...next,
        nodes,
        currentNode: index >= 0 && next.currentNode === nodeName ? null : next.currentNode,
        lastMessage: `Completed ${nodeName}`,
      };
    }

    if (eventType === 'tool_start') {
      const toolId = data.callback_run_id || event.event_id || `${data.tool_name}-${timestamp}`;
      next = {
        ...next,
        toolCount: next.toolCount + 1,
        activeTools: { ...next.activeTools, [toolId]: data.tool_name || 'tool' },
        lastMessage: `Running ${data.tool_name || 'tool'}`,
      };
    }

    if (eventType === 'tool_end' || eventType === 'tool_error') {
      const toolId = data.callback_run_id;
      const activeTools = { ...next.activeTools };
      if (toolId) delete activeTools[toolId];
      next = {
        ...next,
        activeTools,
        error: eventType === 'tool_error' ? data.error || 'Tool failed' : next.error,
        lastMessage: eventType === 'tool_error' ? data.error || 'Tool failed' : 'Tool completed',
      };
    }

    if (eventType === 'llm_start') {
      next = { ...next, llmCount: next.llmCount + 1, lastMessage: 'Reasoning with LLM' };
    }

    if (eventType === 'contact_found') {
      const contactKey = data.linkedin_url || `${data.person_name || ''}:${data.role || ''}`;
      if (contactKey && !next.contacts.some((contact) => contact.key === contactKey)) {
        next = {
          ...next,
          contacts: [...next.contacts, {
            key: contactKey,
            name: data.person_name || data.name || 'LinkedIn profile',
            role: data.role || data.position || '',
            url: data.linkedin_url || '',
          }],
          lastMessage: data.person_name ? `Found ${data.person_name}` : 'Found LinkedIn profile',
        };
      }
    }

    if (eventType === 'company_contacts_snapshot' && (
      !next.rootExecutionId || next.rootExecutionId === executionId
    )) {
      const contacts = snapshotContacts(data, next.contacts);
      next = {
        ...next,
        rootExecutionId: next.rootExecutionId || executionId,
        contacts,
        snapshotCount: Number.isFinite(data.contact_count) ? data.contact_count : contacts.length,
        snapshotReceivedAt: timestamp,
        lastMessage: `Synchronized ${Number.isFinite(data.contact_count) ? data.contact_count : contacts.length} contacts`,
      };
    }

    if (eventType === 'progress' && data.message) next = { ...next, lastMessage: data.message };
    if (eventType.endsWith('_error')) next = { ...next, error: data.error || eventType };

    return next;
  });
}

export function telemetryReducer(state, action) {
  switch (action.type) {
    case 'connection':
      return { ...state, connection: action.status };
    case 'local_start':
      return beginRun(state, action.runId || 'pending', action.timestamp, action.query);
    case 'start_error':
      return {
        ...state,
        run: { ...(state.run || {}), status: 'error', error: action.error, endedAt: new Date().toISOString() },
      };
    case 'message': {
      const message = action.message;
      if (message.type === 'control' && message.control === 'run_started') {
        return beginRun(state, message.run_id, message.timestamp, state.run?.query || '');
      }
      if (message.type === 'control' && (message.control === 'run_completed' || message.control === 'run_failed')) {
        return {
          ...state,
          run: state.run ? {
            ...state.run,
            status: message.control === 'run_completed' ? 'done' : 'error',
            endedAt: message.timestamp,
            error: message.error || state.run.error,
          } : state.run,
        };
      }
      if (message.type === 'event' && message.event) return reduceStructuredEvent(state, message.event);
      return state;
    }
    case 'reset':
      return { ...createInitialTelemetryState(), connection: state.connection };
    default:
      return state;
  }
}

function websocketUrl(apiBase) {
  return `${apiBase.replace(/^http/, 'ws')}/ws/visualizer`;
}

export default function useAgentTelemetry(apiBase) {
  const [state, dispatch] = useReducer(telemetryReducer, initialState);
  const reconnectTimer = useRef(null);

  useEffect(() => {
    let disposed = false;
    let socket = null;
    let attempts = 0;

    const connect = () => {
      if (disposed) return;
      dispatch({ type: 'connection', status: attempts ? 'reconnecting' : 'connecting' });
      socket = new WebSocket(websocketUrl(apiBase));
      socket.onopen = () => {
        attempts = 0;
        dispatch({ type: 'connection', status: 'connected' });
      };
      socket.onmessage = (message) => {
        try {
          dispatch({ type: 'message', message: JSON.parse(message.data) });
        } catch {
          // Ignore malformed transport messages; JSONL parsing is handled server-side.
        }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (disposed) return;
        attempts += 1;
        dispatch({ type: 'connection', status: 'reconnecting' });
        reconnectTimer.current = setTimeout(connect, Math.min(5000, 500 * (2 ** Math.min(attempts, 4))));
      };
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (socket) socket.close();
    };
  }, [apiBase]);

  const beginLocalRun = useCallback((query, runId = 'pending') => {
    dispatch({ type: 'local_start', query, runId, timestamp: new Date().toISOString() });
  }, []);

  const markStartError = useCallback((error) => {
    dispatch({ type: 'start_error', error });
  }, []);

  const reset = useCallback(() => dispatch({ type: 'reset' }), []);

  return { state, beginLocalRun, markStartError, reset };
}
