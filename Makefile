.DEFAULT_GOAL := check
PYTHON ?= python3
SCRIPTS := skills/multi-swe-day/scripts
export PYTHONDONTWRITEBYTECODE := 1

check:
	@$(PYTHON) $(SCRIPTS)/test_msd_lane_registry.py
	@$(PYTHON) $(SCRIPTS)/test_msd_next.py
	@$(PYTHON) $(SCRIPTS)/msd_listen_test.py
	@$(PYTHON) $(SCRIPTS)/msd_review_open.py --self-test
	@$(PYTHON) tests/test_integrations.py

record:
	@$(PYTHON) scripts/record_session.py

demo:
	@$(PYTHON) scripts/generate_demo.py

assets:
	@$(PYTHON) assets/build.py

asset-check:
	@$(PYTHON) assets/build.py --check

.PHONY: check record demo assets asset-check
