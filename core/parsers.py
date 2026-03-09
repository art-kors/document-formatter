# parsers.py
import re
from typing import Dict, List


def simple_text_parser(text: str) -> Dict:
    """
    Простая эвристика для разбора текста инструкции на секции и правила.
    В реальном проекте здесь стоит использовать NLP или LLM.
    """
    lines = text.split('\n')
    sections = []
    rules = []

    current_section = None
    current_content = []

    # Паттерны для поиска заголовков (например: "1. Введение", "Глава 1")
    section_pattern = re.compile(r'^\s*(\d+\.\s+[А-Яа-яA-Za-z]+|Глава\s+\d+|Раздел\s+\d+)')
    # Паттерн для правил (например: "- Правило...", "1.1. Требование...")
    rule_pattern = re.compile(r'^\s*[-\d]\s*[\.\)]\s+')

    for line in lines:
        line = line.strip()
        if not line: continue

        if section_pattern.match(line):
            # Сохраняем предыдущую секцию
            if current_section:
                current_section['content'] = current_content
                sections.append(current_section)

            current_section = {'title': line, 'content': []}
            current_content = []
        elif rule_pattern.match(line):
            rules.append(line)
            if current_section:
                current_content.append(line)
        else:
            # Просто текст
            if current_section:
                current_content.append(line)

    if current_section:
        current_section['content'] = current_content
        sections.append(current_section)

    # Если явных секций не найдено, создаем одну общую
    if not sections:
        sections.append({'title': 'Общие положения', 'content': [text]})

    return {
        'sections': sections,
        'rules': rules
    }