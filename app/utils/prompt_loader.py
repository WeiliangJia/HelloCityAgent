"""
Prompt Loader Utility

Centralized prompt loading from prompts/ directory.
Supports hot-reload in development mode.
"""

from pathlib import Path
from typing import Optional


def load_prompt(name: str, encoding: str = "utf-8") -> str:
    """
    Load a prompt from the prompts/ directory.

    Args:
        name: Prompt filename without extension (e.g., "chatbot" for "chatbot.txt")
        encoding: File encoding, defaults to "utf-8"

    Returns:
        str: The prompt content

    Raises:
        FileNotFoundError: If the prompt file doesn't exist

    Examples:
        >>> chatbot_prompt = load_prompt("chatbot")
        >>> generator_prompt = load_prompt("checklist_generator")
    """
    # Navigate from app/utils/ to project root
    prompts_dir = Path(__file__).parent.parent.parent / "prompts"
    prompt_file = prompts_dir / f"{name}.txt"

    if not prompt_file.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_file}\n"
            f"Available prompts: {list_available_prompts()}"
        )

    return prompt_file.read_text(encoding=encoding).strip()


def list_available_prompts() -> list[str]:
    """
    List all available prompt files in the prompts/ directory.

    Returns:
        list[str]: List of prompt names (without .txt extension)

    Examples:
        >>> prompts = list_available_prompts()
        >>> print(prompts)
        ['chatbot', 'checklist_generator', 'checklist_converter', 'websearch']
    """
    prompts_dir = Path(__file__).parent.parent.parent / "prompts"

    if not prompts_dir.exists():
        return []

    return [
        p.stem for p in prompts_dir.glob("*.txt")
        if p.is_file() and not p.name.startswith("_")
    ]


def get_prompt_path(name: str) -> Path:
    """
    Get the full path to a prompt file.

    Args:
        name: Prompt filename without extension

    Returns:
        Path: Full path to the prompt file

    Examples:
        >>> path = get_prompt_path("chatbot")
        >>> print(path)
        PosixPath('/path/to/hello-city-service-ai/prompts/chatbot.txt')
    """
    prompts_dir = Path(__file__).parent.parent.parent / "prompts"
    return prompts_dir / f"{name}.txt"
