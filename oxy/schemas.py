"""
OXY Schemas — Schema normalization for outgoing LLM definitions and argument coercion.

Handles provider discrepancies across OpenAI, DeepSeek, Anthropic, Bedrock, and Ollama:
  1. Outgoing Sanitizer: Flattens nullable unions, strips invalid combinators ($ref siblings,
     top-level anyOf/allOf), and enforces property key constraints.
  2. Incoming Coercer: Auto-corrects common LLM JSON hallucinations before tool dispatch
     (stringified numbers, stringified booleans, nested JSON strings, scalar-to-array).
"""

from __future__ import annotations

import json
import re
from typing import Any


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Outgoing Schema Sanitizer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def sanitize_schema_node(node: Any) -> Any:
    """Recursively sanitize a JSON Schema node for cross-provider compatibility."""
    if not isinstance(node, dict):
        if isinstance(node, list):
            return [sanitize_schema_node(item) for item in node]
        return node

    sanitized = {}

    # Handle nullable unions: {"anyOf": [{"type": "string"}, {"type": "null"}]}
    for union_key in ("anyOf", "oneOf"):
        if union_key in node and isinstance(node[union_key], list):
            branches = node[union_key]
            null_branch = any(isinstance(b, dict) and b.get("type") == "null" for b in branches)
            non_null = [b for b in branches if not (isinstance(b, dict) and b.get("type") == "null")]

            if null_branch and len(non_null) == 1 and isinstance(non_null[0], dict):
                # Flatten into single nullable type
                merged = sanitize_schema_node(non_null[0])
                merged["nullable"] = True
                return merged

    for key, value in node.items():
        # Strip default beside $ref
        if key == "default" and "$ref" in node:
            continue

        # Recursively sanitize nested structures
        if key == "properties" and isinstance(value, dict):
            clean_props = {}
            for prop_name, prop_def in value.items():
                # Sanitize property name to valid identifier
                clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', prop_name)[:64]
                clean_props[clean_name] = sanitize_schema_node(prop_def)
            sanitized["properties"] = clean_props
        elif isinstance(value, (dict, list)):
            sanitized[key] = sanitize_schema_node(value)
        else:
            sanitized[key] = value

    return sanitized


def sanitize_tool_definition(tool_def: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a full OpenAI tool definition dictionary."""
    clean = tool_def.copy()
    if "function" in clean and isinstance(clean["function"], dict):
        fn = clean["function"].copy()
        if "parameters" in fn and isinstance(fn["parameters"], dict):
            fn["parameters"] = sanitize_schema_node(fn["parameters"])
        clean["function"] = fn
    return clean


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Incoming Argument Coercer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_raw_arguments(raw_args: str | dict[str, Any]) -> dict[str, Any]:
    """Safely parse raw tool arguments into a dictionary."""
    if isinstance(raw_args, dict):
        return raw_args
    if not raw_args or not isinstance(raw_args, str):
        return {}

    raw_args = raw_args.strip()
    if not raw_args:
        return {}

    try:
        return json.loads(raw_args)
    except json.JSONDecodeError:
        # Fallback 1: repair unescaped newlines in strings
        try:
            repaired = re.sub(r'(?<!\\)\n', r'\\n', raw_args)
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Fallback 2: trailing comma cleanup
        try:
            repaired = re.sub(r',\s*([}\]])', r'\1', raw_args)
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Fallback 3: Python dict syntax (single quotes from local models)
        try:
            import ast
            val = ast.literal_eval(raw_args)
            if isinstance(val, dict):
                return val
        except Exception:
            pass

        return {"_raw": raw_args}


def coerce_tool_arguments(
    raw_args: str | dict[str, Any],
    param_schema: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Coerce malformed model argument outputs into target schema types."""
    parsed = parse_raw_arguments(raw_args)
    if not param_schema or not isinstance(param_schema, dict):
        return parsed

    props = param_schema.get("properties", {})
    if not isinstance(props, dict):
        return parsed

    coerced = {}
    for key, val in parsed.items():
        if key not in props or not isinstance(props[key], dict):
            coerced[key] = val
            continue

        target_type = props[key].get("type")

        # 1. String to integer / float
        if target_type == "integer" and isinstance(val, str):
            try:
                coerced[key] = int(val.strip())
                continue
            except (ValueError, TypeError):
                pass
        elif target_type == "number" and isinstance(val, str):
            try:
                coerced[key] = float(val.strip())
                continue
            except (ValueError, TypeError):
                pass

        # 2. String to boolean
        elif target_type == "boolean" and isinstance(val, str):
            lower = val.strip().lower()
            if lower in ("true", "1", "yes"):
                coerced[key] = True
                continue
            elif lower in ("false", "0", "no"):
                coerced[key] = False
                continue

        # 3. String to list (if passed as JSON-encoded array)
        elif target_type == "array":
            if isinstance(val, str):
                val_stripped = val.strip()
                if val_stripped.startswith("[") and val_stripped.endswith("]"):
                    try:
                        coerced[key] = json.loads(val_stripped)
                        continue
                    except Exception:
                        pass
                # Wrap bare scalar into single-element array
                coerced[key] = [val]
                continue
            elif not isinstance(val, list):
                coerced[key] = [val]
                continue

        # 4. String to object (if passed as JSON-encoded object)
        elif target_type == "object" and isinstance(val, str):
            val_stripped = val.strip()
            if val_stripped.startswith("{") and val_stripped.endswith("}"):
                try:
                    coerced[key] = json.loads(val_stripped)
                    continue
                except Exception:
                    pass

        coerced[key] = val

    return coerced
