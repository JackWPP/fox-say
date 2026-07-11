"""Test embedding with different inputs and parameters."""
from openai import OpenAI
from app.core.config import settings

client = OpenAI(api_key=settings.embedding_api_key, base_url=settings.embedding_api_base, max_retries=0)

# Test 1: simple English
try:
    r = client.embeddings.create(model=settings.embedding_model, input=["test"])
    print(f"Test 1 (English, no dimensions): OK dim={len(r.data[0].embedding)}")
except Exception as e:
    print(f"Test 1 FAILED: {e}")

# Test 2: simple Chinese
try:
    r = client.embeddings.create(model=settings.embedding_model, input=["线性代数"])
    print(f"Test 2 (Chinese, no dimensions): OK dim={len(r.data[0].embedding)}")
except Exception as e:
    print(f"Test 2 FAILED: {e}")

# Test 3: with dimensions=1024
try:
    r = client.embeddings.create(model=settings.embedding_model, input=["test"], dimensions=1024)
    print(f"Test 3 (dimensions=1024): OK dim={len(r.data[0].embedding)}")
except Exception as e:
    print(f"Test 3 FAILED: {e}")

# Test 4: batch of 2
try:
    r = client.embeddings.create(model=settings.embedding_model, input=["test", "线性代数"])
    print(f"Test 4 (batch 2): OK dim={len(r.data[0].embedding)}")
except Exception as e:
    print(f"Test 4 FAILED: {e}")

# Test 5: with LaTeX
try:
    r = client.embeddings.create(model=settings.embedding_model, input=["n阶行列式等于 $\\mu^2$ 的元素"])
    print(f"Test 5 (LaTeX): OK dim={len(r.data[0].embedding)}")
except Exception as e:
    print(f"Test 5 FAILED: {e}")

# Test 6: without dimensions param
try:
    r = client.embeddings.create(model=settings.embedding_model, input=["test", "线性代数", "n阶行列式"])
    print(f"Test 6 (batch 3, no dims): OK dim={len(r.data[0].embedding)}")
except Exception as e:
    print(f"Test 6 FAILED: {e}")
