"""AI model provider presets for OpenAI-compatible APIs."""


MODEL_PRESETS = [
    {
        "key": "openai",
        "name": "OpenAI",
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "recommended_models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
        "description": "适合通用写作、摘要、结构化分类和高稳定性的生产流程。",
        "extra_body_example": {},
        "key_env_names": ["OPENAI_API_KEY", "AI_API_KEY"],
    },
    {
        "key": "deepseek",
        "name": "DeepSeek",
        "provider": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "recommended_models": ["deepseek-chat", "deepseek-reasoner"],
        "description": "适合通用写作、摘要和分类；推理模型可通过 AI_EXTRA_BODY_JSON 透传参数。",
        "extra_body_example": {},
        "key_env_names": ["DEEPSEEK_API_KEY"],
    },
    {
        "key": "dashscope",
        "name": "通义百炼 / 阿里云百炼",
        "provider": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "recommended_models": ["qwen-plus", "qwen-max", "qwen-long"],
        "description": "国内团队接入稳定，长文和结构化任务可选 qwen-long/qwen-plus。",
        "extra_body_example": {},
        "key_env_names": ["DASHSCOPE_API_KEY", "QWEN_API_KEY", "ALIBABA_API_KEY"],
    },
    {
        "key": "zhipu",
        "name": "智谱 GLM",
        "provider": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "recommended_models": ["glm-4.6", "glm-4-plus"],
        "description": "适合中文写作和结构化任务，thinking 参数可通过 extra body 透传。",
        "extra_body_example": {},
        "key_env_names": ["ZHIPU_API_KEY", "GLM_API_KEY", "BIGMODEL_API_KEY"],
    },
    {
        "key": "kimi",
        "name": "Kimi / Moonshot",
        "provider": "openai_compatible",
        "base_url": "https://api.moonshot.ai/v1",
        "recommended_models": ["kimi-k2-0905-preview", "moonshot-v1-128k"],
        "description": "长上下文和资料消化体验较好，适合素材摘要和长文参考。",
        "extra_body_example": {},
        "key_env_names": ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
    },
    {
        "key": "doubao",
        "name": "火山方舟 / 豆包",
        "provider": "openai_compatible",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "recommended_models": ["doubao-seed-1-6-250615"],
        "description": "模型名通常使用方舟推理接入点，请在控制台复制后填入。",
        "extra_body_example": {},
        "key_env_names": ["ARK_API_KEY", "VOLCENGINE_API_KEY", "DOUBAO_API_KEY"],
    },
    {
        "key": "mimo",
        "name": "MiMo / Xiaomi MiMo",
        "provider": "openai_compatible",
        "base_url": "https://api.mimo-v2.com/v1",
        "recommended_models": ["mimo-v2-pro", "mimo-v2-flash", "mimo-v2-omni"],
        "description": "小米 MiMo 的 OpenAI 兼容接口，适合长上下文、推理和智能体类任务。",
        "extra_body_example": {"max_completion_tokens": 4096},
        "key_env_names": ["MIMO_API_KEY", "XIAOMI_API_KEY", "XIAOMI_MIMO_API_KEY"],
    },
    {
        "key": "custom",
        "name": "自定义 OpenAI-compatible",
        "provider": "openai_compatible",
        "base_url": "",
        "recommended_models": [],
        "description": "用于 OpenRouter、私有网关或其它兼容 /chat/completions 的服务。",
        "extra_body_example": {},
        "key_env_names": ["AI_API_KEY"],
    },
]


def model_presets() -> list[dict]:
    return MODEL_PRESETS


def find_model_preset(key: str | None) -> dict | None:
    key = (key or "").strip()
    return next((preset for preset in MODEL_PRESETS if preset["key"] == key), None)
