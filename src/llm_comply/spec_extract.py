"""Extract format-specific subsets from upstream OpenAPI documents."""

from __future__ import annotations

from typing import Any


def _refs_in(node: Any) -> list[str]:
    """Collect every ``$ref`` string in a JSON value."""
    refs: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(_refs_in(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(_refs_in(item))
    return refs


def extract_openai_responses(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the OpenAI Responses API subset of the full OpenAI spec.

    OpenAI publishes Chat Completions and Responses in one OpenAPI document.
    Keeping only the ``/responses*`` paths and their transitive component
    references avoids shipping a second copy of the full document.

    Args:
        spec: The full OpenAI OpenAPI document.

    Raises:
        ValueError: If the document has no ``/responses`` paths or contains an
            unresolvable component reference.

    Returns:
        A self-contained OpenAPI document for the Responses API.
    """
    paths = {
        path: item
        for path, item in spec.get("paths", {}).items()
        if path.startswith("/responses") and "?" not in path
    }
    if not paths:
        raise ValueError("OpenAI spec has no /responses paths")

    components = spec.get("components", {})
    kept: dict[str, dict[str, Any]] = {section: {} for section in components}

    pending = _refs_in(paths)
    while pending:
        ref = pending.pop()
        if not ref.startswith("#/components/"):
            continue
        parts = ref.split("/")
        if len(parts) != 4:
            continue
        _, _, section, name = parts
        if name in kept.setdefault(section, {}):
            continue
        target = components.get(section, {}).get(name)
        if target is None:
            raise ValueError(f"unresolved $ref in OpenAI spec: {ref}")
        kept[section][name] = target
        pending.extend(_refs_in(target))

    subset: dict[str, Any] = {
        "openapi": spec.get("openapi", "3.1.0"),
        "info": dict(spec.get("info", {})),
        "paths": paths,
        "components": {section: items for section, items in kept.items() if items},
    }
    for key in ("servers", "security"):
        if key in spec:
            subset[key] = spec[key]
    if "security" in spec:
        # Security requirements reference schemes by name, and those are not
        # reachable through ``$ref``; copy them so the subset stays
        # self-contained.
        kept.setdefault("securitySchemes", {}).update(
            components.get("securitySchemes", {})
        )
        subset["components"] = {
            section: items for section, items in kept.items() if items
        }
    subset["info"]["x-llm-comply-subset"] = "OpenAI Responses API"
    return subset
