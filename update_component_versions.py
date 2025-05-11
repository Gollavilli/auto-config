#!/usr/bin/env python3
import os
import sys
import json
import requests
from github import Github
import yaml

# Configuration - Components to check for updates
COMPONENTS = {
    "karpenter": {
        "type": "github",
        "github_repo": "aws/karpenter-provider-aws",
        "metadata_key": "karpenter.version"
    },
    "aws-load-balancer-controller": {
        "type": "github",
        "github_repo": "kubernetes-sigs/aws-load-balancer-controller",
        "metadata_key": "aws_ingress_controller.version"
    },
    "datadog": {
        "type": "github",
        "github_repo": "DataDog/helm-charts",
        "metadata_key": "datadog.agent_version"
    },
    "wiz": {
        "type": "github",
        "github_repo": "wiz-sec/charts",
        "metadata_key": ["wiz.connector.version", "wiz.sensor.version", "wiz.admission_controller.version"]
    }
}

def get_github_release_info(repo_name):
    """Get the latest release version from GitHub repository"""
    try:
        g = Github(os.environ.get("GITHUB_TOKEN"))
        repo = g.get_repo(repo_name)
        releases = repo.get_releases()
        
        if releases.totalCount > 0:
            latest_release = releases[0]
            # Clean the tag name (remove 'v' prefix if present)
            version = latest_release.tag_name
            if version.startswith('v'):
                version = version[1:]
            return version
        else:
            print(f"No releases found for {repo_name}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Error fetching GitHub release info for {repo_name}: {str(e)}", file=sys.stderr)
        return None

def update_metadata_value(metadata, key_path, value):
    """Update a nested key in metadata dict using dot notation path"""
    keys = key_path.split('.')
    current = metadata
    
    # Navigate to the nested location
    for i, k in enumerate(keys[:-1]):
        if k not in current:
            print(f"Warning: Key path {key_path} not found in metadata", file=sys.stderr)
            return False
        current = current[k]
    
    # Set the value if there's a change
    last_key = keys[-1]
    if last_key in current and current[last_key] != value:
        current[last_key] = value
        return True
    
    return False

def main():
    # Path to metadata file
    metadata_file = "config/metadata.json"
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(metadata_file), exist_ok=True)
    
    # Load existing metadata
    try:
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
    except FileNotFoundError:
        print(f"Error: Metadata file {metadata_file} not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Metadata file {metadata_file} is not valid JSON", file=sys.stderr)
        sys.exit(1)
    
    changes = []
    
    # Check each component for updates
    for component_name, config in COMPONENTS.items():
        print(f"Checking {component_name}...", file=sys.stderr)
        
        # Get latest version from GitHub
        latest_version = get_github_release_info(config["github_repo"])
        if not latest_version:
            continue
        
        # Update metadata for this component
        updated = False
        if isinstance(config["metadata_key"], list):
            # Handle multiple keys for the same component
            for key_path in config["metadata_key"]:
                if update_metadata_value(metadata, key_path, latest_version):
                    changes.append(f"- {component_name}: {key_path.split('.')[-1]} updated to {latest_version}")
                    updated = True
        else:
            # Single key for component
            if update_metadata_value(metadata, config["metadata_key"], latest_version):
                changes.append(f"- {component_name}: {config['metadata_key'].split('.')[-1]} updated to {latest_version}")
                updated = True
        
        if updated:
            print(f"Updated {component_name} to {latest_version}", file=sys.stderr)
    
    # Save updated metadata
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Output changes for the PR description
    if changes:
        changes_str = "\n".join(changes)
        print(f"::set-output name=changes::{changes_str}")
        print("Components updated successfully", file=sys.stderr)
    else:
        print("No components needed updating", file=sys.stderr)

if __name__ == "__main__":
    main()
