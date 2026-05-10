from src.parser.parser import PortInstruction, PortInstructionParser


def test_port_instruction_has_is_urgent():
    inst = PortInstruction(part_name="轴承", quantity=5,
                           action_required="出库", is_urgent=True)
    assert inst.is_urgent is True


def test_port_instruction_is_urgent_defaults_false():
    inst = PortInstruction(part_name="轴承", quantity=5)
    assert inst.is_urgent is False


def test_port_instruction_no_location_field():
    inst = PortInstruction()
    assert not hasattr(inst, "location")


def test_port_instruction_no_installation_equipment_field():
    inst = PortInstruction()
    assert not hasattr(inst, "installation_equipment")


def test_rule_based_parse_returns_port_instruction():
    parser = PortInstructionParser()
    result = parser._rule_based_parse("需要3个轴承")
    assert isinstance(result, PortInstruction)
    assert result.quantity == 3
