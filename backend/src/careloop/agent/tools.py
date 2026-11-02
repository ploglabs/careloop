"""Tool definitions shared by the text loop (OpenAI format) and the voice pipeline (Pipecat)."""

from typing import Any

from careloop.languages import LANGUAGES

LEVELS = ["REVIEW", "URGENT", "EMERGENCY"]

# name -> (description, properties, required)
TOOL_SPECS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "record_consent": (
        "Record whether the patient agreed to continue after the consent message.",
        {"granted": {"type": "boolean"}},
        ["granted"],
    ),
    "record_answer": (
        "Store the patient's answer to one checklist question as a typed value. Use status 'declined' if they "
        "won't answer, 'unclear' if you could not understand after asking twice.",
        {
            "key": {"type": "string", "description": "Question key from the checklist"},
            "value": {"description": "Normalised value: enum option, number, true/false, or short text"},
            "status": {"type": "string", "enum": ["answered", "declined", "unclear"]},
            "confidence": {"type": "number", "description": "0 to 1"},
            "evidence_quote": {"type": "string", "description": "The patient's exact words"},
        },
        ["key", "status", "evidence_quote"],
    ),
    "escalate": (
        "Flag something concerning the patient said that is not covered by a checklist question.",
        {
            "level": {"type": "string", "enum": LEVELS},
            "reason": {"type": "string"},
            "evidence_quote": {"type": "string"},
        },
        ["level", "reason", "evidence_quote"],
    ),
    "check_slots": (
        "Find up to 3 free appointment slots, with the same doctor by default.",
        {
            "preferred_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
            "specialty": {"type": "string", "description": "Only when routing to a different department"},
        },
        [],
    ),
    "book_slot": (
        "Book a slot after the patient confirmed the read-back.",
        {"slot_id": {"type": "integer"}, "reason": {"type": "string"}},
        ["slot_id"],
    ),
    "list_appointments": ("List the patient's upcoming appointments.", {}, []),
    "reschedule": (
        "Move an existing appointment to a new slot after the patient confirmed.",
        {"appointment_id": {"type": "integer"}, "new_slot_id": {"type": "integer"}},
        ["appointment_id", "new_slot_id"],
    ),
    "cancel_appointment": (
        "Cancel an existing appointment after the patient confirmed.",
        {"appointment_id": {"type": "integer"}},
        ["appointment_id"],
    ),
    "suggest_department": (
        "Use when the patient reports a problem that doesn't belong to the original specialty.",
        {"complaint": {"type": "string"}},
        ["complaint"],
    ),
    "record_medication": (
        "Record adherence for one specific medicine.",
        {
            "medication": {"type": "string"},
            "taken": {"type": "string", "enum": ["all", "some", "none"]},
            "reason": {"type": "string"},
        },
        ["medication", "taken"],
    ),
    "set_language": (
        "Switch the call language when the patient asks for or clearly speaks another language.",
        {"language": {"type": "string", "enum": sorted(LANGUAGES)}},
        ["language"],
    ),
    "end_call": (
        "End the call. The closing line is spoken automatically.",
        {
            "reason": {
                "type": "string",
                "enum": ["completed", "consent_declined", "emergency", "patient_request", "callback",
                         "patient_unavailable", "wrong_person"],
            }
        },
        ["reason"],
    ),
}


def openai_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {"type": "object", "properties": props, "required": req},
            },
        }
        for name, (desc, props, req) in TOOL_SPECS.items()
    ]


def pipecat_tools():
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    return ToolsSchema(
        standard_tools=[
            FunctionSchema(name=name, description=desc, properties=props, required=req)
            for name, (desc, props, req) in TOOL_SPECS.items()
        ]
    )
