from types import SimpleNamespace

from jyotisha.chart import Position
from jyotisha.prashna import _applying


def test_applying_uses_relative_motion_across_sign_boundary() -> None:
    approaching = SimpleNamespace(
        grahas={
            "Sun": Position("Sun", 359.0, speed=1.0),
            "Mercury": Position("Mercury", 1.0, speed=0.0),
        }
    )
    separating = SimpleNamespace(
        grahas={
            "Sun": Position("Sun", 1.0, speed=1.0),
            "Mercury": Position("Mercury", 359.0, speed=0.0),
        }
    )
    assert _applying(approaching, "Sun", "Mercury")[0]
    assert not _applying(separating, "Sun", "Mercury")[0]
