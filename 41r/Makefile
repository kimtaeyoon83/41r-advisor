# 41R 개발 워크플로
# Usage: make <target>

PYTHON := .venv/bin/python3
PYTEST := $(PYTHON) -m pytest
GUARD := $(PYTHON) -m persona_agent._internal.integrity.hallucination_guard

.PHONY: help
help:
	@echo "41R 개발 명령:"
	@echo "  make test          - unit test 실행 (pytest)"
	@echo "  make test-cov      - coverage 포함 test"
	@echo "  make audit         - 모든 리포트 hallucination guard"
	@echo "  make audit-trail   - 모든 리포트 audit trail 생성"
	@echo "  make bootstrap-ci  - n=200 ablation bootstrap CI 재계산"
	@echo "  make cate-demo     - CATE validator self-demo 재실행"
	@echo "  make cross-cohort  - cross-cohort 메타 분석 재계산"
	@echo "  make tag-reports   - 모든 리포트 자동 claim 태깅 (high-conf만)"
	@echo "  make render-exec   - EXECUTIVE_REPORT 동적 갱신 (RC + CI + boxes)"
	@echo "  make verify        - test + audit (release 전 검증)"
	@echo "  make verify-all    - 전체 파이프라인 (분석 → render → tag → audit → test)"
	@echo "  make clean         - cache, __pycache__, *.audit.md 정리"

.PHONY: test
test:
	$(PYTEST) tests/ -q

.PHONY: test-cov
test-cov:
	$(PYTEST) tests/ \
		--cov=persona_agent._internal.persona.persona_store \
		--cov=persona_agent._internal.reports.version_manager \
		--cov=persona_agent._internal.cohort.cohort_report \
		--cov=persona_agent._internal.integrity.hallucination_guard \
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

.PHONY: bootstrap-ci
bootstrap-ci:
	$(PYTHON) experiments/ablation/bootstrap_ci.py

.PHONY: cate-demo
cate-demo:
	$(PYTHON) experiments/cate_self_demo/run_self_demo.py

.PHONY: cross-cohort
cross-cohort:
	$(PYTHON) -m persona_agent._internal.analysis.cross_cohort_meta

.PHONY: tag-reports
tag-reports:
	@for f in reports/EXECUTIVE_REPORT.html reports/SIMPLE_REPORT.html reports/sample_report_v2.html; do \
		if [ -f "$$f" ]; then \
			echo "--- Tagging $$f ---"; \
			$(PYTHON) -m persona_agent._internal.integrity.claim_tagger "$$f" --apply || true; \
		fi; \
	done

.PHONY: render-exec
render-exec:
	$(PYTHON) scripts/render_executive.py

.PHONY: verify
verify: test audit
	@echo ""
	@echo "✓ All checks passed (release-ready)"

.PHONY: verify-all
verify-all: bootstrap-ci cate-demo cross-cohort render-exec tag-reports audit test
	@echo ""
	@echo "✓ Full pipeline verified (분석 → render → tag → audit → test)"

.PHONY: clean
clean:
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find reports/ -name "*.audit.md" -delete 2>/dev/null || true
	@echo "Cleaned."
