import pytest
from app.ai.gateway.provider import NemotronProvider
from app.ai.exceptions import AIDecisionError

def test_json_extraction_clean():
    provider = NemotronProvider()
    content = '{"action": "CHARGE", "confidence": 0.9, "reason": "test"}'
    assert provider._extract_json(content) == content

def test_json_extraction_markdown_blocks():
    provider = NemotronProvider()
    content = "Here is your JSON:\n`json\n{\"action\": \"CHARGE\"}\n`\nHope it helps!"
    assert provider._extract_json(content) == '{"action": "CHARGE"}'

def test_json_extraction_multiple_markdown_blocks():
    provider = NemotronProvider()
    content = "`json\n{\"a\": 1}\n`\nAnd another:\n`json\n{\"b\": 2}\n`"
    with pytest.raises(AIDecisionError, match="Multiple JSON objects returned, ambiguous response"):
        provider._extract_json(content)

def test_json_extraction_outer_brackets():
    provider = NemotronProvider()
    content = "Thinking... {\"action\": \"ABORT\"} Done."
    assert provider._extract_json(content) == '{"action": "ABORT"}'

def test_json_extraction_multiple_brackets():
    provider = NemotronProvider()
    content = "Thinking... {\"action\": \"ABORT\"} Wait, maybe {\"action\": \"CHARGE\"}"
    with pytest.raises(AIDecisionError, match="Multiple JSON objects returned, ambiguous response"):
        provider._extract_json(content)

def test_json_extraction_no_json():
    provider = NemotronProvider()
    content = "I cannot fulfill this request."
    with pytest.raises(AIDecisionError, match="No valid JSON object found in response"):
        provider._extract_json(content)
