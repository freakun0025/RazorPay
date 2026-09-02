import pytest
from sqlalchemy import text
from app.persistence.database import engine

def test_recovery_job_case_id_index_exists():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'recovery_jobs';"))
        indexes = [row[0] for row in result]
        assert 'ix_recovery_jobs_case_id' in indexes, f"Index missing. Found: {indexes}"

def test_recovery_case_created_at_index_exists():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'recovery_cases';"))
        indexes = [row[0] for row in result]
        assert 'ix_recovery_cases_created_at' in indexes, f"Index missing. Found: {indexes}"

def test_recovery_attempt_case_id_index_exists():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'recovery_attempts';"))
        indexes = [row[0] for row in result]
        assert 'ix_recovery_attempts_case_id' in indexes, f"Index missing. Found: {indexes}"

def test_recovery_decision_case_id_index_exists():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'recovery_decisions';"))
        indexes = [row[0] for row in result]
        assert 'ix_recovery_decisions_case_id' in indexes, f"Index missing. Found: {indexes}"

def test_env_example_contains_no_real_openrouter_secret():
    import os
    env_example_path = os.path.join(os.path.dirname(__file__), "../../../.env.example")
    with open(env_example_path, "r") as f:
        content = f.read()
    
    assert "sk-or-v1-" not in content, "Real OpenRouter key found in .env.example!"
    assert "sk-" not in content, "Secret key found in .env.example!"
    assert "Bearer" not in content, "Bearer token found in .env.example!"
    assert "your-openrouter-api-key-here" in content, "Placeholder missing from .env.example!"
