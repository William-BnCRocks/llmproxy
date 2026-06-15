def test_acp_client_patterns_extracted():
    content = open("references/acp-client-reference.md").read()
    assert "ACP client" in content
    assert "MCP" not in content  # explicit separation
