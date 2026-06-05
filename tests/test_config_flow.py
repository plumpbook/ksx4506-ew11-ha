from pathlib import Path
import asyncio
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _integration_loader import load_integration_module  # noqa: E402
from ha_stubs import install_homeassistant_stubs  # noqa: E402

install_homeassistant_stubs()
const = load_integration_module("const")
config_flow = load_integration_module("config_flow")


def _schema_validator(data_schema, field):
    for key, validator in data_schema.schema.items():
        if getattr(key, "key", key) == field:
            return validator
    raise AssertionError(f"schema field not found: {field}")


def test_options_flow_packet_capture_filter_schema_is_frontend_serializable():
    entry = types.SimpleNamespace(
        data={
            const.CONF_HOST: "ew11.example.invalid",
            const.CONF_TIMEOUT: 3.0,
            const.CONF_RETRY: 2,
            const.CONF_MAX_ATTEMPTS: 10,
        },
        options={},
    )

    flow = config_flow.Ksx4506OptionsFlow(entry)
    result = asyncio.run(flow.async_step_init())

    assert _schema_validator(result["data_schema"], const.CONF_PACKET_CAPTURE_FILTER) is str


def test_options_flow_stores_user_editable_options():
    entry = types.SimpleNamespace(
        data={
            const.CONF_HOST: "ew11.example.invalid",
            const.CONF_PORT: 8899,
            const.CONF_TIMEOUT: 3.0,
            const.CONF_RETRY: 2,
            const.CONF_MAX_ATTEMPTS: 10,
            const.CONF_GAS_UNLOCK: False,
            const.CONF_EXPOSE_PACKET_SAMPLES: False,
            const.CONF_PACKET_CAPTURE_ENABLED: False,
            const.CONF_PACKET_CAPTURE_FILTER: "33,40",
            const.CONF_PACKET_CAPTURE_LIMIT: 20,
        },
        options={},
    )
    user_input = {
        const.CONF_TIMEOUT: 5.0,
        const.CONF_RETRY: 3,
        const.CONF_MAX_ATTEMPTS: 12,
        const.CONF_GAS_UNLOCK: False,
        const.CONF_EXPOSE_PACKET_SAMPLES: True,
        const.CONF_PACKET_CAPTURE_ENABLED: True,
        const.CONF_PACKET_CAPTURE_FILTER: "33",
        const.CONF_PACKET_CAPTURE_LIMIT: 10,
    }

    flow = config_flow.Ksx4506OptionsFlow(entry)
    result = asyncio.run(flow.async_step_init(user_input))

    assert result == {"type": "create_entry", "title": "", "data": user_input}


def test_options_flow_shows_form_for_existing_entry():
    entry = types.SimpleNamespace(
        data={
            const.CONF_HOST: "ew11.example.invalid",
            const.CONF_TIMEOUT: 3.0,
            const.CONF_RETRY: 2,
            const.CONF_MAX_ATTEMPTS: 10,
        },
        options={const.CONF_EXPOSE_PACKET_SAMPLES: True},
    )

    flow = config_flow.Ksx4506OptionsFlow(entry)
    result = asyncio.run(flow.async_step_init())

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert hasattr(result["data_schema"], "schema")
