"""AI model provider presets for China-friendly OpenAI-compatible APIs."""


MODEL_PRESETS = [
    {
        "key": "deepseek",
        "name": "DeepSeek",
        "provider": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "recommended_models": ["deepseek-chat", "deepseek-reasoner"],
        "description": "适合通用写作、摘要和分类；推理模型可通过 AI_EXTRA_BODY_JSON 透传参数。",
        "extra_body_example": {},
    },
    {
        "key": "dashscope",
        "name": "通义百炼 / 阿里云百炼",
        "provider": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "recommended_models": ["qwen-plus", "qwen-max", "qwen-long"],
        "description": "国内团队接入稳定，长文和结构化任务可选 qwen-long/qwen-plus。",
        "extra_body_example": {},
    },
    {
        "key": "zhipu",
        "name": "智谱 GLM",
        "provider": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "recommended_models": ["glm-4.6", "glm-4-plus"],
        "description": "适合中文写作和结构化任务，thinking 参数可通过 extra body 透传。",
        "extra_body_example": {},
    },
    {
        "key": "kimi",
        "name": "Kimi / Moonshot",
        "provider": "openai_compatible",
        "base_url": "https://api.moonshot.ai/v1",
        "recommended_models": ["kimi-k2-0905-preview", "moonshot-v1-128k"],
        "description": "长上下文和资料消化体验较好，适合素材摘要和长文参考。",
        "extra_body_example": {},
    },
    {
        "key": "doubao",
        "name": "火山方舟 / 豆包",
        "provider": "openai_compatible",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "recommended_models": ["doubao-seed-1-6-250615"],
        "description": "模型名通常使用方舟推理接入点，请在控制台复制后填入。",
        "extra_body_example": {},
    },
    {
        "key": "custom",
        "name": "自定义 OpenAI-compatible",
        "provider": "openai_compatible",
        "base_url": "",
        "recommended_models": [],
        "description": "用于 OpenRouter、私有网关或其它兼容 /chat/completions 的服务。",
        "extra_body_example": {},
    },
]


def model_presets() -> list[dict]:
    return MODEL_PRESETS
