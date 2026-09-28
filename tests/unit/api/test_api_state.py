"""Unit tests for the API process-wide runtime state singletons."""

import asyncio

from leadgen.api import state as api_state
from leadgen.api.routers import exports as exports_router
from leadgen.api.routers import linkedin as linkedin_router
from leadgen.api.routers import shortlister as shortlister_router
from leadgen.api.visualizer_broker import VisualizerBroker


def test_agent_state_initial_values():
    state = api_state.AgentState()

    assert state.status == "idle"
    assert isinstance(state.log_queues, list) and state.log_queues == []
    assert isinstance(state.log_buffer, list) and state.log_buffer == []
    assert state.last_excel is None
    assert isinstance(state.companies, list) and state.companies == []
    assert state.current_company is None
    assert isinstance(state.active_companies, list) and state.active_companies == []
    assert state.completed_count == 0
    assert state.total_count == 0
    assert state.user_query == ""
    assert state.extracted_location == ""
    assert state.error is None


def test_reset_restores_every_field():
    state = api_state.AgentState()
    state.status = "error"
    state.log_queues.append(asyncio.Queue())
    state.log_buffer.append("buffered line")
    state.last_excel = "C:/tmp/report.xlsx"
    state.companies.append({"company_name": "Acme"})
    state.current_company = "Acme"
    state.active_companies.append("Acme")
    state.completed_count = 3
    state.total_count = 9
    state.user_query = "indian it companies"
    state.extracted_location = "India"
    state.error = "boom"

    state.reset()

    assert state.status == "idle"
    assert state.log_queues == []
    assert state.log_buffer == []
    assert state.last_excel is None
    assert state.companies == []
    assert state.current_company is None
    assert state.active_companies == []
    assert state.completed_count == 0
    assert state.total_count == 0
    assert state.user_query == ""
    assert state.extracted_location == ""
    assert state.error is None


def test_reset_keeps_the_same_container_objects():
    state = api_state.AgentState()
    queues = state.log_queues
    buffers = state.log_buffer
    companies = state.companies
    active = state.active_companies

    state.reset()

    # ``reset`` clears in place rather than rebinding, so existing references stay valid.
    assert state.log_queues is queues
    assert state.log_buffer is buffers
    assert state.companies is companies
    assert state.active_companies is active


def test_agent_singletons_are_distinct_instances(api_state_reset):
    assert isinstance(api_state.shortlister_state, api_state.AgentState)
    assert isinstance(api_state.linkedin_state, api_state.AgentState)
    assert api_state.shortlister_state is not api_state.linkedin_state
    assert api_state.shortlister_state.status == "idle"
    assert api_state.linkedin_state.status == "idle"


def test_routers_share_the_module_level_singletons():
    assert shortlister_router.shortlister_state is api_state.shortlister_state
    assert linkedin_router.linkedin_state is api_state.linkedin_state
    assert exports_router.shortlister_state is api_state.shortlister_state
    assert exports_router.linkedin_state is api_state.linkedin_state


def test_email_store_is_a_mutable_dict(api_state_reset):
    assert isinstance(api_state._email_store, dict)
    assert api_state._email_store == {}

    api_state._email_store[("acme corp", "jane doe")] = "jane@acme.com"

    assert api_state._email_store == {("acme corp", "jane doe"): "jane@acme.com"}


def test_ws_log_clients_starts_as_an_empty_list(api_state_reset):
    assert isinstance(api_state.ws_log_clients, list)
    assert api_state.ws_log_clients == []

    client = object()
    api_state.ws_log_clients.append(client)

    assert api_state.ws_log_clients == [client]


def test_visualizer_broker_is_a_broker_instance():
    broker = api_state.visualizer_broker

    assert isinstance(broker, VisualizerBroker)
    assert isinstance(broker.clients, set)
    assert isinstance(broker.process_outcome, dict)
    assert callable(broker.subscribe)
    assert callable(broker.unsubscribe)
    assert callable(broker.publish)
    assert callable(broker.begin_run)
    assert callable(broker.mark_process_done)
    # ``api_state`` holds the very same singleton the shortlister router uses.
    assert shortlister_router.visualizer_broker is broker


def test_fresh_visualizer_broker_defaults():
    broker = VisualizerBroker()

    assert broker.clients == set()
    assert broker.active_run_id is None
    assert broker.active_log_path is None
    assert broker.tail_task is None
    assert broker.process_done is None
    assert broker.process_outcome == {}
