KB_MISS_MODE_KB_ONLY = "kb_only"
KB_MISS_MODE_AI_ASSIST = "ai_assist"

KB_MISS_MODE_LABELS = {
    KB_MISS_MODE_KB_ONLY: "Только база знаний",
    KB_MISS_MODE_AI_ASSIST: "ИИ отвечает, если в БЗ нет",
}


def label_for_mode(mode: str) -> str:
    return KB_MISS_MODE_LABELS.get(mode, mode)
