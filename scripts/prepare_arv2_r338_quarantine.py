"""One new offline full-input, conservative coverage and six-source preparation.

All original DATA remain unchanged. Conservative price gaps are retained;
no QC target/holdings/quote, launch or formal source admission is inferred.
"""
import argparse
import csv
from contextlib import ExitStack
from datetime import date
from decimal import Decimal,InvalidOperation
import hashlib
import importlib
from importlib.machinery import PathFinder
import io
import json
import math
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE=ROOT/'scripts/prepare_arv2_r338_quarantine.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/quarantine/R338-20261104-A'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r338-offline-quarantine-input-coverage-binding-v1'
INPUT_PACKAGE=ROOT/'artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-D5/package/arv2-preliminary-qc-package-411c2734da61c7d4172c4cb3d'
INPUT_LINEAGE=INPUT_PACKAGE.parent/'arv2-october-lineage-e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9/lineage.json'
DATA_PLAN={'quarantine': {'relative_path': 'artifacts/analyst_revisions_v2/quarantine/R337-20261103-A/quarantine-catalog-private.json', 'byte_count': 6924, 'sha256': 'bebe830cba48c6eafb0c99c8feb4251c59871bb7a52f054327076d946d81bc94'}, 'archive': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_available_history_archive/R327-20261028-K/vendor-payload-private.bin', 'byte_count': 148543046, 'sha256': '2a2815b543c41728b441b0b300a9d269f282778ef1915923fd68f61993f9ca1f'}}
SOURCE_PINS={'data/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'data/exchange_calendar.py': '174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89', 'data/financial_primitives.py': 'e5fe36fb858b07945a166fba5271a83512523cadec286f42d104a0351e8d931e', 'research/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'research/analyst_revisions_v2/__init__.py': 'e94066c7eed2f34d7342a7a8c3cf15acfac359e47216a058b24b31cf83592ce2', 'research/analyst_revisions_v2/accepted_risk_input_pair.py': '4aa82377661420e4ee017b3cdefd54f038af75eca2b3cf086f57d11a6c55a037', 'research/analyst_revisions_v2/artifact_io.py': '813dc69c4eafe9907b1201ee3d781ae7522aab6065cb6e39f5bbf08a773158fb', 'research/analyst_revisions_v2/availability.py': '238738109bb7e2e3408376b143dfafc8fe5dc174b30a6a642276fda669d26ce4', 'research/analyst_revisions_v2/canonical.py': 'c1d1d1aab633b16868fccc371de7c4cf4f3a692943e04a8d785109110e17ae6e', 'research/analyst_revisions_v2/contracts.py': 'baac4b85f1eacc3442a06d704c48631cd5e7a5b28f99a05b551c29672c992417', 'research/analyst_revisions_v2/dataset.py': '67233650d34520198005eb7808093e2e27f8c445d645a34c3ac038235ef431a8', 'research/analyst_revisions_v2/evidence.py': '810f0af1a9fe0bb0f2af30d8bb59c1f3bb0463e4352d9fdf8c62afa57ffe1840', 'research/analyst_revisions_v2/firm_ontology.py': '83977d2b0ca34712f516d17776857979b7bc0112e171dfc8e8b5b92d39224ae9', 'research/analyst_revisions_v2/fold_manifest.py': 'bf8fdc6e8cd81b1d79732504c07c165b1b1745ac797fb7d8cda660e3b406aaad', 'research/analyst_revisions_v2/formulas.py': 'd9cc74c2961c204280ce599e0362995d5f7649939eca7196bb466c2ed6bce45a', 'research/analyst_revisions_v2/four_family_multiplicity.py': '7d4961a6ac4a4546a434dd5472a7e5b72a212b3d9a1ce3eac8e212a7862605b9', 'research/analyst_revisions_v2/global_benchmark_contract.py': 'ebb91b61eea62e53466bc20f2b3b3272a48bc2487e3b1e75a9f9337b69e2068b', 'research/analyst_revisions_v2/normalization.py': 'e62a15d750e150f44c0f3916dcd948072bc2f24ae71ca8b2774e99594f618e3d', 'research/analyst_revisions_v2/power_calibration_input_manifest.py': '0e4ae00bb21f054f3f40aba47a71c3014d8194d665fc31bfd21057d96181a910', 'research/analyst_revisions_v2/power_calibration_input_schema.py': '6c461aaba8898f7550101707ea2f1680a91565affa8c9ef33e5d1e66a2a805cd', 'research/analyst_revisions_v2/power_calibration_protocol.py': '3fe7ed9abb9692f2dcd122db0014af3dec83785fa8662cbe074c8a53b0a49442', 'research/analyst_revisions_v2/power_calibration_receipt.py': '90a52ef80efcdde80bae8b305916a8834223b6821de462e6b8731e4edb2cea14', 'research/analyst_revisions_v2/preopen_control_acquisition.py': '8b4702b8ca431fa9a3c8ba518f650e0f35e866324ab1b90ff71952a6ea47c616', 'research/analyst_revisions_v2/preregistration.py': 'ab6c84521688faa7ce3a9528c80b7df5dd9c9fdb848c37aa4bc3179b7eb90988', 'research/analyst_revisions_v2/production_evidence_acquisition.py': '53d726dff2f441aa0fe6a76cb0f46950ca81e4867707736ba54bb07be4b6578d', 'research/analyst_revisions_v2/production_input_pipeline.py': '2054933a8c36854b385ebf2ecc388f63714b522d81d90b3006ad20ea2dfa88e8', 'research/analyst_revisions_v2/production_registry.py': '6c91299eea2f631d69a9eefbd083654e918644d99bd2da8ad3f3ca4ba598aed6', 'research/analyst_revisions_v2/production_scoring.py': '511da9fda0d6c4aee825542bc9d4d444cbdd56d3564bafc40370209a5da0e27c', 'research/analyst_revisions_v2/production_truth_gate.py': '139c7e36a24e22158826435d579d78e03ab62106a167732c2274777847c65214', 'research/analyst_revisions_v2/provider_history.py': '69a93210a5f5c2b20e88022a05e16db644310ec6b64325b633efe05dafdc3e85', 'research/analyst_revisions_v2/qc_first_plan.py': '5b10d898e3dec6a07c96e0048e3ad73e5c9d907812a52ac9d5b5c651b904de14', 'research/analyst_revisions_v2/ratings_ingest.py': '3e53d8606710ed3bf27d8e834221d0be7a7d4904469615ba5eac0c3279461dd1', 'research/analyst_revisions_v2/security_master.py': 'b1b435fe5eab32eddaf138e504e8a028ea667eab8bbb1b9f08f407a33a8fc69b', 'research/analyst_revisions_v2/snapshot.py': '1537e7a87a2ffdf15318e39c1cfbf6b33f1b4e49311c82cf5382c2e362b2a0c2', 'research/analyst_revisions_v2/stock_controls.py': 'edd841a50bc32720b1e024118c1e7f593f83fc102cf884cb075136e45121428f', 'research/analyst_revisions_v2/stock_evaluation_contract.py': '3229df011a567fb524cecd5130acdfa56d3bc9ee4766318718052beaa8bfbf60', 'research/analyst_revisions_v2/stock_signal.py': 'c6800ec987dc8ca1f2205b1150f05e61daa56e8712ed6d12962dd57ee6093a76', 'research/analyst_revisions_v2_qc/__init__.py': 'ce8f07aeab0358f5eb3241190169d4f967a5423dc88719f0783a83d010d43dcc', 'research/analyst_revisions_v2_qc/accepted_risk_delta_order_package.py': 'f0465c6bc52722a51cfa8a97700f99e2f87476a195ed88e071aa4a265eacd365', 'research/analyst_revisions_v2_qc/accepted_risk_latest_order_package.py': '817206750b0ab308a0aecbc1fe6f564cd969eaf8248a5ed9102db8660d464948', 'research/analyst_revisions_v2_qc/accepted_risk_massive_delta.py': 'f8c8f42bb4a2619ede45d5d34648b656732324cbd8de68b957a99cd4599c522f', 'research/analyst_revisions_v2_qc/accepted_risk_massive_ratings_delta.py': '9c0ec2eede6daeabc03d150c1146d595026fe724028ead856edce9f29b872390', 'research/analyst_revisions_v2_qc/accepted_risk_massive_ratings_delta_v2.py': 'ba736022c91e759e6fce899e8e8b85286bfa9113ce3a063c5ec12fff7b2d5138', 'research/analyst_revisions_v2_qc/accepted_risk_october_order_package.py': '655eec765a8b99d489881f7de7ddc339ab6b2c0bb0470feb814c6ef005d03c0a', 'research/analyst_revisions_v2_qc/accepted_risk_order_level_core.py': '063ed8fb7024c879a640780c07723c7edfb95665acc711d02fc8be0d964e965f', 'research/analyst_revisions_v2_qc/accepted_risk_order_level_forced_exit.py': '21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f', 'research/analyst_revisions_v2_qc/accepted_risk_order_level_input_runtime.py': 'a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee', 'research/analyst_revisions_v2_qc/accepted_risk_pair_bridge.py': '86b48ce8c4dd650ca5a62b7b5aeb00ace882b92e29a7129a3ffc1d46e19561ad', 'research/analyst_revisions_v2_qc/accepted_risk_preliminary_package.py': '794bdcb8ed3be34b625030ac8a0cd0d65aeaf7dd14e58d081d40f495528e0824', 'research/analyst_revisions_v2_qc/accepted_risk_preliminary_qc_figi.py': '4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9', 'research/analyst_revisions_v2_qc/accepted_risk_preliminary_rating_evaluator.py': '2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910', 'research/analyst_revisions_v2_qc/accepted_risk_preliminary_rating_policy.py': '7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd', 'research/analyst_revisions_v2_qc/accepted_risk_preopen_rating_score.py': '67f86ffc696c036c7fbfef64ee00fb1ad1a8599727f5ef36762e329df85a023a', 'research/analyst_revisions_v2_qc/accepted_risk_security_master_admission.py': 'eed43aac8d2cd1ea4862e4695d1f6824e287736f26257699f83bafa88beb9c2d', 'research/analyst_revisions_v2_qc/accepted_risk_sequential_r055_score.py': '6c34940cb821c04554e9073a77e013d306d059a688dbac02fe5b0511d91d217b', 'research/analyst_revisions_v2_qc/accepted_risk_simulated_moo_executor.py': 'e2f4b5508427e6f4c5bf20813e255cecae1d8652177391eeb226dc56084c5fb7', 'research/analyst_revisions_v2_qc/accepted_risk_six_universe_gate.py': '158445ae072ef6c66a49b2069c53b02ee805adbccbb9a522650ccd3a72fa9f1e', 'research/analyst_revisions_v2_qc/accepted_risk_six_universe_gate_evaluator.py': 'd0f1ba677c63f2caf3703cd7a4df5fbc8ef6225aac4a2357c7d54003da73eb1c', 'research/analyst_revisions_v2_qc/accepted_risk_six_universe_order_qc_projection.py': '5037fdc1153c9ac927a540201fa92cb45db463e8313e0c88e04ddc9f0eb301f6', 'research/analyst_revisions_v2_qc/accepted_risk_six_universe_order_qc_runtime.py': '84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a', 'research/analyst_revisions_v2_qc/accepted_risk_six_universe_order_targets.py': '0b280fdc1ebcb5f8ab073ff78f3008057e86db14b6254145bc5f86e18d2e5ea0', 'research/analyst_revisions_v2_qc/accepted_risk_terminal_disposition.py': '7bbd6996b7f7d35e663773a16bdc6f112d5448abd752924c8726bb89ccde0985', 'research/analyst_revisions_v2_qc/event_study.py': '0f1e6f69c4bde56bb42a49d24d42b0a27cb2417d3c7bf8f1ea196e15fa0628fe', 'research/analyst_revisions_v2_qc/firm_ontology_owner_decision.py': '9115f777ac9ebe654edbfe816ce3a7927b4dcc8c11aefcc5376c53a690e4e345', 'research/analyst_revisions_v2_qc/firm_ontology_proposal_generator.py': 'd12e77db30cf1dd30d657a5716e1433ba215a41e1873bcd48a3dbb8cba1a2a03', 'research/analyst_revisions_v2_qc/formal_cloud_evaluator.py': '7af87aaeec47d4677f0f351d2ad3113725e8783d0cba91ea2fbbb935028c5f15', 'research/analyst_revisions_v2_qc/formal_economic_execution_definition.py': 'b1cb6d1b603c6994a84646d34f179715bbec5c527b2d554793adeddc6ede5902', 'research/analyst_revisions_v2_qc/formal_evaluation.py': '90b8f61fe39143d6d0fbd4e603c2652f54ba049d3c1b1c1e205174238d9da1fc', 'research/analyst_revisions_v2_qc/formal_input_bundle.py': '45e28e392b126fa55dc1ea06ff49d36a4907dc603ddee193a9e1d478e6149472', 'research/analyst_revisions_v2_qc/formal_input_composer.py': '0975ee1b504056390d926b307b9742e1eeb51385238704e3b0b5af643b1bf4a0', 'research/analyst_revisions_v2_qc/formal_qc_transport.py': 'b8c332eda827aeaee23f0dbbddcc96dbd269c82c996812a8a31fe2a4fec62ac4', 'research/analyst_revisions_v2_qc/formal_report_contract.py': '2bf962789679434cad76a1d0dc837b82b4327882796acc0615c588b89bd228ea', 'research/analyst_revisions_v2_qc/formal_run_protocol.py': 'f2c974d67d9317bea4e1b4d6b942a6116fe8619f80c7611ca4353228d17d6d97', 'research/analyst_revisions_v2_qc/formal_runtime_projection.py': '5c2dedc02a13ef84b6cb04079ce854162f509f5ef12bbc15448de7cf8dcd4675', 'research/analyst_revisions_v2_qc/formal_streaming_bridge.py': '8cc672907425242c5291cc1d4a87365c08601b5f935e952d0352b6394f0a1913', 'research/analyst_revisions_v2_qc/formal_streaming_input.py': '8bfc126b8e74c4ac0bca1f8e3e44bbdb571e7d46f90fa9d11fa7365548faef33', 'research/analyst_revisions_v2_qc/formal_submission_adapter.py': '0c743225966aa1d3f27af14af7662563ff328c3c683c7659620b0f67f786c734', 'research/analyst_revisions_v2_qc/formal_terminal_disposition_builder.py': '471b7ce0cdf959097250a5a0828f155b579c1c2bba30ec8ae1a43452a105081b', 'research/analyst_revisions_v2_qc/fundamental_universe_discovery.py': '05e67a307b0d7514c72b129e909c47cc3ebe3fdcd03e26de6ca3a1bc104a7a3b', 'research/analyst_revisions_v2_qc/global_input_bundle.py': 'cdf24e6bdf3bf63e4635d7524e213f9db25abe308c3973999c1215fb5a4cec18', 'research/analyst_revisions_v2_qc/global_input_schema.py': 'f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a', 'research/analyst_revisions_v2_qc/lean_source_assembly.py': '62f88c33b9041c8e5d9ff1ae018b80787c38df29dce87186b9e980284b9edd52', 'research/analyst_revisions_v2_qc/newrule_available_history_comparison_runtime.py': '7b32ec439553089fbd9b3ffd5fabb708bc823fffca479c8f941dbfe185b33150', 'research/analyst_revisions_v2_qc/newrule_common_price_format.py': 'd254b3e3a6a52445e4422f03885ec58a3d2b30e8ce902cb80ed8f841c374f873', 'research/analyst_revisions_v2_qc/newrule_comparison_projection.py': '4f51d1a9a50293f4fa39be297666c1e6144462abaa82e69e342845580a1a4076', 'research/analyst_revisions_v2_qc/newrule_comparison_qc_runtime.py': '674415b3179836a613afc6f7bdea23a966db21ab67221472fc5d87b4a742049d', 'research/analyst_revisions_v2_qc/newrule_comparison_targets.py': '30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d', 'research/analyst_revisions_v2_qc/newrule_five_case_quarantine_common_price.py': '7006b05843e4c7fbdfec0b9f8ea5f716c0d631dcde4cdf04a13a520b9a67645b', 'research/analyst_revisions_v2_qc/newrule_five_case_quarantine_contract.py': 'f047a1f0eff4fc7424da04246b0a89edc47bb8358ea93cd979ca10c935cbe8ad', 'research/analyst_revisions_v2_qc/newrule_five_case_quarantine_policy.py': '77280e4963c38e9197da81f3b02b920d91d5e727380b1323bfa9e54a715a8ac0', 'research/analyst_revisions_v2_qc/newrule_five_case_quarantine_runtime.py': '2cbb69c89b9735331219ec9f573110ec9f27338f6d706c08a836404f43ccc958', 'research/analyst_revisions_v2_qc/newrule_five_case_quarantine_targets.py': 'd98777e7398f3f1779a5a0bd4ec68b83db24542730aeb24a4cea70b6f95ff6b4', 'research/analyst_revisions_v2_qc/newrule_five_case_quarantine_vendor_book.py': '8f1baa74cb5fa3b27a26748f94b6bf422fbb13f13f5524d598b92a82def80504', 'research/analyst_revisions_v2_qc/newrule_native_price_book_publication.py': '03d100e962b98cd8b174d947a33636e421692445422c0dcce2282b46015435e2', 'research/analyst_revisions_v2_qc/newrule_native_price_source_diagnostic.py': '57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697', 'research/analyst_revisions_v2_qc/newrule_plain_input_runtime.py': 'bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f', 'research/analyst_revisions_v2_qc/newrule_plain_transport.py': '4cf351095015fddb7a463692f6d789917d229966772e04a60de0c804ed965f5a', 'research/analyst_revisions_v2_qc/object_store_read_contract.py': 'bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3', 'research/analyst_revisions_v2_qc/owner_signature_authority.py': '0b456f6aef4f70a26591c1bc5218725895f7874a5da8608a69f8d840862da6fb', 'research/analyst_revisions_v2_qc/physical_accepted_risk_archive.py': 'f8da20bb28296a942cb1d9219b2fb3056a33af774cf55276c1788aa8983d3b4b', 'research/analyst_revisions_v2_qc/physical_firm_ontology_review_packet.py': 'dfed48da54c605f7ca8a5295edbb419b94328bde43e95339eef1636f063d64e8', 'research/analyst_revisions_v2_qc/physical_preopen_seed_archive.py': '873d92b365d520ad1d4da1b371469ec9cb7e5162cd4eaeed8cd048845f783421', 'research/analyst_revisions_v2_qc/physical_production_evidence_acquisition.py': 'd126666a3dd5f4e6a99d2bec51698a2a742347063b04ab8e23d5cee4454a437c', 'research/analyst_revisions_v2_qc/physical_production_evidence_bridge.py': '6d0d6dc47a513ad81fd274749218cc44597240e0aa7bb7793c3086e649ea5294', 'research/analyst_revisions_v2_qc/physical_production_input_archive.py': '05eb7e7ca52bec9eec5900e739b54a0ebf217d2c508c0a6c36ac7afb01de6622', 'research/analyst_revisions_v2_qc/power_calibration_bridge.py': '4f67a917e1e922274afabf0c5f427313a80b41ce3c5b33b52a7065748abc3226', 'research/analyst_revisions_v2_qc/preopen_control_acquisition_io.py': '8b1582ee2e8f64106fa62182d7f6c672d84e11258c9bfb98c9bb0ed3108acaf6', 'research/analyst_revisions_v2_qc/preopen_control_prereview_downloader.py': '19d4851200256c03aec7aa73656c9bb14554293b5d50e3caca8fff100c760e8c', 'research/analyst_revisions_v2_qc/preopen_control_stage.py': '7e0bf082d5d3842ac161b86f475c7e0b04d06ea4817c18ac1f4ab5f2ea9762b8', 'research/analyst_revisions_v2_qc/preopen_control_submission_adapter.py': '9366d2c5ddede4df0722c0c45ccd7180c80fd0cb37d8deff88fece3e30c9dce3', 'research/analyst_revisions_v2_qc/preopen_quality_worker.py': '90923d1554c15d3a01669be3e374597b5c3536616fbaa95b07fa69d105092320', 'research/analyst_revisions_v2_qc/production_evidence_composer.py': '17fa2c3c994a781f0df2fe945f0cd0af2cbfe718d72a9b9d10d2a5d4085e6cb5', 'research/analyst_revisions_v2_qc/run_contract.py': 'a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5', 'research/analyst_revisions_v2_qc/runtime_shard_projection.py': 'fb5abac77b28d1fabe53d3ff9e9448ef54d81bbb829607984fef9960f0d788ac', 'research/analyst_revisions_v2_qc/synthetic_input_transport.py': 'c473bf91a99fd5207ab10407ea85971db9e24e75f7d29ccf64b38c628538ebe9', 'research/quantconnect.py': '7a12fdb68194ee10f6e8c3d7c0fc49c08b34166d056bd5ea2a72937dd03be373', 'scripts/arv2_r298_ar_source_binding.py': '52ae31ddb440e1ecaf693d54fb6cf6d48ee377813d8614e7ce3cee5a02d68d76', 'scripts/arv2_r327_k_source_binding.py': '1814d6a71ee20a6cda6ec14a6af6cf938a7c95c8b02cfee38730f3caac9176b9', 'scripts/arv2_r337_quarantine_preparation.py': 'e41136a3927564f3b5691f7d2a9272b8bc71ff810c19582c8ecbe35074a5fd6e', 'scripts/arv2_r337_quarantine_projection.py': 'a61c467b8b9935ed5129836733b2708010b6280f6693140cb8399fb5cc6a7082', 'scripts/arv2_r338_quarantine_coverage.py': '9901e912c19d7348822c7d19d554213034ab23798dddd26d9abdadad9d588208', 'scripts/arv2_r338_quarantine_data_guard.py': '98f10fe2a65331980a1f23cd284fa9d695643a3502f5c5f236a44edfdb52f691', 'scripts/arv2_r338_quarantine_input.py': 'a7e56ca57bd54b4743c18f04f5287119b91c82a9bf7165692ad2cb457b8d7ce8', 'scripts/arv2_r338_quarantine_materialization.py': 'b9c5c84bee710f2e4c1b2ce062d8ec56d7293193c7b00fcc8113d3d94ca2016f', 'scripts/arv2_relocation_security.py': '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30', 'scripts/build_arv2_historical_preopen_bridge.py': 'a4f283800538efcfbbac5b1aee17b946694a456ae6d8da32e010239457c6c5b6', 'scripts/build_arv2_massive_input_pair.py': '58e671d4823f26b126f7eed971df0d2c7f07bd3fa12f60967454a63b679e05bd', 'scripts/build_arv2_preopen_input.py': '1916d67c80a4e48b3779adbd7286c201b4003cb713c23a8434a491ef3380c41b', 'scripts/capture_arv2_massive.py': 'e67cabf821a3df804d157c790b6df1c7cd1a13a7c50d717a48b55b3d32e5e906', 'scripts/capture_arv2_sharadar.py': '17e516b4cc721c7f97c4690f54dfcc9d2d11d8cebd413100f2e2ffa68e663ca2'}
SECONDS,MAX_OUTPUT,MAX_PRIVATE=900,131072,64*1024*1024
MIN_FREE_BYTES=256*1024*1024
WORKER_SECONDS=840
COMPONENT_PROFILE_PINS={'guard': {'byte_count': 1566, 'sha256': 'bc257b3773032e016152abdb6ae4090b7f88808a25d4ebd8954c6e49f8c5338e'}, 'input': {'byte_count': 3564, 'sha256': 'e45b26f969a5c03904bf23a56e9ff2f22d28a0bce0c3559ac81f1283e994b80e'}, 'coverage': {'byte_count': 3221, 'sha256': '5f1fa2505d4acf4fe99679f3f05c4743161dbec6612311aa35d00ec58202662d'}, 'materialization': {'byte_count': 10045, 'sha256': 'c85d706477df422c9d8713af8f3fa84ef4edfbfe151eb9aa0859c18d02f62833'}}
CHILD_OBSERVATION=None
DEADLINE_FIRED=False
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
FAILURE_STAGE,FAILURE_CASE='preflight',None
STAGES=frozenset(('preflight','retained_DATA','coverage','materialization','output'))
MODULES={}
MODULE_CODES={name:frozenset(values) for name,values in {'guard': ('byte_pin', 'close', 'deadline', 'metadata', 'named_changed', 'path_open', 'plan', 'read_spent', 'receipt', 'scope', 'security', 'security_changed', 'shape', 'state'), 'input': ('axis', 'bindings', 'byte_pin', 'changed', 'close', 'contributions', 'deadline', 'descriptor', 'genuine', 'inventory', 'json', 'manifest', 'memberships', 'metadata', 'named_changed', 'output', 'path_open', 'plain', 'scope', 'security', 'security_changed', 'shape', 'state', 'stream', 'unknown'), 'coverage': ('archive', 'assignment', 'axis', 'catalog', 'conditional_demand', 'deadline', 'grid', 'input_binding', 'input_pin', 'input_shape', 'manifest', 'memberships', 'missing_bound', 'output', 'period', 'private_bound', 'quarantine', 'transport_nonce', 'unknown'), 'materialization': ('archive', 'archive_pin', 'assignment', 'axis', 'bindings', 'bound', 'bundle', 'catalog', 'catalog_pin', 'context', 'deadline', 'header_pin', 'input_binding', 'json', 'output', 'projection', 'range_pin', 'sources', 'transport_nonce', 'unknown')}.items()}

FALSE_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'security_identifiers_disclosed': False, 'licensed_rows_disclosed': False, 'original_data_rewritten': False, 'actual_QC_target_or_holdings_path_proven': False, 'current_cloud_project_verified': False, 'current_cloud_sources_or_objects_verified': False, 'QC_processing_rights_granted': False, 'source_admission_granted': False, 'formal_identity_admitted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'strategy_action_invoked': False, 'strategy_result_accepted': False}
FINITE=frozenset(('arguments','bound','changed','child_failure','child_stderr','claim_spent','control','deadline','descriptor_budget','disk_budget','environment','git_state','host','input','output','path','scope','shape','source_changed','source_pin','unknown'))|frozenset(name+'_'+code for name,codes in MODULE_CODES.items() for code in codes if code!='deadline')


class Refused(ValueError):
    """Closed local predicate; never retain private source text in errors."""

class RunDeadline(BaseException):
    """Timer control flow outside ordinary JSON, data and transport errors."""

def deadline_expired(*_):
    global DEADLINE_FIRED
    DEADLINE_FIRED=True
    raise RunDeadline()

def require(value, code):
    if not value:
        raise Refused(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}

def finite(error):
    if DEADLINE_FIRED or isinstance(error,(RunDeadline,TimeoutError,subprocess.TimeoutExpired)):
        return 'deadline'
    for name,module in MODULES.items():
        if module is not None and hasattr(module,'Refused') and type(error) is module.Refused:
            code=module.finite(error)
            return 'deadline' if code=='deadline' else name+'_'+code if code in MODULE_CODES.get(name,()) else 'unknown'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def failure_packet(code):
    require(type(code) is str and code in FINITE, 'output')
    return {'schema': SCHEMA, 'binding': ACTIVE_BINDING, 'failure_code': code,
        'stage': FAILURE_STAGE, 'case_ordinal': FAILURE_CASE,
        'attempt_reusable': False, 'claim_state': CLAIM_STATE,'child_observation':CHILD_OBSERVATION,
        'deadline_fired':DEADLINE_FIRED, **FALSE_FLAGS}

def validate_failure(value, args):
    require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code',
        'stage', 'case_ordinal', 'attempt_reusable', 'claim_state','child_observation','deadline_fired', *FALSE_FLAGS}
        and value['schema'] == SCHEMA
        and value['binding'] == binding(args) and type(value['failure_code']) is str
        and value['failure_code'] in FINITE and value['attempt_reusable'] is False
        and type(value['deadline_fired']) is bool and (not value['deadline_fired'] or value['failure_code']=='deadline')
        and value['claim_state'] in ('unallocated', 'allocated_unknown', 'consumed', 'consumed_or_unknown')
        and value['stage'] in STAGES and (value['case_ordinal'] is None or
            type(value['case_ordinal']) is int and 0 <= value['case_ordinal'] < 5)
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    if value['child_observation'] is not None:validate_observation(value['child_observation'])
    return value


def validate_observation(value):
    require(type(value) is dict and set(value)=={'actual_child_exit','child_stdout_pin','child_stderr_byte_count','child_stderr_sha256','failure_code'}
        and (value['actual_child_exit'] is None or type(value['actual_child_exit']) is int)
        and type(value['child_stderr_byte_count']) is int and 0<=value['child_stderr_byte_count']<=16384
        and type(value['child_stderr_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['child_stderr_sha256'])
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE),'output')
    item=value['child_stdout_pin'];require(type(item) is dict and set(item)=={'byte_count','sha256'}
        and type(item['byte_count']) is int and 0<=item['byte_count']<=MAX_OUTPUT
        and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']),'output')
    return value

def parse(raw, bound):
    require(type(raw) is bytes and 0 < len(raw) <= bound, 'bound')
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'input'); result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('input')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('input') from None

def budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= SECONDS, 'deadline')
    return deadline - time.monotonic()

def meta(info):
    result = tuple(getattr(info, key, None) for key in FIELDS)
    require(all(type(value) is int and value >= 0 for value in result), 'metadata')
    return result

class HeldFile:
    """Original nofollow leaf/ancestor descriptors; current equality only.

    This code-only held-source guard makes endpoint equality checks; native
    security for private package/DATA is enforced by separate concrete guards.
    """
    def __init__(self, path, *, maximum, expected=None, deadline):
        self.path, self.maximum, self.expected, self.deadline = Path(path), maximum, expected, deadline
        self.directories, self.fd, self.info = [], None, None

    def __enter__(self):
        require(self.path.is_absolute() and '..' not in self.path.parts, 'path')
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.directories.append((parent, parent, '.', meta(os.fstat(parent))))
            for part in self.path.parts[1:-1]:
                budget(self.deadline)
                before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.directories.append((fd, parent, part, before))
                require(stat.S_ISDIR(before[2]) and meta(os.fstat(fd)) == before, 'changed'); parent = fd
            before = meta(os.stat(self.path.name, dir_fd=parent, follow_symlinks=False))
            self.fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            require(stat.S_ISREG(before[2]) and before[5] == 1 and before[6] <= self.maximum
                and (before[6] > 0 or (before[6] == 0 and self.path.is_relative_to(ROOT) and self.path.name == '__init__.py'
                    and SOURCE_PINS.get(self.path.relative_to(ROOT).as_posix()) == sha(b'')))
                and meta(os.fstat(self.fd)) == before, 'shape')
            self.info = before; self.verify(); return self
        except BaseException:
            self.close(); raise

    def verify(self):
        budget(self.deadline)
        for fd, parent, name, before in self.directories:
            require(meta(os.fstat(fd)) == before == meta(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'changed')
        require(self.fd is not None and meta(os.fstat(self.fd)) == self.info
            == meta(os.stat(self.path.name, dir_fd=self.directories[-1][0], follow_symlinks=False)), 'changed')

    def read(self):
        self.verify(); chunks, count = [], 0
        while count <= self.info[6]:
            budget(self.deadline)
            raw = os.pread(self.fd, min(65536, self.info[6] + 1 - count), count)
            if not raw: break
            chunks.append(raw); count += len(raw)
        raw = b''.join(chunks)
        require(len(raw) == self.info[6] and (self.expected is None or pin(raw) == self.expected), 'source_pin')
        self.verify(); return raw

    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd = None
        for fd, _, _, _ in reversed(self.directories): os.close(fd)
        self.directories.clear()

    def __exit__(self, kind, *_):
        try:
            if kind is None: self.verify()
        finally: self.close()

def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'control':str(CONTROL),
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'component_profile_pins':COMPONENT_PROFILE_PINS,
        'genuine_package':str(INPUT_PACKAGE),'genuine_lineage':str(INPUT_LINEAGE),
        'purpose':'fresh_full_input_and_all_shard_conservative_coverage_plus_six_proposed_source_bindings_not_QC_execution',
        'maximum_seconds':SECONDS,'maximum_worker_seconds':WORKER_SECONDS,'validator_seconds':30,'own_reap_seconds':5,
        'maximum_output_bytes':MAX_OUTPUT,'maximum_private_bytes':MAX_PRIVATE,'maximum_bundle_bytes':3*1024*1024,
        'minimum_inroot_free_bytes':MIN_FREE_BYTES,
        'descriptor_budget':'unchanged_soft_limit_at_least_32_per_selected_source_plus512_for_unique_genuine_DATA_output_and_process_fds_no_limit_change',
        'deadline_taxonomy':'RunDeadline_outside_Exception_timer_fact_preserved_dependency_timeouts_canonical',
        'private_transport_blinding':'two_independent_os_urandom_256bit_nonces_generated_after_claim_marker_kept_only_in_distinct_private_payloads',
        'claim':'exclusive_claim_fsync_marker_before_any_retained_DATA_or_genuine_input_read',
        'normal_return':'genuine_full10field_native_security_DATA_and_held_public_source_guards_return_before_any_private_publication',
        'native_worker_policy_sha256':sha(native_profile().encode('utf8')),
        'actual_acceptance':'actual_parent_and_child_zero_and_exact_pinned_canonical_original_stdout_not_report_alone',
        'coverage':'authenticated_conservative_membership_envelope_incomplete_is_observation_not_run_readiness',
        'held_path':'no_historical_ETF_fundamental_callback_or_actual_QC_holdings_path_reconstructed',
        'cloud_binding':'proposed_historical_project_only_no_current_access_source_objects_or_rights_verified',
        'deadline_limitation':'startup_host_suspension_and_uninterruptible_IO_not_bounded',**FALSE_FLAGS}



def binding(args):
    require(all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', getattr(args, key))
        for key, length in (('expected_head', 40), ('caller_sha256', 64), ('profile_sha256', 64))), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}

def safe_env():
    support = ROOT / '.pytest_cache/r338-runtime'
    support.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(support.resolve() == support, 'environment')
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(support), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'GIT_OPTIONAL_LOCKS': '0'}

def preflight(args, deadline):
    binding(args); budget(deadline)
    soft,_=resource.getrlimit(resource.RLIMIT_NOFILE)
    require(soft==resource.RLIM_INFINITY or soft>=32*len(SOURCE_PINS)+512,'descriptor_budget')
    disk=os.statvfs(ROOT)
    require(disk.f_bavail*disk.f_frsize>=MIN_FREE_BYTES,'disk_budget')
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON and sys.flags.isolated == 1
        and Path(__file__).absolute() == SOURCE and sys.dont_write_bytecode, 'host')
    require(args.profile_sha256 == sha(canonical(profile_record())), 'source_pin')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
            (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=safe_env(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(15, budget(deadline)))
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 262144
            and result.stdout.decode('ascii').strip() == expected, 'git_state')
    with HeldFile(SOURCE, maximum=131072, expected={'byte_count': SOURCE.stat().st_size,
            'sha256': args.caller_sha256}, deadline=deadline) as held:
        raw = held.read()
    result = subprocess.run(['/usr/bin/git', 'cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
        cwd=ROOT, env=safe_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=min(15, budget(deadline)))
    require(result.returncode == 0 and not result.stderr and result.stdout == raw, 'source_pin')

def bootstrap(role,stack,deadline):
    """Compile all selected repository code from exact original held source bytes."""
    from importlib.abc import MetaPathFinder,Loader
    from importlib.util import spec_from_loader
    from importlib.machinery import ModuleSpec
    require(role in ('worker','validate') and 7<len(SOURCE_PINS)<=160,'source_pin')
    raws={}
    for relative,expected in SOURCE_PINS.items():
        require(type(relative) is str and relative.endswith('.py') and len((ROOT/relative).parts)<=32 and type(expected) is str
            and re.fullmatch('[0-9a-f]{64}',expected),'source_pin')
        held=stack.enter_context(HeldFile(ROOT/relative,maximum=1024*1024,deadline=deadline))
        raw=held.read();require(sha(raw)==expected,'source_pin');raws[relative]=raw
    names={relative[:-12].replace('/','.') if relative.endswith('/__init__.py')
        else relative[:-3].replace('/','.'):relative for relative in raws}
    require(len(names)==len(raws),'source_pin')
    sys.path[:]=[str(ROOT),*(v for v in sys.path if v and Path(v).is_absolute()
        and Path(v)!=ROOT and ROOT not in Path(v).parents)]
    # No prior repository code except this running caller/the genuine scripts namespace.
    for name,module in tuple(sys.modules.items()):
        location=getattr(module,'__file__',None)
        if type(location) is str and Path(location).is_relative_to(ROOT):
            require(Path(location)==SOURCE,'source_pin')
    if 'scripts' in sys.modules:
        package=sys.modules['scripts']
        require(getattr(package,'__file__',None) is None
            and tuple(package.__path__)==(str(ROOT/'scripts'),),'source_pin')
    class SourceLoader(Loader):
        def __init__(self,relative):self.relative=relative
        def create_module(self,spec):return None
        def exec_module(self,module):
            path=ROOT/self.relative
            module.__file__=str(path)
            if self.relative.endswith('/__init__.py'):module.__path__=[str(path.parent)]
            exec(compile(raws[self.relative],str(path),'exec'),module.__dict__)
    class SourceFinder(MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname=='scripts':
                spec=ModuleSpec(fullname,loader=None,is_package=True);spec.submodule_search_locations=[str(ROOT/'scripts')];return spec
            if fullname in names:
                relative=names[fullname]
                return spec_from_loader(fullname,SourceLoader(relative),origin=str(ROOT/relative),
                    is_package=relative.endswith('/__init__.py'))
            spec=PathFinder.find_spec(fullname,path)
            location=None if spec is None else spec.origin
            if type(location) is str and Path(location).is_absolute() and Path(location).is_relative_to(ROOT):
                raise Refused('source_pin')
            return None
    finder=SourceFinder();sys.meta_path.insert(0,finder)
    stack.callback(lambda:sys.meta_path.remove(finder) if finder in sys.meta_path else None)
    paths={'security':'scripts.arv2_relocation_security',
        'guard':'scripts.arv2_r338_quarantine_data_guard',
        'input':'scripts.arv2_r338_quarantine_input',
        'coverage':'scripts.arv2_r338_quarantine_coverage',
        'materialization':'scripts.arv2_r338_quarantine_materialization'}
    loaded={name:importlib.import_module(fullname) for name,fullname in paths.items()}
    for name in ('guard','input','coverage','materialization'):
        module=loaded[name]
        require(module.FINITE==MODULE_CODES[name],'source_pin')
        record=module.profile_record(DATA_PLAN) if name=='guard' else module.profile_record()
        require(pin(canonical(record))==COMPONENT_PROFILE_PINS[name],'source_pin')
        MODULES[name]=module
    require(loaded['guard'].DATA_PLAN==DATA_PLAN,'source_pin')
    require(not any(n=='AlgorithmImports' or n=='assistant.dispatch_fence'
        or n.startswith(('QuantConnect','quantconnect','qc.client')) for n in sys.modules),'environment')
    loaded['source_pairs']=tuple((name,raws['research/analyst_revisions_v2_qc/'+name])
        for name in sorted(loaded['materialization'].projection.HOST_SOURCE_PINS))
    return loaded

class Store:
    def __init__(self, security):
        self.fd, self.held, self.security = None, [], security
        self.directory_info, self.directory_security = None, None
        self.chain, self.pending = [], []

    def verify(self):
        require(self.fd is not None and meta(os.fstat(self.fd)) == self.directory_info
            == meta(os.stat(CONTROL, follow_symlinks=False))
            and self.directory_info[3] == os.getuid() and stat.S_IMODE(self.directory_info[2]) == 0o700
            and self.security.snapshot(self.fd) == self.directory_security
            and set(os.listdir(self.fd)) == {item[0] for item in self.held}, 'control')
        for parent, name, fd, expected, observed_security in self.chain:
            require(meta(os.fstat(fd)) == expected == meta(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and (observed_security is None or self.security.snapshot(fd) == observed_security), 'control')
        for name, fd, original, expected, observed_security in self.held:
            require(meta(os.fstat(fd)) == original == meta(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and original[3] == os.getuid() and stat.S_IMODE(original[2]) == 0o600 and original[5] == 1
                and not original[9] & ~(stat.UF_TRACKED | stat.UF_HIDDEN)
                and self.security.snapshot(fd) == observed_security
                and pin(os.pread(fd, expected['byte_count'] + 1, 0)) == expected, 'output')

    def __enter__(self):
        global CLAIM_STATE
        opened = []; path = Path('/')
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened.append((parent, '.', parent, None))
            for part in CONTROL.parts[1:]:
                path /= part
                if path in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent)
                        if path == CONTROL: CLAIM_STATE = 'allocated_unknown'
                        os.fsync(parent)
                    except FileExistsError:
                        if path == CONTROL: CLAIM_STATE = 'consumed_or_unknown'
                        require(path != CONTROL, 'claim_spent')
                before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                opened.append((parent, part, fd, None))
                require(meta(os.fstat(fd)) == before and stat.S_ISDIR(before[2]), 'control')
                if path == ROOT or ROOT in path.parents:
                    require(before[3] == os.getuid() and stat.S_IMODE(before[2]) == (0o755 if path == ROOT else 0o700), 'control')
                parent = fd
            self.fd = parent; CLAIM_STATE = 'allocated_unknown'
            self.chain = [(parent, name, fd, meta(os.fstat(fd)),
                self.security.snapshot(fd) if index >= len(ROOT.parts) - 1 else None)
                for index, (parent, name, fd, _) in enumerate(opened[:-1])]
            self.directory_info = meta(os.fstat(self.fd)); self.directory_security = self.security.snapshot(self.fd)
            os.fsync(self.fd); self.verify(); return self
        except BaseException:
            for _, _, fd, _ in reversed(opened): os.close(fd)
            self.fd = None; raise

    def write(self, name, raw):
        global CLAIM_STATE
        require(name in ('claim.json', 'worker-started.json', 'coverage-private.json', 'prepared-sources-private.bin', 'report.json', 'failure.json')
            and type(raw) is bytes and 0 < len(raw) <= MAX_PRIVATE, 'output')
        self.verify(); before = self.directory_info
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.pending.append(fd)
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); require(count > 0, 'output'); offset += count
        os.fsync(fd); require(os.pread(fd, len(raw) + 1, 0) == raw, 'output')
        require(os.stat(name, dir_fd=self.fd, follow_symlinks=False) == os.fstat(fd), 'output')
        after = meta(os.fstat(self.fd))
        require(all(after[index] == before[index] for index in (0, 1, 2, 3, 4, 9))
            and after[5] in (before[5], before[5] + 1) and after[6] >= before[6]
            and self.security.snapshot(self.fd) == self.directory_security, 'control')
        self.directory_info = after
        self.held.append((name, fd, meta(os.fstat(fd)), pin(raw), self.security.snapshot(fd)))
        self.pending.remove(fd)
        os.fsync(self.fd); self.verify()
        if name == 'claim.json': CLAIM_STATE = 'consumed'
        return pin(raw)

    def __exit__(self, *_):
        try: self.verify()
        finally:
            for _, fd, _, _, _ in self.held: os.close(fd)
            for fd in self.pending: os.close(fd)
            if self.fd is not None: os.close(self.fd)
            for _, _, fd, _, _ in reversed(self.chain): os.close(fd)

def worker(args,deadline):
    global FAILURE_STAGE
    require(type(args.intent_fd) is int and args.intent_fd>=3,'arguments')
    try:intent=os.read(args.intent_fd,4097)
    finally:os.close(args.intent_fd)
    require(intent==canonical(binding(args)),'arguments');preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('worker',sources,deadline)
        with Store(modules['security']) as store:
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}))
            marker_pin=store.write('worker-started.json',canonical({'binding':binding(args),'phase':'input_coverage_and_source_binding'}))
            coverage_nonce,bundle_nonce=os.urandom(32).hex(),os.urandom(32).hex()
            require(coverage_nonce!=bundle_nonce,'input')
            FAILURE_STAGE='retained_DATA'
            with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as data:
                raw=data.read_all_once()
                with modules['input'].GenuineInput(deadline=deadline) as genuine:
                    FAILURE_STAGE='coverage'
                    coverage,private=modules['coverage'].prepare(raw['archive'],raw['quarantine'],
                        axis=genuine.axis,bindings=genuine.bindings,membership_rows=genuine.memberships,
                        evaluator_manifest=genuine.manifest,input_binding=genuine.input_binding,
                        transport_nonce=coverage_nonce,
                        deadline=min(deadline,time.monotonic()+300))
                    FAILURE_STAGE='materialization'
                    materialization,outputs=modules['materialization'].prepare(modules['source_pairs'],
                        axis=genuine.axis,bindings=genuine.bindings,quarantine_catalog_raw=raw['quarantine'],
                        archive_raw=raw['archive'],input_binding=genuine.input_binding,
                        deadline=min(deadline,time.monotonic()+300))
                    bundle=modules['materialization'].pack_outputs(outputs,transport_nonce=bundle_nonce)
                    modules['materialization'].validate_bundle(bundle,expected_pin=pin(bundle),
                        summary=materialization,source_pairs=modules['source_pairs'],
                        deadline=min(deadline,time.monotonic()+300))
                    genuine.verify(deadline=deadline);input_receipt=genuine.receipt();budget(deadline)
                data.verify();data_receipt=data.receipt();budget(deadline)
            sources.close();FAILURE_STAGE='output'
            bundle_pin=store.write('prepared-sources-private.bin',bundle)
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'bound')
            private_pin=store.write('coverage-private.json',private_raw)
            result={'schema':SCHEMA,'diagnostic_complete':True,'coverage':coverage,
                'materialization':materialization,'input_receipt':input_receipt,
                'source_bundle_pin':bundle_pin,'coverage_private_pin':private_pin,
                'both_DATA_authenticated':True,'genuine_guard_normal_return':True,'source_guard_normal_return':True,
                'worker_marker_pin':marker_pin,'data_receipt_sha256':sha(canonical(data_receipt)),**FALSE_FLAGS}
            validate_result(result,args);preflight(args,deadline)
            report={'binding':binding(args),'result':result}
            report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}



def validate_result(value,args):
    keys={'schema','diagnostic_complete','coverage','materialization','input_receipt',
        'source_bundle_pin','coverage_private_pin','both_DATA_authenticated','genuine_guard_normal_return',
        'source_guard_normal_return','worker_marker_pin','data_receipt_sha256',*FALSE_FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA
        and value['diagnostic_complete'] is True
        and all(value[key] is True for key in ('both_DATA_authenticated','genuine_guard_normal_return','source_guard_normal_return'))
        and value['worker_marker_pin']==pin(canonical({'binding':binding(args),'phase':'input_coverage_and_source_binding'}))
        and type(value['data_receipt_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['data_receipt_sha256'])
        and all(value[k] is False for k in FALSE_FLAGS),'output')
    require(all(MODULES.get(name) is not None for name in ('input','coverage','materialization')),'source_pin')
    MODULES['input'].validate_receipt(value['input_receipt'])
    MODULES['coverage'].validate_summary(value['coverage'])
    MODULES['materialization'].validate_summary(value['materialization'])
    coverage,materialization,receipt=value['coverage'],value['materialization'],value['input_receipt']
    require(coverage['input_binding_pin']==pin(canonical(receipt['input_binding']))
        and coverage['input_binding_pin']['sha256']==receipt['input_binding_sha256']==materialization['input_binding_sha256']
        and all(coverage[key]==materialization[key] for key in
            ('quarantine_catalog_pin','vendor_archive_pin','vendor_catalog_pin','vendor_manifest_pin'))
        and value['coverage_private_pin']==coverage['private_evidence_pin'],'output')
    for key,maximum in (('source_bundle_pin',3*1024*1024),('coverage_private_pin',MAX_PRIVATE)):
        row=value[key];require(type(row) is dict and set(row)=={'byte_count','sha256'} and type(row['byte_count']) is int
            and 0<row['byte_count']<=maximum and type(row['sha256']) is str
            and re.fullmatch('[0-9a-f]{64}',row['sha256']),'output')
    return value



def native_profile():
    value='(version 1)(allow default)(deny network*)(deny file-read* file-write* (subpath "/Volumes"))'
    value+=''.join('(deny file-read* file-write* (subpath "'+path+'"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value+='(deny file-write* (require-all (require-not (subpath "'+str(CONTROL)+'"))'
    value+='(require-not (literal "'+str(CONTROL.parent)+'"))(require-not (subpath "'+str(ROOT/'.pytest_cache')+'"))(require-not (literal "/dev/null"))))'
    paths=[*(ROOT/item['relative_path'] for item in DATA_PLAN.values()),CONTROL,INPUT_PACKAGE,INPUT_LINEAGE]
    allowed={path for leaf in paths for path in (*leaf.parents,leaf) if path==ROOT/'artifacts' or ROOT/'artifacts' in path.parents}
    value+='(deny file-read* (require-all (subpath "'+str(ROOT/'artifacts')+'")'
    value+='(require-not (subpath "'+str(CONTROL)+'"))(require-not (subpath "'+str(INPUT_PACKAGE)+'"))'
    value+=''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(allowed))+'))'
    return value

def parent(args):
    preflight(args, ENTRY_DEADLINE)
    with ExitStack() as sources:
        bootstrap('validate',sources,ENTRY_DEADLINE)
        return _parent_bound(args)

def _parent_bound(args):
    global CHILD_OBSERVATION,CLAIM_STATE
    CHILD_OBSERVATION=None;preflight(args,ENTRY_DEADLINE)
    reader,writer=os.pipe()
    try:
        intent=canonical(binding(args));require(len(intent)<4096 and os.write(writer,intent)==len(intent),'bound')
    finally:os.close(writer)
    stop=min(ENTRY_DEADLINE,time.monotonic()+WORKER_SECONDS)
    command=['/usr/bin/sandbox-exec','-p',native_profile(),PYTHON,'-I','-B',str(SOURCE),'worker',
        '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256,
        '--intent-fd',str(reader),'--outer-deadline',repr(stop)]
    CLAIM_STATE='consumed_or_unknown'
    try:actual,raw,stderr_count,stderr_sha,problem=run_child(command,(reader,),stop)
    finally:os.close(reader)
    observed={'actual_child_exit':actual,'child_stdout_pin':pin(raw),'child_stderr_byte_count':stderr_count,
        'child_stderr_sha256':stderr_sha,'failure_code':problem}
    CHILD_OBSERVATION=observed
    require(problem is None,problem if problem in FINITE else 'child_failure')
    require(type(actual) is int and actual in (0,2) and stderr_count==0 and stderr_sha==sha(b'')
        and raw.endswith(b'\n') and raw.count(b'\n')==1,'child_failure')
    value=parse(raw[:-1],MAX_OUTPUT);require(canonical(value)+b'\n'==raw,'output')
    if actual==0:validate_envelope(raw,actual,args);key='outcome'
    else:validate_failure(value,args);key='failure'
    return {'binding':binding(args),'observation':observed,'output_authenticated':True,key:value}

def validate_envelope(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit == 0 and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'child_failure')
    value = parse(raw[:-1], MAX_OUTPUT); require(canonical(value) + b'\n' == raw and type(value) is dict
        and set(value) == {'binding', 'result', 'report_pin'} and value['binding'] == binding(args), 'output')
    validate_result(value['result'],args)
    require(value['report_pin'] == pin(canonical({'binding': binding(args), 'result': value['result']})), 'output')
    return value

def validate_parent_output(raw,actual_exit,args):
    require(type(actual_exit) is int and actual_exit in (0,2) and type(raw) is bytes
        and raw.endswith(b'\n') and raw.count(b'\n')==1,'output')
    value=parse(raw[:-1],MAX_OUTPUT);require(canonical(value)+b'\n'==raw and type(value) is dict,'output')
    if value.get('schema')==SCHEMA:
        require(actual_exit==2,'output');validate_failure(value,args)
        return {'binding':binding(args),'output_authenticated':True,'accepted':False,'failure':value}
    key='outcome' if actual_exit==0 else 'failure'
    require(set(value)=={'binding','observation','output_authenticated',key} and value['binding']==binding(args)
        and value['output_authenticated'] is True,'output')
    observed=validate_observation(value['observation'])
    require(type(observed['actual_child_exit']) is int and observed['actual_child_exit']==actual_exit
        and observed['child_stderr_byte_count']==0 and observed['child_stderr_sha256']==sha(b'')
        and observed['failure_code'] is None and observed['child_stdout_pin']==pin(canonical(value[key])+b'\n'),'output')
    if key=='failure':validate_failure(value[key],args)
    else:validate_envelope(canonical(value[key])+b'\n',actual_exit,args)
    return {'binding':binding(args),'output_authenticated':True,'accepted':actual_exit==0,
        **({'result':value[key]['result']} if actual_exit==0 else {'failure':value[key]})}

def run_child(command,descriptors,deadline):
    output=bytearray();stderr=hashlib.sha256();count=0;child=None;problem=None
    try:
        child=subprocess.Popen(command,cwd=ROOT,env=safe_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,close_fds=True,pass_fds=descriptors)
        with selectors.DefaultSelector() as selector:
            for stream,label in ((child.stdout,'out'),(child.stderr,'err')):
                os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,label)
            while selector.get_map() or child.poll() is None:
                for key,_ in selector.select(min(.1,budget(deadline))):
                    chunk=os.read(key.fileobj.fileno(),8192)
                    if not chunk:selector.unregister(key.fileobj)
                    elif key.data=='out':require(len(output)+len(chunk)<=MAX_OUTPUT,'bound');output.extend(chunk)
                    else:count+=len(chunk);stderr.update(chunk);require(count<=8192,'child_stderr')
        child.wait(timeout=min(5,budget(deadline)))
    except BaseException as error:problem=finite(error)
    finally:
        if child is not None:
            if child.poll() is None:child.kill()
            child.wait(timeout=5);child.stdout.close();child.stderr.close()
    return (None if child is None else child.returncode),bytes(output),count,stderr.hexdigest(),problem

class Parser(argparse.ArgumentParser):
    def error(self, message): raise Refused('arguments')

def main():
    global ACTIVE_BINDING
    parser = Parser(add_help=False)
    parser.add_argument('mode', choices=('launch', 'worker', 'validate', 'profile'))
    for name in ('expected-head', 'caller-sha256', 'profile-sha256'): parser.add_argument('--' + name)
    parser.add_argument('--intent-fd', type=int); parser.add_argument('--outer-deadline', type=float)
    parser.add_argument('--actual-parent-exit', type=int)
    args = parser.parse_args()
    if args.mode == 'profile':
        require(all(getattr(args, key) is None for key in ('expected_head', 'caller_sha256', 'profile_sha256',
            'intent_fd', 'outer_deadline', 'actual_parent_exit')), 'arguments')
        return profile_record()
    ACTIVE_BINDING = binding(args)
    if args.mode == 'launch':
        require(args.intent_fd is args.outer_deadline is args.actual_parent_exit is None, 'arguments')
        signal.signal(signal.SIGALRM,deadline_expired);signal.setitimer(signal.ITIMER_REAL,budget(ENTRY_DEADLINE))
        return parent(args)
    if args.mode == 'validate':
        require(args.intent_fd is args.outer_deadline is None and type(args.actual_parent_exit) is int
            and args.actual_parent_exit in (0, 2), 'arguments')
        signal.signal(signal.SIGALRM, deadline_expired); signal.setitimer(signal.ITIMER_REAL, 30)
        preflight(args, ENTRY_DEADLINE)
        with ExitStack() as sources:
            bootstrap('validate',sources,ENTRY_DEADLINE)
            return validate_parent_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_parent_exit, args)
    require(args.outer_deadline is not None and args.actual_parent_exit is None, 'arguments')
    deadline = min(ENTRY_DEADLINE, args.outer_deadline); budget(deadline)
    signal.signal(signal.SIGALRM, deadline_expired); signal.setitimer(signal.ITIMER_REAL, budget(deadline))
    return worker(args, deadline)

if __name__ == '__main__':
    try:
        value = main(); raw = canonical(value) + b'\n'; require(len(raw) <= MAX_OUTPUT, 'bound')
        sys.stdout.buffer.write(raw); raise SystemExit(2 if type(value) is dict and 'failure' in value else 0)
    except SystemExit: raise
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure_packet(finite(error))) + b'\n')
        raise SystemExit(2)
