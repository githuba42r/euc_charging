"""Gotway model picker, InMotion V1 password: flows, repairs, coordinator wiring."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.data_entry_flow import FlowResultType  # noqa: E402

from euc_charging import config_flow, repairs  # noqa: E402
from euc_charging import coordinator as coord_mod  # noqa: E402
from euc_charging.const import (  # noqa: E402
    CONF_GOTWAY_CELLS,
    CONF_GOTWAY_MODEL,
    CONF_INMOTION_PASSWORD,
    CONF_INMOTION_PASSWORD_MODE,
    DOMAIN,
    INMOTION_WRITE_SERVICE_UUID,
    WheelBrand,
    is_inmotion_v1_device,
)
from euc_charging.decoders import GotwayDecoder, InMotionDecoder, KingSongDecoder  # noqa: E402
from euc_charging.gotway_models import GOTWAY_MODELS  # noqa: E402

TRANSLATIONS = json.loads(
    (Path(__file__).parent.parent / "custom_components/euc_charging/translations/en.json").read_text()
)


class FakeEntries:
    def __init__(self, entry):
        self.entry = entry
        self.updates = []

    def async_get_known_entry(self, entry_id):
        return self.entry

    def async_get_entry(self, entry_id):
        return self.entry

    def async_update_entry(self, entry, data=None, options=None):
        if data is not None:
            entry.data = data
        if options is not None:
            entry.options = options
        self.updates.append((data, options))
        return True


def make_entry(data=None, options=None, title="My wheel"):
    return SimpleNamespace(
        entry_id="abc", title=title, data=data or {"address": "AA:BB"}, options=options or {}
    )


def make_hass(entry, decoder=None):
    coordinator = SimpleNamespace(decoder=decoder)
    return SimpleNamespace(
        config_entries=FakeEntries(entry), data={DOMAIN: {entry.entry_id: coordinator}}
    )


def run_options(entry, decoder, user_input=None):
    flow = config_flow.WheelOptionsFlow()
    flow.hass = make_hass(entry, decoder)
    flow.handler = entry.entry_id
    flow.flow_id = "f"
    flow.context = {}
    return flow, asyncio.run(
        flow.async_step_wheel(user_input) if user_input is not None else flow.async_step_init()
    )


# --- options flow ------------------------------------------------------------------

def test_gotway_options_form_lists_auto_custom_and_all_models():
    entry = make_entry()
    _, result = run_options(entry, GotwayDecoder())
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "wheel"
    keys = [str(k) for k in result["data_schema"].schema]
    assert keys == [CONF_GOTWAY_MODEL, CONF_GOTWAY_CELLS]
    choices = config_flow.gotway_model_choices()
    assert [c["value"] for c in choices[:2]] == ["auto", "custom"]
    assert len(choices) == 2 + len(GOTWAY_MODELS) == 96


def test_gotway_options_saved():
    entry = make_entry()
    _, result = run_options(entry, GotwayDecoder(), {CONF_GOTWAY_MODEL: "RS C38", CONF_GOTWAY_CELLS: "24"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_GOTWAY_MODEL: "RS C38", CONF_GOTWAY_CELLS: 24}


def test_inmotion_options_change_password_in_entry_data():
    entry = make_entry()
    flow, result = run_options(
        entry, InMotionDecoder(),
        {CONF_INMOTION_PASSWORD_MODE: "custom", CONF_INMOTION_PASSWORD: "4321"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_INMOTION_PASSWORD] == "4321"


def test_invalid_password_rejected():
    entry = make_entry()
    _, result = run_options(
        entry, InMotionDecoder(),
        {CONF_INMOTION_PASSWORD_MODE: "custom", CONF_INMOTION_PASSWORD: "1234567"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_INMOTION_PASSWORD: "invalid_password"}


def test_unknown_brand_shows_both_and_veteran_none():
    assert config_flow.wheel_option_fields(make_entry(), None) == (True, True)
    assert config_flow.wheel_option_fields(make_entry(), WheelBrand.VETERAN) == (False, False)
    entry = make_entry()
    from euc_charging.decoders import VeteranDecoder
    _, result = run_options(entry, VeteranDecoder())
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "no_wheel_options"


# --- config flow password step ------------------------------------------------------

def test_is_inmotion_v1_device():
    assert is_inmotion_v1_device("V8F-1234")
    assert is_inmotion_v1_device("Mystery", [INMOTION_WRITE_SERVICE_UUID.upper()])
    assert not is_inmotion_v1_device("V13-1")
    assert not is_inmotion_v1_device("LK3336")


def _config_flow():
    flow = config_flow.EucChargingConfigFlow()
    flow.hass = SimpleNamespace()
    flow.flow_id = "f"
    flow.context = {"source": "user"}
    flow.handler = DOMAIN
    return flow


def test_config_flow_asks_inmotion_v1_password():
    flow = _config_flow()
    info = SimpleNamespace(name="V8F-1234", address="AA:BB", service_uuids=[])
    result = asyncio.run(flow._async_create_wheel_entry(info))
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "inmotion_password"
    result = asyncio.run(flow.async_step_inmotion_password(
        {CONF_INMOTION_PASSWORD_MODE: "custom", CONF_INMOTION_PASSWORD: "8888"}
    ))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {"address": "AA:BB", CONF_INMOTION_PASSWORD: "8888"}


def test_config_flow_default_password():
    flow = _config_flow()
    asyncio.run(flow._async_create_wheel_entry(SimpleNamespace(name="V8F", address="AA:BB", service_uuids=[])))
    result = asyncio.run(flow.async_step_inmotion_password({CONF_INMOTION_PASSWORD_MODE: "default"}))
    assert result["data"][CONF_INMOTION_PASSWORD] == "000000"


def test_config_flow_other_wheels_skip_password():
    flow = _config_flow()
    result = asyncio.run(flow._async_create_wheel_entry(
        SimpleNamespace(name="LK3336", address="AA:BB", service_uuids=[])
    ))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {"address": "AA:BB"}


# --- repairs ------------------------------------------------------------------------

def _repair(flow_cls, entry):
    flow = flow_cls("abc")
    flow.hass = make_hass(entry)
    flow.flow_id = "r"
    flow.handler = DOMAIN
    flow.context = {"issue_id": "x"}
    return flow


def test_gotway_repair_flow_sets_option():
    entry = make_entry()
    flow = _repair(repairs.GotwayModelRepairFlow, entry)
    result = asyncio.run(flow.async_step_init())
    assert result["step_id"] == "select_model"
    result = asyncio.run(flow.async_step_select_model({CONF_GOTWAY_MODEL: "custom", CONF_GOTWAY_CELLS: "36"}))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_GOTWAY_MODEL: "custom", CONF_GOTWAY_CELLS: 36}


def test_inmotion_repair_flow_sets_password():
    entry = make_entry()
    flow = _repair(repairs.InMotionPasswordRepairFlow, entry)
    assert asyncio.run(flow.async_step_init())["step_id"] == "password"
    result = asyncio.run(flow.async_step_password(
        {CONF_INMOTION_PASSWORD_MODE: "custom", CONF_INMOTION_PASSWORD: "1111"}
    ))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_INMOTION_PASSWORD] == "1111"


def test_create_fix_flow_dispatch():
    flow = asyncio.run(repairs.async_create_fix_flow(None, "gotway_model_abc", {"entry_id": "abc"}))
    assert isinstance(flow, repairs.GotwayModelRepairFlow)
    flow = asyncio.run(repairs.async_create_fix_flow(None, "inmotion_password_abc", {"entry_id": "abc"}))
    assert isinstance(flow, repairs.InMotionPasswordRepairFlow)


# --- coordinator wiring ---------------------------------------------------------------

class IssueRecorder:
    def __init__(self, monkeypatch):
        self.open = {}
        monkeypatch.setattr(coord_mod.ir, "async_create_issue",
                            lambda hass, domain, issue_id, **kw: self.open.__setitem__(issue_id, kw))
        monkeypatch.setattr(coord_mod.ir, "async_delete_issue",
                            lambda hass, domain, issue_id: self.open.pop(issue_id, None))


def coordinator(entry, decoder):
    c = object.__new__(coord_mod.EucChargingCoordinator)
    c.hass = SimpleNamespace()
    c.entry = entry
    c.decoder = decoder
    c._silent_password_connects = 0
    c._password_issue_open = False
    c._gotway_issue_open = None
    c._preselect_disabled = False
    return c


def test_gotway_option_applied_and_issue_lifecycle(monkeypatch):
    issues = IssueRecorder(monkeypatch)
    entry = make_entry()
    d = GotwayDecoder()
    c = coordinator(entry, d)
    c._configure_decoder()
    d._probe = "done"            # probe gave up without a match
    c._update_issues()
    assert "gotway_model_abc" in issues.open
    assert issues.open["gotway_model_abc"]["is_fixable"]
    entry.options = {CONF_GOTWAY_MODEL: "Master Pro"}
    c.async_apply_options()
    assert d.model.name == "Master Pro"
    assert "gotway_model_abc" not in issues.open
    entry.options = {CONF_GOTWAY_MODEL: "custom", CONF_GOTWAY_CELLS: 20}
    c.async_apply_options()
    assert d.model.full_voltage == pytest.approx(84.0)
    entry.options = {CONF_GOTWAY_MODEL: "auto"}
    c.async_apply_options()
    assert d.model is None and "gotway_model_abc" in issues.open


def test_inmotion_password_issue_after_three_silent_connects(monkeypatch):
    issues = IssueRecorder(monkeypatch)
    entry = make_entry(data={"address": "AA:BB", CONF_INMOTION_PASSWORD: "1234"})
    d = InMotionDecoder()
    c = coordinator(entry, d)
    c._configure_decoder()
    assert d.password == "1234"
    for i in range(3):
        d.get_requests()          # password goes out, wheel stays silent
        assert d.password_sent
        c._check_inmotion_password()
        d.reset_session()
    assert "inmotion_password_abc" in issues.open
    # new password -> fresh chances; successful decode clears the issue
    entry.data = {**entry.data, CONF_INMOTION_PASSWORD: "000000"}
    c.async_apply_options()
    assert d.password == "000000" and c._silent_password_connects == 0
    d.values_received = True
    c._update_issues()
    assert "inmotion_password_abc" not in issues.open


def test_answering_inmotion_wheel_never_raises_issue(monkeypatch):
    issues = IssueRecorder(monkeypatch)
    d = InMotionDecoder()
    c = coordinator(make_entry(), d)
    for _ in range(5):
        d.password_sent = True
        d.values_received = True
        c._check_inmotion_password()
    assert issues.open == {}


def test_other_decoders_untouched(monkeypatch):
    issues = IssueRecorder(monkeypatch)
    c = coordinator(make_entry(options={CONF_GOTWAY_MODEL: "RS C38"}), KingSongDecoder())
    c._configure_decoder()
    c._update_issues()
    c._check_inmotion_password()
    assert issues.open == {}


# --- translations --------------------------------------------------------------------

def test_translations_cover_new_strings():
    t = TRANSLATIONS
    assert "inmotion_password" in t["config"]["step"]
    assert "wheel" in t["options"]["step"]
    assert "init" in t["options"]["step"]            # TPMS options untouched
    assert set(t["issues"]) == {"gotway_model", "inmotion_password"}
    assert "select_model" in t["issues"]["gotway_model"]["fix_flow"]["step"]
    assert "password" in t["issues"]["inmotion_password"]["fix_flow"]["step"]
    assert set(t["selector"]["inmotion_password_mode"]["options"]) == {"default", "custom"}


def test_gotway_issue_not_flapped_by_reconnect(monkeypatch):
    """Reconnect restarts the probe: the issue must stay (so "Ignore" sticks)."""
    issues = IssueRecorder(monkeypatch)
    calls = []
    monkeypatch.setattr(coord_mod.ir, "async_delete_issue",
                        lambda hass, domain, issue_id: calls.append(("delete", issue_id)))
    d = GotwayDecoder()
    c = coordinator(make_entry(), d)
    d._probe = "done"
    c._update_issues()
    assert "gotway_model_abc" in issues.open
    created = len(issues.open)
    d.reset_session()                 # reconnect: probing again
    assert d.model_unmatched is None
    c._update_issues()
    d._probe = "done"                 # probe fails again
    c._update_issues()
    assert calls == [] and len(issues.open) == created
