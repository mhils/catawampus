default: all

all:
	@echo "Nothing to build."

test: all
	../../tr/vendor/wvtest/wvtestrun $(MAKE) runtests

runtests: all $(wildcard *_test.py)
	set -e; \
	for d in $(filter %_test.py,$^); do \
		echo; \
		echo "Testing $$d"; \
		python $$d; \
	done
