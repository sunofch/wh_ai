from src.common.prompts import load_prompts


def test_load_prompts_has_required_keys():
    prompts = load_prompts()
    assert "qwen2" in prompts
    assert "qwen35" in prompts


def test_load_prompts_system_is_nonempty_string():
    prompts = load_prompts()
    assert isinstance(prompts["qwen2"]["system"], str)
    assert len(prompts["qwen2"]["system"].strip()) > 0
    assert isinstance(prompts["qwen35"]["system"], str)
    assert len(prompts["qwen35"]["system"].strip()) > 0


def test_load_prompts_format_prefix_is_nonempty_string():
    prompts = load_prompts()
    assert isinstance(prompts["qwen2"]["format_prefix"], str)
    assert len(prompts["qwen2"]["format_prefix"].strip()) > 0
    assert isinstance(prompts["qwen35"]["format_prefix"], str)
    assert len(prompts["qwen35"]["format_prefix"].strip()) > 0


def test_load_prompts_is_cached():
    assert load_prompts() is load_prompts()
