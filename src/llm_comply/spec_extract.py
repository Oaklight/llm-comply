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


def _composition_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect a schema node and its ``allOf``/``anyOf``/``oneOf`` members.

    Descending only through composition keywords keeps a ``required`` rewrite
    scoped to the schema itself; walking nested ``properties`` would let an
    entry naming a common field silently strip it from child objects.
    """
    found: list[dict[str, Any]] = [node]
    for keyword in ("allOf", "anyOf", "oneOf"):
        members = node.get(keyword)
        if not isinstance(members, list):
            continue
        for member in members:
            if isinstance(member, dict):
                found.extend(_composition_nodes(member))
    return found


# Fields the OpenAI OpenAPI document marks required but the production
# Responses API omits unless the account has the feature enabled. Keeping them
# required would reject valid production responses after every refresh.
PRODUCTION_OPTIONAL_FIELDS: dict[str, frozenset[str]] = {
    "Response": frozenset({"access_programs"}),
    # Present upstream but not in the bundled subset today; keeping the entry
    # means the same relaxation applies if beta schemas ever enter it.
    "BetaResponse": frozenset({"access_programs"}),
}


def relax_production_required(spec: dict[str, Any]) -> dict[str, Any]:
    """Drop known production-omitted fields from ``required`` arrays.

    Args:
        spec: An OpenAPI document (modified in place).

    Returns:
        The same document, for call chaining.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    for name, fields in PRODUCTION_OPTIONAL_FIELDS.items():
        schema = schemas.get(name)
        if not isinstance(schema, dict):
            continue
        for node in _composition_nodes(schema):
            required = node.get("required")
            if not isinstance(required, list):
                continue
            remaining = [item for item in required if item not in fields]
            if remaining:
                node["required"] = remaining
            else:
                node.pop("required")
    return spec


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
    return relax_production_required(subset)
