.PHONY: test demo lint
test:
	python -m pytest -q
demo:
	python -m graph_data_platform.demo
lint:
	python -m compileall graph_data_platform
