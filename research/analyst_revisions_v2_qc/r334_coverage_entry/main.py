from AlgorithmImports import *
import newrule_available_history_native_coverage as coverage
EXPECTED_PROFILE = {'History_called': False, 'ObjectStore_written': False, 'actual_target_or_holdings_path_proven': False, 'binding_stream_sha256': '73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f', 'complete_strategy_price_coverage_proven': False, 'deadline_limitation': 'cooperative_checks_cannot_interrupt_engine_or_native_IO', 'dense_coverage': 'conservative_potential_envelope_not_actual_holdings_or_unconditional_launch_gate', 'dense_period': 'first_potential_prior_through_evaluation_last_all_sessions_no_expiry_shortening', 'evaluation_first': '2021-11-01', 'evaluation_last': '2026-10-13', 'expected_demand': [{'eligible_decision_count': 90, 'eligible_decisions_sha256': '86ed3decb2ab7c5d6a99aae89f494d86a2585c438a3efe3e11aebf079f809b25', 'first_prior': '2025-01-24', 'required_session_count': 432, 'required_sessions_sha256': 'b656433185ecbd14a9b49de24cda0200eb43769c76d373d353658eb4da56836b', 'whole_binding_sha256': '1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331'}, {'eligible_decision_count': 87, 'eligible_decisions_sha256': 'daf514d8c49c0b504f2740711b601dd02040350f27c2bbc85f82503711e7352e', 'first_prior': '2025-02-14', 'required_session_count': 417, 'required_sessions_sha256': '4560ecf123f4c4b41059b0769d202e15bf6d1e83934770a0d5f95c6534f60ac1', 'whole_binding_sha256': 'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8'}, {'eligible_decision_count': 63, 'eligible_decisions_sha256': 'f66d561b40b70a7272ae27b63ffb088a9b0d18225b2a6c9d40421f2a305378b2', 'first_prior': '2025-08-01', 'required_session_count': 302, 'required_sessions_sha256': '39482e443afe824c08620c57bd48997d7e374b2075718ffd8318aa394021c5b1', 'whole_binding_sha256': 'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9'}, {'eligible_decision_count': 87, 'eligible_decisions_sha256': 'daf514d8c49c0b504f2740711b601dd02040350f27c2bbc85f82503711e7352e', 'first_prior': '2025-02-14', 'required_session_count': 417, 'required_sessions_sha256': '4560ecf123f4c4b41059b0769d202e15bf6d1e83934770a0d5f95c6534f60ac1', 'whole_binding_sha256': 'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7'}, {'eligible_decision_count': 150, 'eligible_decisions_sha256': '920a5400e5076b12ed99b7486f9921edbf2f159beabafbbc3bcb0910d8a35008', 'first_prior': '2023-12-01', 'required_session_count': 718, 'required_sessions_sha256': '2bddfbb2bd6f6523cb8f84030e6eebf671da4ce7c38a02dabc4bab580b770199', 'whole_binding_sha256': 'f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986'}], 'first_reference_close': '2021-10-29', 'formal_forward_ready': False, 'full_axis_sha256': '4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585', 'gap_classification': 'missing_before_between_after_observed_valid_cells_or_no_valid_no_cause_inference', 'historical_identity_proven': False, 'initial_state_requirement': 'future_W5_empty_holdings_open_orders_before_first_decision', 'maximum_seconds': 600, 'maximum_statistic_bytes': 8002, 'membership_end_retires_holdings': False, 'membership_stream_sha256': '6da39a900784aea5f0be81a9a329b28a1399d8dc5d95ec60b3951f55e31f40cd', 'observation_clock': '2026Oct14_New_York_all_requested_closes_in_past', 'orders_submitted': False, 'paper_or_live_ready': False, 'per_date_or_other_source_fallback': False, 'period_sha256': '88113155d49f74e00a89ba743aaa314d718cfd0d29b017ac501058460fe5d11a', 'permanent_security_master_proven': False, 'point_in_time_proven': False, 'potential_references': 'prior_close_for_every_membership_eligible_decision_not_actual_selected_target', 'price_input_admitted': False, 'processing_rights_granted': False, 'raw_prices_exported': False, 'research_epoch_id': 'R327-20261027-available-history-v1', 'rights_and_access': 'external_current_paid_private_owner_scope_before_invocation', 'runtime_project_id': 38522505, 'schema': 'arv2-r329-W5-native-dated-coverage-v1', 'source_assignment_changed': False, 'source_book_byte_count': 1313871, 'source_book_sha256': 'b149c9c659ef53084782e25ee18ffc4133bebb063180958651cafc69725c7299', 'source_context_sha256': 'dca0fb0cc15093a1fd892dfbfc2f4d1216a330bcf4bf355625cc07e774e3e07b', 'source_reads': 'fresh_genuine_package_then_concrete_reader_fresh_package_and_one_exact_QC_book_read', 'strategy_result_accepted': False, 'terminal_payoff_proven': False, 'vendor_coverage_proven': False}

class AvailableHistoryNativeCoverageAlgorithm(QCAlgorithm):

    def initialize(self):
        if getattr(self, '_coverage_init_claimed', False):
            raise RuntimeError('native_coverage_duplicate_initialize')
        self._coverage_init_claimed = True
        self._coverage_done = False
        self._coverage_emit_attempted = False
        self._coverage = None
        try:
            coverage.require(type(self.project_id) is int and self.project_id == 38522505, 'project')
            coverage.require(self.live_mode is False, 'orders')
            self.set_time_zone('America/New_York')
            self.set_account_currency('USD')
            self.settings.daily_precise_end_time = True
            self.settings.seed_initial_prices = False
            self.set_start_date(2026, 10, 14)
            self.set_end_date(2026, 10, 14)
            self.set_cash(1000000)
            etfs = {ticker: self.add_equity(ticker, Resolution.DAILY, fill_forward=False, leverage=1, extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW).symbol for ticker in coverage.period.OWN_FUNDS}
            self.set_benchmark(etfs['SPY'])
            self._coverage = coverage.AvailableHistoryNativeCoverage(self, runtime_project_id=38522505, benchmark_symbol=etfs['SPY'], etf_symbols=etfs, trade_bar_type=TradeBar, daily_resolution=Resolution.DAILY, raw_normalization=DataNormalizationMode.RAW)
            observed = self._coverage.observe_once()
            observed = coverage.validate_summary(observed, expected_profile=EXPECTED_PROFILE)
            raw = coverage.canonical(observed)
            coverage.require(type(raw) is bytes and 0 < len(raw) <= 8002, 'summary')
            self._coverage_emit_attempted = True
            self.set_summary_statistic(coverage.STATISTIC, raw.decode('ascii'))
            coverage.require(observed['terminal'] == 'complete', 'summary')
            self._coverage.assert_no_orders()
            self._coverage_done = True
        except Exception as error:
            raise RuntimeError('native_coverage_refused/' + coverage.finite(error)) from None

    def on_data(self, data):
        if self._coverage is not None:
            self._coverage.assert_no_orders()

    def on_end_of_algorithm(self):
        if not self._coverage_done or not self._coverage_emit_attempted or self._coverage is None:
            raise RuntimeError('native_coverage_not_finished')
        self._coverage.assert_no_orders()
