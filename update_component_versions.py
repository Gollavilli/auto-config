#!/usr/bin/env python3
import os
import sys
import json
import requests
from github import Github
import re

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
        "chart_path": "charts/datadog",
        "metadata_key": "datadog.agent_version"
    },
    "wiz": {
        "type": "github",
        "github_repo": "wiz-sec/charts",
        "metadata_key": ["wiz.connector.version", "wiz.sensor.version", "wiz.admission_controller.version"]
    }
}

def get_github_release_info(repo_name, check_tag_format=None):
    """Get the latest release version from GitHub repository"""
    try:
        g = Github(os.environ.get("GITHUB_TOKEN", ""))
        repo = g.get_repo(repo_name)
        releases = repo.get_releases()
        
        # Find a valid release version
        for release in releases:
            # Skip prereleases if there are more than 1 release
            if releases.totalCount > 1 and release.prerelease:
                continue
                
            # Clean the tag name (remove 'v' prefix if present)
            version = release.tag_name
            if version.startswith('v'):
                version = version[1:]
                
            # For karpenter, ensure it follows semver and is not a controller version
            if check_tag_format == 'karpenter':
                # Only accept versions like v0.37.3 or 0.37.3, not v0.37.3-controller-v0.37.3
                if '-controller-' in version:
                    continue
                if not re.match(r'^\d+\.\d+\.\d+$', version):
                    continue
                    
            # For datadog agent, make sure it's a valid agent version
            if check_tag_format == 'datadog':
                # Datadog agent versions should look like 7.x.x
                if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+$', version):
                    continue
                    
            print(f"Found version {version} for {repo_name}", file=sys.stderr)
            return version
            
        print(f"No suitable releases found for {repo_name}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error fetching GitHub release info for {repo_name}: {str(e)}", file=sys.stderr)
        return None

def update_metadata_value(metadata, key_path, value):
    """Update a nested key in metadata dict using dot notation path"""
    keys = key_path.split('.')
    current = metadata
    
    # Navigate to the nested location
    for k in keys[:-1]:
        if k not in current:
            print(f"Warning: Key path {key_path} not found in metadata", file=sys.stderr)
            return False
        current = current[k]
    
    # Set the value if there's a change
    last_key = keys[-1]
    if last_key in current and current[last_key] != value:
        old_value = current[last_key]
        current[last_key] = value
        print(f"Updated {key_path} from {old_value} to {value}", file=sys.stderr)
        return True
    else:
        print(f"No change needed for {key_path}, current value: {current.get(last_key, 'N/A')}", file=sys.stderr)
    
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
    
    # Print the current metadata for debugging
    print(f"Current metadata contents:", file=sys.stderr)
    print(json.dumps(metadata, indent=2), file=sys.stderr)
    
    changes = []
    
    # Check each component for updates
    for component_name, config in COMPONENTS.items():
        print(f"Checking {component_name}...", file=sys.stderr)
        
        # Get latest version from GitHub
        check_tag_format = component_name if component_name in ['karpenter', 'datadog'] else None
        latest_version = get_github_release_info(config["github_repo"], check_tag_format)
        
        if not latest_version:
            print(f"Skipping {component_name} - no valid version found", file=sys.stderr)
            continue
        
        # Update metadata for this component
        updated = False
        if isinstance(config["metadata_key"], list):
            # Handle multiple keys for the same component
            for key_path in config["metadata_key"]:
                if update_metadata_value(metadata, key_path, latest_version):
                    changes.append(f"{component_name}: {key_path.split('.')[-1]} updated to {latest_version}")
                    updated = True
        else:
            # Single key for component
            if update_metadata_value(metadata, config["metadata_key"], latest_version):
                changes.append(f"{component_name}: {config['metadata_key'].split('.')[-1]} updated to {latest_version}")
                updated = True
        
        if updated:
            print(f"Updated {component_name} to {latest_version}", file=sys.stderr)
        else:
            print(f"No update needed for {component_name}", file=sys.stderr)
    
    # Save updated metadata
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Output changes for the PR description using the new GitHub Actions output format
    if changes:
        changes_str = "\n".join(changes)
        # GitHub Actions output changed from set-output to GITHUB_OUTPUT
        with open(os.environ.get('GITHUB_OUTPUT', '/dev/stdout'), 'a') as f:
            f.write(f"changes<<EOF\n{changes_str}\nEOF\n")
        print("Components updated successfully", file=sys.stderr)
    else:
        print("No components needed updating", file=sys.stderr)

if __name__ == "__main__":
    main()
