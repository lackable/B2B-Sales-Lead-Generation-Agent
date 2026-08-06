import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createInitialTelemetryState,
  reduceStructuredEvent,
} from './useAgentTelemetry.js';


let sequence = 0;

function event(eventType, options = {}) {
  sequence += 1;
  const data = options.data || {};
  return {
    event_id: `event-${sequence}`,
    sequence,
    timestamp: `2026-08-05T00:00:${String(sequence).padStart(2, '0')}Z`,
    run_id: options.runId || 'pipeline-1',
    parent_run_id: options.parentRunId ?? null,
    agent: options.agent || 'shortlister',
    component: options.component || 'graph.shortlister',
    event_type: eventType,
    company: options.company || data.company || null,
    branch: options.branch || data.branch || null,
    execution_id: options.executionId || data.execution_id || null,
    parent_execution_id: options.parentExecutionId || data.parent_execution_id || null,
    data,
  };
}

function apply(state, structuredEvent) {
  return reduceStructuredEvent(state, structuredEvent);
}

test('interleaved executions update only their matching company and execution', () => {
  let state = createInitialTelemetryState();
  state = apply(state, event('pipeline_start', { data: { user_query: 'Find leaders' } }));
  state = apply(state, event('subagent_start', {
    company: 'Alpha', branch: 'company_research', executionId: 'alpha-root',
    data: { company: 'Alpha', branch: 'company_research', execution_id: 'alpha-root' },
  }));
  state = apply(state, event('subagent_start', {
    company: 'Beta', branch: 'company_research', executionId: 'beta-root',
    data: { company: 'Beta', branch: 'company_research', execution_id: 'beta-root' },
  }));
  state = apply(state, event('subagent_start', {
    company: 'Alpha', branch: 'linkedin_contact_finder', executionId: 'alpha-finder', parentExecutionId: 'alpha-root',
    data: { company: 'Alpha', branch: 'linkedin_contact_finder', execution_id: 'alpha-finder' },
  }));
  state = apply(state, event('subagent_start', {
    company: 'Beta', branch: 'linkedin_contact_finder', executionId: 'beta-finder', parentExecutionId: 'beta-root',
    data: { company: 'Beta', branch: 'linkedin_contact_finder', execution_id: 'beta-finder' },
  }));
  state = apply(state, event('node_enter', {
    company: 'Alpha', branch: 'linkedin_contact_finder', executionId: 'alpha-finder',
    data: { node_name: 'research_loop' },
  }));
  state = apply(state, event('node_enter', {
    company: 'Beta', branch: 'linkedin_contact_finder', executionId: 'beta-finder',
    data: { node_name: 'research_loop' },
  }));
  state = apply(state, event('node_exit', {
    company: 'Alpha', branch: 'linkedin_contact_finder', executionId: 'alpha-finder',
    data: { node_name: 'research_loop' },
  }));

  assert.equal(state.companies.Alpha.nodes.at(-1).status, 'done');
  assert.equal(state.companies.Beta.nodes.at(-1).status, 'running');
  assert.equal(state.companies.Beta.currentExecutionId, 'beta-finder');
});

test('snapshots correct incremental contacts and pipeline end reports missing telemetry', () => {
  let state = createInitialTelemetryState();
  state = apply(state, event('pipeline_start', { data: { user_query: 'Find leaders' } }));
  for (const [company, executionId] of [['Alpha', 'alpha-root'], ['Beta', 'beta-root']]) {
    state = apply(state, event('subagent_start', {
      company, branch: 'company_research', executionId,
      data: { company, branch: 'company_research', execution_id: executionId },
    }));
  }
  state = apply(state, event('contact_found', {
    company: 'Alpha', branch: 'company_research', executionId: 'alpha-root',
    data: { company: 'Alpha', person_name: 'Ada Lovelace', role: 'Old title', linkedin_url: 'https://example.test/ada' },
  }));
  state = apply(state, event('company_contacts_snapshot', {
    company: 'Alpha', branch: 'company_research', executionId: 'alpha-root',
    data: {
      company: 'Alpha', execution_id: 'alpha-root', contact_count: 2,
      contacts: [
        { name: 'Ada Lovelace', role: 'CTO' },
        { name: 'Grace Hopper', role: 'VP Engineering' },
      ],
    },
  }));
  state = apply(state, event('subagent_end', {
    company: 'Alpha', branch: 'linkedin_contact_finder', executionId: 'alpha-finder',
    data: { company: 'Alpha', branch: 'linkedin_contact_finder', execution_id: 'alpha-finder', status: 'completed' },
  }));
  assert.equal(state.companies.Alpha.status, 'running');

  state = apply(state, event('subagent_end', {
    company: 'Alpha', branch: 'company_research', executionId: 'alpha-root',
    data: { company: 'Alpha', branch: 'company_research', execution_id: 'alpha-root', status: 'completed' },
  }));
  state = apply(state, event('pipeline_end', { data: { company_count: 2 } }));

  assert.equal(state.run.status, 'done');
  assert.equal(state.companies.Alpha.status, 'done');
  assert.equal(state.companies.Beta.status, 'running');
  assert.equal(state.companies.Alpha.snapshotCount, 2);
  assert.deepEqual(
    state.companies.Alpha.contacts.map(({ name, role }) => ({ name, role })),
    [
      { name: 'Ada Lovelace', role: 'CTO' },
      { name: 'Grace Hopper', role: 'VP Engineering' },
    ],
  );
  assert.deepEqual(state.telemetryIntegrity.expectedCompanies, ['Alpha', 'Beta']);
  assert.deepEqual(state.telemetryIntegrity.completedCompanies, ['Alpha']);
  assert.deepEqual(state.telemetryIntegrity.receivedSnapshots, ['Alpha']);
  assert.deepEqual(state.telemetryIntegrity.missingTerminalEvents, ['Beta']);
  assert.deepEqual(state.telemetryIntegrity.missingSnapshots, ['Beta']);
  assert.equal(state.telemetryIntegrity.isValid, false);
  assert.deepEqual(state.run.metrics.telemetry_integrity, state.telemetryIntegrity);
});

test('pipeline end reports valid integrity when every root has a terminal and snapshot', () => {
  let state = createInitialTelemetryState();
  state = apply(state, event('pipeline_start', { data: { user_query: 'Find leaders' } }));

  for (const [company, executionId] of [['Alpha', 'alpha-root'], ['Beta', 'beta-root']]) {
    state = apply(state, event('subagent_start', {
      company, branch: 'company_research', executionId,
      data: { company, branch: 'company_research', execution_id: executionId },
    }));
    state = apply(state, event('company_contacts_snapshot', {
      company, branch: 'company_research', executionId,
      data: { company, execution_id: executionId, contact_count: 0, contacts: [] },
    }));
    state = apply(state, event('subagent_end', {
      company, branch: 'company_research', executionId,
      data: { company, branch: 'company_research', execution_id: executionId, status: 'completed' },
    }));
  }

  state = apply(state, event('pipeline_end', { data: { company_count: 2 } }));

  assert.equal(state.telemetryIntegrity.isValid, true);
  assert.deepEqual(state.telemetryIntegrity.mismatches, []);
  assert.deepEqual(state.telemetryIntegrity.completedCompanies, ['Alpha', 'Beta']);
  assert.deepEqual(state.telemetryIntegrity.receivedSnapshots, ['Alpha', 'Beta']);
  assert.ok(Object.values(state.companies).every((lane) => lane.status === 'done'));
});
