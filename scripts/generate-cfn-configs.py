#!/usr/bin/env python3
"""
Reads config/deployment.json and writes per-stack CloudFormation TemplateConfiguration
JSON files into the config/ directory. Run this locally or from the buildspec.

Output files (used as TemplateConfiguration in CodePipeline deploy actions):
  config/01-foundation-config.json
  config/02-website-config.json
  config/03-cicd-config.json

TemplateConfiguration format: {"Parameters": {"Key": "Value"}}
The StackName key is stripped — it is a deploy action property, not a CFN parameter.
"""

import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(REPO_ROOT, "config", "deployment.json")

STACK_MAP = {
    "foundation": "01-foundation-config.json",
    "website":    "02-website-config.json",
    "cicd":       "03-cicd-config.json",
}

EXCLUDED_KEYS = {"StackName", "_comment"}

with open(CONFIG_FILE) as f:
    config = json.load(f)

for section, filename in STACK_MAP.items():
    params = {k: v for k, v in config[section].items() if k not in EXCLUDED_KEYS}
    output = {"Parameters": params}
    out_path = os.path.join(REPO_ROOT, "config", filename)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")
    print(f"Written: config/{filename}  ({len(params)} parameters)")
