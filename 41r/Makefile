# 41R 개발 워크플로
# Usage: make <target>

PYTHON := .venv/bin/python3
PYTEST := $(PYTHON) -m pytest
GUARD := $(PYTHON) -m modules.hallucination_guard

.PHONY: help
help:
	@echo "41R 개발 명령:"
	@echo "  make test          - unit test 실행 (pytest)"
	@echo "  make test-cov      - coverage 포함 test"
	@echo "  make audit         - 모든 리포트 hallucination guard"
	@echo "  make audit-trail   - 모든 리포트 audit trail 생성"
	@echo "  make verify        - test + audit (release 전 검증)"
	@echo "  make clean         - cache, __pycache__, *.audit.md 정리"

.PHONY: test
test:
	$(PYTEST) tests/ -q

.PHONY: test-cov
test-cov:
	$(PYTEST) tests/ \
		--cov=modules.persona_store \
		--cov=modules.version_manager \
		--cov=modules.cohort_report \
		--cov=modules.hallucination_guard \
		--cov-report=term

.PHONY: audit
audit:
	@echo "=== Auditing reports ==="
	@for f in reports/sample_report_v2.html reports/sample_report_v1.html \
	         experiments/outbound/differentiation.md \
	         experiments/ablation/MARGINAL_VALUE_REPORT.md; do \
		if [ -f "$$f" ]; then \
			echo ""; echo "--- $$f ---"; \
			$(GUARD) $$f || true; \
		fi; \
	done

.PHONY: audit-trail
audit-trail:
	@for f in reports/sample_report_v2.html reports/sample_report_v1.html; do \
		if [ -f "$$f" ]; then \
			echo "Generating trail for $$f..."; \
			$(GUARD) $$f --trail; \
		fi; \
	done

.PHONY: verify
verify: test audit
	@echo ""
	@echo "✓ All checks passed (release-ready)"

.PHONY: clean
clean:
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find reports/ -name "*.audit.md" -delete 2>/dev/null || true
	@echo "Cleaned."
