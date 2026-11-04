from pathlib import Path

import pytest

from quant_engine.validation import HoldoutRegistry, PassBar, RegistryError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "rule.py").write_text("THRESHOLD = 1\n")
    return tmp_path


def register(registry: HoldoutRegistry, project: Path, family: str = "idea", **params: int) -> str:
    return registry.register(
        family=family,
        hypothesis="it works",
        segments=["P3"],
        files=["rule.py"],
        params=params or {"x": 1},
        pass_bar=PassBar(min_trades=3, min_mean=0.0, min_t=1.0),
        root=project,
    )


def test_register_open_and_record(project: Path) -> None:
    registry = HoldoutRegistry(project / "registry.json")
    reg_id = register(registry, project)
    registry.open(reg_id, root=project)
    verdict = registry.record_result(reg_id, [0.5, 0.4, 0.6, 0.5])
    assert verdict.passed
    assert HoldoutRegistry(project / "registry.json").entries()[reg_id]["verdict"]["passed"]


def test_a_changed_file_blocks_the_opening(project: Path) -> None:
    registry = HoldoutRegistry(project / "registry.json")
    reg_id = register(registry, project)
    (project / "rule.py").write_text("THRESHOLD = 2  # tweaked after registering\n")
    assert registry.changed_files(reg_id, project) == ["rule.py"]
    with pytest.raises(RegistryError, match="changed since registration"):
        registry.open(reg_id, root=project)


def test_a_registration_opens_once_and_spends_its_segments(project: Path) -> None:
    registry = HoldoutRegistry(project / "registry.json")
    reg_id = register(registry, project)
    registry.open(reg_id, root=project)
    with pytest.raises(RegistryError, match="already opened"):
        registry.open(reg_id, root=project)
    assert registry.spent("idea") == {"P3"}
    with pytest.raises(RegistryError, match="already spent"):
        register(registry, project, x=2)  # a tweaked variant on the same segment
    register(registry, project, family="another idea")  # other families are unaffected


def test_results_need_an_opening_and_are_recorded_once(project: Path) -> None:
    registry = HoldoutRegistry(project / "registry.json")
    reg_id = register(registry, project)
    with pytest.raises(RegistryError, match="not been opened"):
        registry.record_result(reg_id, [1.0, 2.0, 3.0])
    registry.open(reg_id, root=project)
    registry.record_result(reg_id, [1.0, 2.0, 3.0])
    with pytest.raises(RegistryError, match="already has a result"):
        registry.record_result(reg_id, [5.0, 5.0, 5.0])


def test_pass_bar_gives_its_reasons() -> None:
    verdict = PassBar(min_trades=5, min_mean=0.05, min_t=2.0).judge([0.1, -0.1, 0.02])
    assert not verdict.passed
    assert len(verdict.reasons) == 3
    assert PassBar(min_trades=2, min_t=1.0).judge([1.0, 1.2, 0.9]).passed


def test_unknown_registrations_are_errors(project: Path) -> None:
    with pytest.raises(RegistryError, match="no registration"):
        HoldoutRegistry(project / "registry.json").open("missing", root=project)
