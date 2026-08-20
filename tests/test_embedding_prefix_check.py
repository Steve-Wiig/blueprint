import sys
import subprocess
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.embedding_prefix_check import (
    EmbeddingService,
    fake_encode,
    REQUIRED_DOC_PREFIX,
    REQUIRED_QUERY_PREFIX,
    REQUIRED_DIM,
    calls
)

@pytest.fixture(autouse=True)
def clear_calls():
    calls.clear()

def test_embedding_service_logic():
    svc = EmbeddingService(fake_encode)
    
    doc_text = "test doc"
    query_text = "test query"
    
    doc_vec = svc.embed_document(doc_text)
    query_vec = svc.embed_query(query_text)
    
    assert len(doc_vec) == REQUIRED_DIM
    assert len(query_vec) == REQUIRED_DIM
    assert calls[0] == REQUIRED_DOC_PREFIX + doc_text
    assert calls[1] == REQUIRED_QUERY_PREFIX + query_text

def test_fake_encode_output():
    text = "hello"
    result = fake_encode(text)
    assert len(result) == REQUIRED_DIM
    assert all(isinstance(x, float) for x in result)
    assert calls[-1] == text

def test_cli_execution():
    tool_path = Path(__file__).parent.parent / "tools" / "embedding_prefix_check.py"
    
    # The main() function in the module prints success and returns 0
    result = subprocess.run(
        [sys.executable, str(tool_path)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "PASS" in result.stdout

def test_cli_dry_run_flag():
    tool_path = Path(__file__).parent.parent / "tools" / "embedding_prefix_check.py"
    
    # Testing that the script accepts the --dry-run flag defined in the source
    result = subprocess.run(
        [sys.executable, str(tool_path), "--dry-run"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "PASS" in result.stdout