# flight-search test triage

This table records the current post-migration test ownership. Removed legacy
projection tests must not be reintroduced as public-contract compatibility
guards.

| Bucket | Test files | Migration rule |
| --- | --- | --- |
| keep | `test_tutu_mcp.py`, `test_kupibilet.py`, `test_fli_mcp.py`, `test_provider_capabilities.py`, `test_provider_segment_normalization.py`, `test_provider_port_dispatch.py`, `test_failure_classifier.py`, `test_request_deduper.py`, `test_probe_ledger.py`, `test_coverage_diagnostics.py`, `test_date_validation.py`, `test_stop_policy.py`, `test_stop_policy_bad_patterns.py`, `test_static_catalog_layers.py`, `test_cache_status.py`, `test_route_intel.py`, `test_contract_registry.py`, `test_architecture.py`, `test_pyflakes_lint_gate.py`, `test_skill_docs_contract.py`, `test_vocabulary.py`, `test_primary_cli_namespaces.py`, `test_provider_fixtures.py` | Keep as domain/provider/platform guards. Update only when contracts or public provider behavior intentionally changes. |
| rewrite | `test_search_plan_contract.py`, `test_live_route_pipeline.py`, `test_live_assembly_options.py`, `test_offer_graph.py`, `test_candidate_ranker.py`, `test_provider_aggregate_candidates.py`, `test_provider_aggregate_stop_policy.py`, `test_aggregate_control_runner.py`, `test_flow_decision_evidence_contract.py`, `test_agent_report_contract.py`, `test_user_answer_contract.py`, `test_user_answer_module.py`, `test_catalog_answer_contract.py`, `test_reporting_option_semantics.py`, `test_date_window_inventory.py`, `test_gateway_discovery.py`, `test_gateway_leg_probe_executor.py`, `test_airport_priority_policy.py`, `test_route_access_profiles.py`, `test_offer_query_runner.py`, `test_unified_route_planning.py`, `test_final_command_smoke.py` | Maintain around the compact public contract, per-probe router, constraints-first planning, wave planner, controls policy, and round-trip pairing. |
| deleted | Legacy projection/report-budget tests | Deleted with the compact report migration. Do not restore unless a new active public contract intentionally requires the behavior. |

Live provider checks must use `@pytest.mark.live_provider` and are skipped unless
pytest is run with `--run-live-providers`.
