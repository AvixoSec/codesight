MODEL_PRICES = {
    "gpt-5.4":           (2.50, 10.00),
    "gpt-5.3-codex":     (1.50,  6.00),
    "o3-mini":           (1.10,  4.40),
    "claude-opus-4-6-20251101":  (15.00, 75.00),
    "claude-sonnet-4-6-20251101": (3.00, 15.00),
    "gemini-3.1-pro":    (1.25,  5.00),
    "gemini-3.1-flash":  (0.075, 0.30),
    "llama3":            (0.0, 0.0),
    "llama3.1":          (0.0, 0.0),
    "codellama":         (0.0, 0.0),
    "mistral":           (0.0, 0.0),
    "deepseek-coder":    (0.0, 0.0),
    "qwen2.5-coder":     (0.0, 0.0),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prices = MODEL_PRICES.get(model)
    if prices is None:
        for key, val in MODEL_PRICES.items():
            if key in model or model in key:
                prices = val
                break
    if prices is None:
        return 0.0
    input_price, output_price = prices
    cost = (
        (prompt_tokens / 1_000_000) * input_price
        + (completion_tokens / 1_000_000) * output_price
    )
    return round(cost, 6)


def format_cost(cost: float) -> str:
    if cost == 0.0:
        return "free (local)"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"
