import json
from typing import Dict

def load_lexicon(language: str = 'ru') -> Dict:
    """Загружает тексты из файла JSON."""
    try:
        with open(f'src/locales/{language}.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback to default language if requested language file is not found
        print(f"Warning: Lexicon file for language '{language}' not found. Loading 'ru.json' instead.")
        with open('src/locales/ru.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding lexicon JSON for language '{language}': {e}")
        # In a real application, you might want to raise an error or handle this more gracefully
        return {} # Return empty dict on error

# Load the lexicon when this module is imported
lexicon: Dict = load_lexicon()

# You can also add a function to get text safely
def get_text(key: str, default: str = "", **kwargs) -> str:
    parts = key.split('.')
    current = lexicon
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default # Key not found

    if isinstance(current, str):
        return current.format(**kwargs)
    return default
