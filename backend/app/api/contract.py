"""What each route declares it may send, built from the code that sends it (stress test, 2026-10-30, tools 2 / K62).

openapi.json declared none of the API's own errors, not the 200 a create-or-hold route answers with the record it
already held, a 422 as a list where the API's own refusals send a string, and the evidence pack, the event stream, the
memo's Word file and the values CSV as JSON or plain text. The declarations are made here, from the primitives:

- an error status from the WorkbenchError subclass that raises it (errors.py), its description from the class's own
  docstring, so a class's status is never restated by hand; every error body is ErrorOut, whose detail is a sentence
  (the API's own) or FastAPI's list of what failed validation;
- GATED for every route behind the gate (a missing session, another origin, a public visitor at an owner's tool, and
  the door's bound on a network's requests in flight, api/in_flight.py), WRITES for the routes the writes limits guard;
- held_or_created for the six routes that hand back the record already held with 200;
- the real media type of every route that sends something other than JSON (media).
"""

from __future__ import annotations

from typing import Any

from ..errors import AccessRequired, Busy, Conflict, Forbidden, InvalidInput, NotFound, Paused, TooLarge, TooManyRequests, WorkbenchError
from ..schemas import ErrorOut

Responses = dict[int | str, dict[str, Any]]

# The classes errors.py leaves without a docstring of their own, said once here.
_SAID = {
    NotFound: "The record does not exist, or this workspace may not read it: the two are answered alike.",
    Forbidden: "The request did not come from the workbench's own pages, or asks to change a curated record.",
    TooLarge: "The body or the file is larger than the route takes.",
    TooManyRequests: "A bound on how often was reached; Retry-After says when it lifts.",
}


def _said(kind: type[WorkbenchError]) -> str:
    own = _SAID.get(kind) or (kind.__doc__ or "").strip()
    return " ".join(own.split()) or kind.__name__


def error_responses(*kinds: type[WorkbenchError]) -> Responses:
    """One declared response per status the given classes raise, ErrorOut each, with every class's sentence."""
    declared: Responses = {}
    for kind in kinds:
        held = declared.get(kind.status_code)
        sentence = f"{kind.__name__}: {_said(kind)}"
        declared[kind.status_code] = {"model": ErrorOut, "description": f"{held['description']} {sentence}" if held else sentence}
    return declared


def merged(*parts: Responses) -> Responses:
    """Responses declared in parts, a status declared twice with both descriptions."""
    out: Responses = {}
    for part in parts:
        for code, response in part.items():
            if code in out and "description" in out[code] and "description" in response and response["description"] not in out[code]["description"]:
                out[code] = {**out[code], **response, "description": f"{out[code]['description']} {response['description']}"}
            else:
                out[code] = {**out.get(code, {}), **response}
    return out


# Every gated route: no session (401), another origin or an owner's tool (403), the door's bound on a network's
# requests in flight in the public store (503, api/in_flight.py).
GATED = error_responses(AccessRequired, Forbidden, Busy)
# A route the writes limits guard (api/access.limit_public_writes, limit_run_starts): the hourly bounds, the owner's
# pause and the disk, the store's write lock; and a body past its bound (api/body_limit.py).
WRITES = error_responses(TooManyRequests, Paused, Busy, TooLarge)
# The API's own refusal of what was sent (a sentence), or FastAPI's of the body's shape (a list): both ErrorOut.
INVALID = error_responses(InvalidInput)
FOUND = error_responses(NotFound)
CONFLICT = error_responses(Conflict)


def held_or_created(model: type[Any]) -> Responses:
    """The 200 of a create-or-hold route: the record already held, unchanged, in the same shape as the one created."""
    return {200: {"model": model, "description": "Already held: the record these inputs name, unchanged; nothing was written."}}


def media(media_type: str, description: str, schema: dict[str, Any] | None = None) -> Responses:
    """A 200 that is not JSON, declared as what it is."""
    return {200: {"description": description, "content": {media_type: {"schema": schema or {"type": "string", "format": "binary"}}}}}
