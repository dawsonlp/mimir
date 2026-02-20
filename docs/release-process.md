# Release Process

## Overview

Mímir uses a tag-based release workflow. When a version tag is pushed to GitHub, the CI/CD pipeline automatically builds multi-architecture Docker images (amd64 + arm64) and pushes them to Docker Hub.

## Branching Strategy

- **main**: Stable releases only. All releases are tagged from main.
- **dev**: Active development branch. All work happens here.

## Development Workflow

1. Work on features/fixes in the `dev` branch
2. Create feature branches from `dev` if needed: `git checkout -b feature/my-feature`
3. Merge completed work back to `dev`
4. When ready to release, merge `dev` to `main` and create a version tag

## Creating a Release

### 1. Ensure dev is ready
```bash
# Ensure all tests pass on dev
git checkout dev
git pull origin dev
```

### 2. Merge to main
```bash
git checkout main
git pull origin main
git merge dev
git push origin main
```

### 3. Create and push version tag
```bash
# Create annotated tag
git tag -a v1.1.0 -m "Release v1.1.0: Brief description"

# Push the tag (this triggers the release workflow)
git push origin v1.1.0
```

### 4. Monitor the release
```bash
# Watch the GitHub Actions workflow
gh run list --workflow=release.yaml --limit 1

# Or view in browser
open https://github.com/dawsonlp/mimir/actions/workflows/release.yaml
```

## Version Numbering

Follow semantic versioning (SemVer):

- **Major** (v2.0.0): Breaking changes
- **Minor** (v1.1.0): New features, backward compatible
- **Patch** (v1.0.1): Bug fixes, backward compatible

## What the Release Workflow Does

When a `v*` tag is pushed, the workflow (`.github/workflows/release.yaml`):

1. Builds multi-arch Docker image for the API
2. Pushes to Docker Hub with the version tag AND `latest`
3. Creates a GitHub Release with auto-generated release notes

## Docker Images

Each release produces:

| Image | Tags |
|-------|------|
| `dawsonlp/mimir-api` | `v1.x.x`, `latest` |

## Prerequisites

The release workflow requires these GitHub repository secrets:

- `DOCKERHUB_USERNAME`: Docker Hub username
- `DOCKERHUB_TOKEN`: Docker Hub access token

## Hotfix Process

For urgent fixes that can't wait for regular dev cycle:

```bash
# Create hotfix branch from main
git checkout main
git checkout -b hotfix/critical-fix

# Make fix, commit
git add .
git commit -m "fix: critical bug description"

# Merge to main
git checkout main
git merge hotfix/critical-fix
git push origin main

# Tag patch release
git tag -a v1.0.1 -m "Hotfix: critical bug description"
git push origin v1.0.1

# Merge fix back to dev
git checkout dev
git merge main
git push origin dev

# Cleanup
git branch -d hotfix/critical-fix
```

## Troubleshooting

### Release workflow fails at Docker Hub login
- Verify `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets exist
- Regenerate Docker Hub access token if needed

### Release workflow fails at GitHub Release creation
- Ensure workflow has `permissions: contents: write`
- Check if a release with that tag already exists

### Build fails
- Check the workflow logs: `gh run view <run-id> --log-failed`
- Verify Dockerfiles are valid and dependencies are available