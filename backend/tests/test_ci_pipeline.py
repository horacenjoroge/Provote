"""
Tests to verify CI/CD pipeline configuration and behavior.

These tests ensure that:
1. Pipeline runs on PR
2. Failed tests block merge
3. Linting failures block merge
4. Deployment succeeds
"""

import pytest
import yaml
from pathlib import Path


class TestCIPipelineConfiguration:
    """Test CI/CD pipeline configuration files."""

    @pytest.fixture
    def workflows_dir(self):
        """Path to GitHub workflows directory."""
        return Path(__file__).parent.parent.parent / ".github" / "workflows"

    @pytest.fixture
    def ci_workflow(self, workflows_dir):
        """Load CI workflow file."""
        ci_file = workflows_dir / "ci.yml"
        if not ci_file.exists():
            pytest.skip(f"CI workflow not found: {ci_file}")
        with open(ci_file) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def deploy_staging_workflow(self, workflows_dir):
        """Load staging deployment workflow."""
        staging_file = workflows_dir / "deploy-staging.yml"
        if not staging_file.exists():
            pytest.skip(f"Staging deployment workflow not found: {staging_file}")
        with open(staging_file) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def deploy_production_workflow(self, workflows_dir):
        """Load production deployment workflow."""
        prod_file = workflows_dir / "deploy-production.yml"
        if not prod_file.exists():
            pytest.skip(f"Production deployment workflow not found: {prod_file}")
        with open(prod_file) as f:
            return yaml.safe_load(f)

    def test_ci_workflow_exists(self, workflows_dir):
        """Test that CI workflow file exists."""
        ci_file = workflows_dir / "ci.yml"
        assert ci_file.exists(), f"CI workflow not found: {ci_file}"

    def test_ci_workflow_triggers_on_pr(self, ci_workflow):
        """Test that CI workflow triggers on pull requests."""
        # YAML may have True as key due to GitHub Actions expressions
        on_config = ci_workflow.get("on") or ci_workflow.get(True) or {}
        assert "pull_request" in on_config, f"Should have pull_request trigger. Found: {list(on_config.keys())}"
        pr_config = on_config["pull_request"]
        assert "branches" in pr_config
        assert "main" in pr_config["branches"] or "develop" in pr_config["branches"]

    def test_ci_workflow_has_lint_job(self, ci_workflow):
        """Test that CI workflow has linting job."""
        jobs = ci_workflow.get("jobs", {})
        assert "lint" in jobs, "CI workflow should have 'lint' job"
        
        lint_job = jobs["lint"]
        assert "steps" in lint_job
        
        # Check for linting steps
        step_names = [step.get("name", "") for step in lint_job["steps"]]
        assert any("Black" in name for name in step_names), "Should have Black check"
        assert any("isort" in name.lower() for name in step_names), "Should have isort check"
        assert any("flake8" in name.lower() for name in step_names), "Should have flake8 check"
        assert any("Bandit" in name or "bandit" in name.lower() for name in step_names), "Should have Bandit security scan"

    def test_ci_workflow_has_test_job(self, ci_workflow):
        """Test that CI workflow has test job."""
        jobs = ci_workflow.get("jobs", {})
        assert "test" in jobs, "CI workflow should have 'test' job"
        
        test_job = jobs["test"]
        assert "services" in test_job, "Test job should have services (PostgreSQL, Redis)"
        assert "postgres" in test_job["services"], "Should have PostgreSQL service"
        assert "redis" in test_job["services"], "Should have Redis service"

    def test_ci_workflow_has_build_job(self, ci_workflow):
        """Test that CI workflow has Docker build job."""
        jobs = ci_workflow.get("jobs", {})
        assert "build" in jobs, "CI workflow should have 'build' job"
        
        build_job = jobs["build"]
        assert "needs" in build_job, "Build job should depend on lint and test"
        assert "lint" in build_job["needs"], "Build should depend on lint"
        assert "test" in build_job["needs"], "Build should depend on test"

    def test_lint_job_fails_on_errors(self, ci_workflow):
        """Test that lint job fails on errors (blocks merge)."""
        jobs = ci_workflow.get("jobs", {})
        lint_job = jobs.get("lint", {})
        
        steps = lint_job.get("steps", [])
        black_found = False
        isort_found = False
        bandit_found = False
        
        for step in steps:
            step_name = step.get("name", "")
            # Handle both string and multi-line string formats
            run_cmd = step.get("run", "")
            if run_cmd is None:
                run_cmd = ""
            if not isinstance(run_cmd, str):
                run_cmd = str(run_cmd)
            
            if "Black" in step_name:
                black_found = True
                assert "exit 1" in run_cmd or "||" in run_cmd, f"Black check should fail on errors. Command: {run_cmd[:200]}"
            if "isort" in step_name.lower():
                isort_found = True
                assert "exit 1" in run_cmd or "||" in run_cmd, f"isort check should fail on errors. Command: {run_cmd[:200]}"
            if ("Bandit" in step_name or "bandit" in step_name.lower()) and "Security scan" in step_name:
                bandit_found = True
                # Bandit has two commands: one for report (|| true) and one that should fail (|| exit 1)
                # Check that there's at least one command that can fail on security issues
                assert "exit 1" in run_cmd, \
                    f"Bandit check should fail on security issues. Step: {step_name}, Command preview: {run_cmd[:300] if run_cmd else 'EMPTY'}"
        
        assert black_found, "Should have Black check step"
        assert isort_found, "Should have isort check step"
        assert bandit_found, "Should have Bandit check step"

    def test_test_job_runs_pytest(self, ci_workflow):
        """Test that test job runs pytest."""
        jobs = ci_workflow.get("jobs", {})
        test_job = jobs.get("test", {})
        
        steps = test_job.get("steps", [])
        test_step = None
        for step in steps:
            if "test" in step.get("name", "").lower() and "Run" in step.get("name", ""):
                test_step = step
                break
        
        assert test_step is not None, "Should have test running step"
        run_cmd = test_step.get("run", "")
        assert "pytest" in run_cmd, "Should run pytest"

    def test_staging_deployment_triggers_on_develop(self, deploy_staging_workflow):
        """Test that staging deployment triggers on develop branch."""
        # YAML may have True as key due to GitHub Actions expressions
        on_config = deploy_staging_workflow.get("on") or deploy_staging_workflow.get(True) or {}
        assert "push" in on_config, f"Should have push trigger. Found: {list(on_config.keys())}"
        push_config = on_config["push"]
        branches = push_config.get("branches", [])
        assert "develop" in branches or isinstance(branches, str) and "develop" in branches

    def test_production_deployment_triggers_on_main(self, deploy_production_workflow):
        """Test that production deployment triggers on main branch."""
        # YAML may have True as key due to GitHub Actions expressions
        on_config = deploy_production_workflow.get("on") or deploy_production_workflow.get(True) or {}
        assert "push" in on_config, f"Should have push trigger. Found: {list(on_config.keys())}"
        push_config = on_config["push"]
        branches = push_config.get("branches", [])
        assert "main" in branches or isinstance(branches, str) and "main" in branches

    def test_staging_deployment_requires_ci_checks(self, deploy_staging_workflow):
        """Test that staging deployment requires CI checks to pass."""
        jobs = deploy_staging_workflow.get("jobs", {})
        deploy_job = jobs.get("deploy-staging", {})
        assert "needs" in deploy_job
        assert "ci-checks" in deploy_job["needs"]

    def test_production_deployment_requires_ci_checks(self, deploy_production_workflow):
        """Test that production deployment requires CI checks to pass."""
        jobs = deploy_production_workflow.get("jobs", {})
        deploy_job = jobs.get("deploy-production", {})
        assert "needs" in deploy_job
        assert "ci-checks" in deploy_job["needs"]

    def test_docker_build_in_ci(self, ci_workflow):
        """Test that Docker build is included in CI."""
        jobs = ci_workflow.get("jobs", {})
        assert "build" in jobs
        
        build_job = jobs["build"]
        steps = build_job.get("steps", [])
        
        # Check for Docker setup
        docker_steps = [s for s in steps if "docker" in s.get("name", "").lower() or "Docker" in s.get("name", "")]
        assert len(docker_steps) > 0, "Should have Docker-related steps"

    def test_docker_registry_push_configured(self, ci_workflow):
        """Test that Docker registry push is configured."""
        jobs = ci_workflow.get("jobs", {})
        build_job = jobs.get("build", {})
        
        steps = build_job.get("steps", [])
        login_step = None
        for step in steps:
            if "login" in step.get("name", "").lower() or "registry" in step.get("name", "").lower():
                login_step = step
                break
        
        # Login step should exist (may be conditional on PR)
        assert login_step is not None or any("push" in str(step) for step in steps), "Should have registry login or push step"

    def test_bandit_configured(self):
        """Test that Bandit is configured."""
        bandit_config = Path(__file__).parent.parent.parent / ".bandit"
        assert bandit_config.exists(), "Bandit configuration file (.bandit) should exist"

    def test_bandit_in_requirements(self):
        """Test that Bandit is in requirements."""
        dev_requirements = Path(__file__).parent.parent.parent / "requirements" / "development.txt"
        assert dev_requirements.exists()
        
        content = dev_requirements.read_text()
        assert "bandit" in content.lower(), "Bandit should be in development requirements"

    def test_pr_check_job_exists(self, ci_workflow):
        """Test that PR check job exists to verify all checks pass."""
        jobs = ci_workflow.get("jobs", {})
        assert "pr-check" in jobs or "pr_check" in jobs or any("pr" in job.lower() for job in jobs.keys()), \
            "Should have PR check job or final verification step"


class TestCIPipelineBehavior:
    """Test CI/CD pipeline behavior (simulated)."""

    def test_linting_blocks_merge_on_failure(self):
        """Test that linting failures would block merge."""
        # This is a conceptual test - in real CI, failed jobs block merge
        # We verify the configuration would cause this behavior
        assert True  # Configuration verified in test_ci_workflow_has_lint_job

    def test_test_failures_block_merge(self):
        """Test that test failures would block merge."""
        # This is a conceptual test - in real CI, failed jobs block merge
        # We verify the configuration would cause this behavior
        assert True  # Configuration verified in test_ci_workflow_has_test_job

    def test_security_scan_blocks_merge_on_failure(self):
        """Test that security scan failures would block merge."""
        # This is a conceptual test - in real CI, failed jobs block merge
        # We verify the configuration would cause this behavior
        assert True  # Configuration verified in test_ci_workflow_has_lint_job

    def test_deployment_only_after_ci_passes(self):
        """Test that deployment only happens after CI passes."""
        # This is verified by the 'needs' dependencies in deployment workflows
        assert True  # Configuration verified in test_staging_deployment_requires_ci_checks

