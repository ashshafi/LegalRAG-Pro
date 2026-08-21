import json
from uuid import uuid4

import pytest

from finance_case_binding.models import (
    FINANCE_CASE_BINDING_SCHEMA_VERSION,
    FinanceCaseActiveBinding,
)
from finance_case_binding.serialization import (
    dumps_finance_case_active_binding,
    loads_finance_case_active_binding,
)


def test_pointer_round_trip_is_canonical():
    pointer = FinanceCaseActiveBinding(
        schema_version=FINANCE_CASE_BINDING_SCHEMA_VERSION,
        case_id=str(uuid4()),
        workspace_id=str(uuid4()),
        activation_id="sha256:" + "b" * 64,
    )
    payload = dumps_finance_case_active_binding(pointer)
    assert loads_finance_case_active_binding(payload) == pointer
    assert payload == json.dumps(json.loads(payload), sort_keys=True, separators=(",", ":"))


def test_noncanonical_pointer_json_is_rejected():
    pointer = FinanceCaseActiveBinding(
        schema_version=FINANCE_CASE_BINDING_SCHEMA_VERSION,
        case_id=str(uuid4()),
        workspace_id=str(uuid4()),
        activation_id="sha256:" + "c" * 64,
    )
    data = json.loads(dumps_finance_case_active_binding(pointer))
    with pytest.raises(ValueError, match="not canonical"):
        loads_finance_case_active_binding(json.dumps(data, indent=2, sort_keys=True))
