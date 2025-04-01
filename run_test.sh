#!/bin/bash
# Run the OpenRouter test script with our fixes
cd /Users/teez/Development/Claude/openmanus/OpenManus
python scripts/test_openrouter.py --model deepseek-chat --prompt "Write a simple Python function to calculate factorial" --no-stream
