from scripts import registry


def test_no_shipped_role_names_an_agent():
    roles = registry.load_roles()
    assert [name for name, cfg in roles.items() if "agent" in cfg] == []
    assert "rigorous-research-" not in registry.ROLES_PATH.read_text(encoding="utf-8")


def test_checking_roles_are_roles():
    assert set(registry.checking_roles()) <= set(registry.load_roles())
