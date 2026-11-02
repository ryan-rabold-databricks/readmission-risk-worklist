import pytest

from readmit.common.env_guardrail import EnvironmentMismatchError, assert_environment


def test_matching_dev_targets_pass():
    env = assert_environment("dev", "rtr_demo_catalog", "readmission-worklist", "readmission_worklist")
    assert env.catalog == "rtr_demo_catalog"


def test_omitted_lakebase_targets_are_not_checked():
    assert_environment("prod", "prod_care_management")


def test_dev_run_against_prod_catalog_is_rejected():
    with pytest.raises(EnvironmentMismatchError, match="catalog='prod_care_management'"):
        assert_environment("dev", "prod_care_management")


def test_wrong_lakebase_project_is_rejected():
    with pytest.raises(EnvironmentMismatchError, match="lakebase_project"):
        assert_environment("dev", "rtr_demo_catalog", lakebase_project="other-project")


def test_unknown_env_is_rejected():
    with pytest.raises(EnvironmentMismatchError, match="Unknown environment"):
        assert_environment("staging", "rtr_demo_catalog")
