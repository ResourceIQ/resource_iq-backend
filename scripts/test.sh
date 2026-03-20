#!/usr/bin/env bash

set -e
set -x

# Run mock-only service tests; avoid root tests/conftest.py DB fixtures.
coverage run -m pytest tests/services/ --confcutdir=tests/services
coverage report
coverage html --title "${@-coverage}"
