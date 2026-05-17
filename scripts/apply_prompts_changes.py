"""Apply safe text replacements to prompts.py for instruction intent extension."""
import pathlib

f = pathlib.Path('app/services/prompts.py')
content = f.read_text('utf-8')

changes = []

# 1. Add theme catch-all pattern to _INSTRUCTION_INTENT_PATTERNS
old1 = '''    # --- style ---
    (r"(?:更|偏).{0,4}(?:简约|简洁|极简)", "style:minimal",
     "整体风格偏极简高端，减少装饰元素，突出产品本身。"),
    (r"(?:更|偏).{0,4}(?:高级|高端|品质感|质感)", "style:premium",
     "整体调性偏高端简约，参考杂志级电商摄影质感。"),
]'''
new1 = '''    # --- style ---
    (r"(?:更|偏).{0,4}(?:简约|简洁|极简)", "style:minimal",
     "整体风格偏极简高端，减少装饰元素，突出产品本身。"),
    (r"(?:更|偏).{0,4}(?:高级|高端|品质感|质感)", "style:premium",
     "整体调性偏高端简约，参考杂志级电商摄影质感。"),
    # --- theme / directional (catch-all, must be last) ---
    (r".+", "theme:direction", ""),
]'''
assert old1 in content, "Change 1: old string not found"
content = content.replace(old1, new1)
changes.append("1. theme:direction pattern")

# 2. Update _parse_instruction_intents
old2 = '''def _parse_instruction_intents(instruction: str | None) -> list[tuple[str, str]]:
    """Parse user instruction into (intent_key, directive) pairs."""
    cleaned = _clean_text(instruction)
    if not cleaned:
        return []
    results: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for pattern, intent_key, directive in _INSTRUCTION_INTENT_PATTERNS:
        if intent_key in seen_keys:
            continue
        if re.search(pattern, cleaned):
            results.append((intent_key, directive))
            seen_keys.add(intent_key)
    return results'''
new2 = '''def _parse_instruction_intents(instruction: str | None) -> list[tuple[str, str]]:
    """Parse user instruction into (intent_key, directive) pairs."""
    cleaned = _clean_text(instruction)
    if not cleaned:
        return []
    results: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    has_structural_intent = False
    for pattern, intent_key, directive in _INSTRUCTION_INTENT_PATTERNS:
        if intent_key in seen_keys:
            continue
        if not re.search(pattern, cleaned):
            continue
        # theme:direction is the catch-all; skip if structural intents already matched
        if intent_key == "theme:direction":
            if has_structural_intent:
                continue
            results.append((intent_key, cleaned))
            seen_keys.add(intent_key)
            continue
        results.append((intent_key, directive))
        seen_keys.add(intent_key)
        has_structural_intent = True
    return results'''
assert old2 in content, "Change 2: old string not found"
content = content.replace(old2, new2)
changes.append("2. _parse_instruction_intents")

# 3. Update _apply_instruction_overrides signature and add theme handling
old3 = '''def _apply_instruction_overrides(
    blocks: dict[str, str],
    intents: list[tuple[str, str]],
    instruction: str | None,
) -> dict[str, str]:
    """Apply parsed intents to override prompt blocks. Returns modified blocks."""
    blocks = dict(blocks)
    extra_constraints: list[str] = []
    for intent_key, directive in intents:
        category, _ = intent_key.split(":", 1)
        if category == "background" and directive:
            blocks["background"] = directive
        elif category == "text_policy":
            # Text policy changes are conveyed as constraints
            extra_constraints.append(directive)
        elif category == "color" and directive:
            extra_constraints.append(directive)
        elif category == "composition" and directive:
            extra_constraints.append(directive)
        elif category == "style" and directive:
            extra_constraints.append(directive)'''
new3 = '''def _apply_instruction_overrides(
    blocks: dict[str, str],
    intents: list[tuple[str, str]],
    instruction: str | None,
    copy_blocks: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Apply parsed intents to override prompt blocks. Returns modified blocks."""
    blocks = dict(blocks)
    extra_constraints: list[str] = []
    for intent_key, directive in intents:
        category, _ = intent_key.split(":", 1)
        if category == "background" and directive:
            blocks["background"] = directive
        elif category == "text_policy":
            extra_constraints.append(directive)
        elif category == "color" and directive:
            extra_constraints.append(directive)
        elif category == "composition" and directive:
            extra_constraints.append(directive)
        elif category == "style" and directive:
            extra_constraints.append(directive)
        elif category == "theme" and directive:
            blocks["goal"] = "围绕\\u201c" + directive + "\\u201d这一主题，" + blocks.get("goal", "")
            subject = blocks.get("subject", "")
            if subject:
                blocks["subject"] = subject + "。本图需突出\\u201c" + directive + "\\u201d使用场景及对应卖点"
            extra_constraints.append("所有可见文案和视觉元素必须围绕\\u201c" + directive + "\\u201d主题展开，不要使用通用化、泛品类措辞")
            if copy_blocks is not None:
                headline = str(copy_blocks.get("headline") or "")
                if headline and directive not in headline:
                    copy_blocks["headline"] = "【" + directive + "】" + headline
                elif not headline:
                    copy_blocks["headline"] = directive'''
assert old3 in content, "Change 3: old string not found"
content = content.replace(old3, new3)
changes.append("3. _apply_instruction_overrides")

# 4. Update compose_prompt call to pass copy_blocks
old4 = '''    instruction_intents = _parse_instruction_intents(instruction)
    if instruction_intents:
        blocks = _apply_instruction_overrides(blocks, instruction_intents, instruction)'''
new4 = '''    instruction_intents = _parse_instruction_intents(instruction)
    if instruction_intents:
        blocks = _apply_instruction_overrides(blocks, instruction_intents, instruction, copy_blocks=copy_blocks)'''
assert old4 in content, "Change 4: old string not found"
content = content.replace(old4, new4)
changes.append("4. compose_prompt call")

f.write_text(content, 'utf-8')
for c in changes:
    print(c)
print("ALL DONE - %d changes applied" % len(changes))
