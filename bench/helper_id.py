#!/usr/bin/env python3
"""Print the helper node id an oMLX server keeps for one of its models.

Usage:
    python3 bench/helper_id.py --base-url http://127.0.0.1:8004 \
        --settings ~/.omlx/settings.json --model my-model

The helper id is a per-model setting the server holds, named `prefill_helper_node_id`, and a runner
needs it as `--helper-node`. This command reads it through the same admin client the runners use
(bench/client.py), so the API calls live in one place.

The settings file given to `--settings` is read for the API key only. It is not where the id lives.

With no `--model`, the command lists every model the server holds and says whether each one has a
helper id. A model with none has not been paired with a Spark yet, and pairing is done in oMLX.

Exit codes: 0 the id was printed, or the model list was read; 1 no helper id is set for the model
asked for; 2 the server could not be read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, TextIO

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bench.client import OMLXClient, load_api_key  # noqa: E402

# The per-model setting that holds the id of the Spark paired with the model.
HELPER_ID_FIELD = "prefill_helper_node_id"
# How much of an id the model list shows, so a terminal log never carries a whole one.
ID_HINT_CHARS = 4
# What a model with no id means, in the words the run guide uses.
NOT_PAIRED = "no helper id set for {model}: pair the Spark in oMLX first"


class ModelReader(Protocol):
    """The two reads this command needs; `bench.client.OMLXClient` is one, a test stub is another."""

    def list_models(self) -> List[Dict[str, Any]]:
        ...

    def get_model_settings(self, model: str) -> Dict[str, Any]:
        ...


def helper_id_of(settings: Dict[str, Any]) -> str:
    """The helper id in one model's settings; an empty string when none is set."""
    value = settings.get(HELPER_ID_FIELD)
    if not isinstance(value, str):
        return ""
    return value.strip()


def model_names(client: ModelReader) -> List[str]:
    """Every model id the server lists, in the order it gives them."""
    names: List[str] = []
    for entry in client.list_models():
        if not isinstance(entry, dict):
            continue
        name = entry.get("id") or entry.get("model_id") or entry.get("name")
        if name:
            names.append(str(name))
    return names


def print_model_list(client: ModelReader, out: TextIO) -> int:
    """One line per model: whether it has a helper id, and the first characters of it."""
    names = model_names(client)
    if not names:
        print("the server lists no models", file=out)
        return 0
    found = 0
    for name in names:
        helper = helper_id_of(client.get_model_settings(name))
        if helper:
            found += 1
            print(f"{name}: helper id set, starts {helper[:ID_HINT_CHARS]}", file=out)
        else:
            print(f"{name}: no helper id set", file=out)
    if not found:
        print("no model here has a helper id: pair the Spark in oMLX first", file=out)
    return 0


def print_helper_id(client: ModelReader, model: str, out: TextIO) -> int:
    """The id for one model, or a plain message and a failure when there is none."""
    helper = helper_id_of(client.get_model_settings(model))
    if not helper:
        print(NOT_PAIRED.format(model=model), file=out)
        return 1
    print(helper, file=out)
    return 0


def build_client(base_url: str, settings_path: str) -> OMLXClient:
    """A logged-in admin client, with the key read from the settings file."""
    client = OMLXClient(base_url, load_api_key(settings_path))
    client.login()
    return client


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print the helper node id your oMLX server keeps for a model",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="oMLX admin base URL, such as http://127.0.0.1:8004",
    )
    parser.add_argument(
        "--settings",
        required=True,
        help="oMLX settings.json path, read for the API key only",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="model id; with no --model, list every model the server holds",
    )
    args = parser.parse_args(argv)

    # Every call to the server sits inside this block: the model reads fail the same way login
    # does (no connection, an error answer, a body that is not JSON), and a traceback would read as
    # "the model has no helper id" to anyone who only looks at the exit code. The reason printed is
    # the exception's own text: the API key is never in it.
    try:
        client = build_client(args.base_url, args.settings)
        if args.model:
            return print_helper_id(client, args.model, sys.stdout)
        return print_model_list(client, sys.stdout)
    except (OSError, ValueError) as exc:
        print(f"could not read the server: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
