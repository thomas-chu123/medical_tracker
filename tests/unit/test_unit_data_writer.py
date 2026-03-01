
import pytest
from app.services.data_writer import _parse_doctor_name

@pytest.mark.unit
@pytest.mark.parametrize("raw_name, expected_name, expected_specialty", [
    # Story: Standard name should return just the name
    ("王大明", "王大明", None),
    
    # Story: Name with English characters
    ("John Doe", "John Doe", None),

    # Story: Name with parentheses should be parsed into name and specialty
    ("陳小美(家庭醫學科)", "陳小美", "家庭醫學科"),
    
    # Story: Name with English parentheses
    ("David Chen(Cardiology)", "David Chen", "Cardiology"),

    # Story: Name with extra spaces should be stripped
    ("  張三豐  ", "張三豐", None),
    ("  李四(骨科)  ", "李四", "骨科"),

    # Story: Empty or invalid input
    ("", "", None),
    ("()", "()", None),
    ("(abc)", "(abc)", None),
])
def test_parse_doctor_name(raw_name, expected_name, expected_specialty):
    """Unit test for the _parse_doctor_name helper function."""
    name, specialty = _parse_doctor_name(raw_name)
    assert name == expected_name
    assert specialty == expected_specialty
