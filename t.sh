#!/bin/bash
.venv/bin/python -m pytest tests/unit/brokers/services/test_pipeline_wiring.py -v --tb=short 2>&1 > /tmp/test_out.txt
echo RC=$? >> /tmp/test_out.txt
