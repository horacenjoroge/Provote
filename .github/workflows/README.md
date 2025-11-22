# GitHub Actions CI/CD Workflows

This directory contains GitHub Actions workflows for automated testing, building, and deployment.

## Workflows

### 1. `ci.yml` - Main CI Pipeline

**Triggers:**
- Pull requests to `main` or `develop`
- Pushes to `main` or `develop`

**Jobs:**
1. **lint** - Code quality checks
   - Black (code formatting)
   - isort (import sorting)
   - flake8 (linting)
   - Bandit (security scanning)

2. **test** - Run test suite
   - Sets up PostgreSQL and Redis services
   - Runs pytest with coverage
   - Uploads coverage reports

3. **build** - Build Docker image
   - Builds Docker image using Dockerfile
   - Pushes to GitHub Container Registry (on non-PR events)
   - Tests the built image

4. **pr-check** - PR merge verification
   - Runs after all other jobs
   - Verifies all checks passed

**Blocking Behavior:**
- All jobs must pass for PR to be mergeable
- Failed linting blocks merge
- Failed tests block merge
- Security issues block merge

### 2. `deploy-staging.yml` - Staging Deployment

**Triggers:**
- Push to `develop` branch
- Manual workflow dispatch

**Process:**
1. Runs CI checks (reusable workflow)
2. Builds and pushes Docker image tagged as `staging`
3. Deploys to staging environment
4. Runs health checks

**Environment:** `staging`

### 3. `deploy-production.yml` - Production Deployment

**Triggers:**
- Push to `main` branch
- Tags matching `v*` (e.g., `v1.0.0`)
- Manual workflow dispatch

**Process:**
1. Runs CI checks (reusable workflow)
2. Runs production-specific checks
3. Builds and pushes Docker image
4. Creates GitHub release (for tags)
5. Deploys to production environment
6. Runs health checks

**Environment:** `production`

## Configuration

### Required Secrets

For Docker registry push (automatically available):
- `GITHUB_TOKEN` - Automatically provided by GitHub Actions

For deployment (if using external services):
- `DEPLOYMENT_TOKEN` - Token for deployment service
- `AWS_ACCESS_KEY_ID` - If deploying to AWS
- `AWS_SECRET_ACCESS_KEY` - If deploying to AWS
- (Add others as needed for your infrastructure)

### Environment Variables

Set in repository settings → Environments:
- **staging** - Staging environment variables
- **production** - Production environment variables

### Branch Protection Rules

Configure in repository settings → Branches:

**For `main` branch:**
- Require status checks: `lint`, `test`, `build`
- Require branches to be up to date
- Require pull request reviews

**For `develop` branch:**
- Require status checks: `lint`, `test`, `build`
- Require branches to be up to date

## Usage

### Running CI Locally

```bash
# Install dependencies
pip install -r requirements/development.txt

# Run linting
black --check backend/
isort --check-only backend/
flake8 backend/
bandit -r backend/ -ll

# Run tests
pytest --cov=backend -v
```

### Triggering Deployments

**Automatic:**
- Push to `develop` → Deploys to staging
- Push to `main` → Deploys to production
- Create tag `v1.0.0` → Deploys to production

**Manual:**
- Go to Actions tab
- Select workflow
- Click "Run workflow"

## Monitoring

- **Workflow Runs:** GitHub Actions tab
- **Test Results:** Uploaded as artifacts
- **Coverage Reports:** Codecov integration
- **Security Reports:** Bandit reports uploaded as artifacts

## Troubleshooting

### CI Fails on Linting

```bash
# Fix formatting
black backend/
isort backend/

# Fix linting issues
flake8 backend/ --show-source
```

### CI Fails on Tests

```bash
# Run tests locally
pytest -v

# Check specific test
pytest backend/tests/test_specific.py -v
```

### Docker Build Fails

```bash
# Test Docker build locally
cd docker
docker build -f Dockerfile -t provote:test ..
```

## Migration from Old Workflows

The old `test.yml` and `deploy.yml` workflows are still present for backward compatibility. The new `ci.yml` workflow replaces `test.yml` with enhanced features:

- **Enhanced linting** with Bandit security scanning
- **Better error messages** with emoji indicators
- **Artifact uploads** for reports
- **PR check job** for merge verification

To migrate:
1. Update branch protection rules to use new job names
2. Test the new workflow on a PR
3. Remove old workflows once confirmed working

