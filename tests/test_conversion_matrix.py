"""Every input format against every output Papyr offers, each fixture run through the engine the way the window
calls it, and each output checked independently. Run one row or column with -k, e.g. -k "PDF-to" or "to-AVIF"."""
import pytest

import fixture_factory
from conversion_matrix import Declared, declared, input_rows, run_pair, targets

pytestmark = [pytest.mark.matrix, pytest.mark.usefixtures("app")]

FIXTURES_BY_ROW = {}
for _spec in fixture_factory.ROSTER:
    FIXTURES_BY_ROW.setdefault(_spec[1], []).append(_spec[0])

CASES = [pytest.param(name, target, id=f"{row}-to-{target.key}-{name}")
         for row in input_rows() for target in targets() for name in FIXTURES_BY_ROW[row]]


def test_every_input_extension_has_a_row_and_fixtures():
    assert set(FIXTURES_BY_ROW) == set(input_rows())


@pytest.mark.parametrize("name, target", CASES)
def test_conversion(name, target, fixture_specs, tmp_path):
    spec = fixture_specs[name]
    result = run_pair(spec, target, tmp_path / "out")
    status, why = declared(spec.format, target)
    if status is Declared.UNSUPPORTED_BY_DESIGN:
        assert not target.offered
        return
    if status is Declared.CONDITIONAL:
        pytest.skip(why)
    assert result.execution == "OK" and result.validation == "PASSED", result.failure
