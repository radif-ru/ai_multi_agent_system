"""Тесты `app.utils.secrets.mask_secrets`."""

from __future__ import annotations

from app.utils.secrets import MASK, mask_secrets


def test_masks_authorization_header_regardless_of_case():
    src = {"headers": {"Authorization": "Bearer abc", "X-API-Key": "zzz"}}
    out = mask_secrets(src)
    assert out == {"headers": {"Authorization": MASK, "X-API-Key": MASK}}


def test_masks_token_and_api_key_fields():
    src = {
        "telegram_bot_token": "123:abc",
        "api_key": "secret",
        "public_id": 42,
        "nested": {"service_token": "xyz", "value": "ok"},
    }
    out = mask_secrets(src)
    assert out["telegram_bot_token"] == MASK
    assert out["api_key"] == MASK
    assert out["public_id"] == 42
    assert out["nested"] == {"service_token": MASK, "value": "ok"}


def test_masks_password_fields_and_handles_lists():
    src = {"items": [{"password": "p"}, {"other": 1}]}
    out = mask_secrets(src)
    assert out == {"items": [{"password": MASK}, {"other": 1}]}


def test_passthrough_for_non_dict_types():
    assert mask_secrets("hello") == "hello"
    assert mask_secrets(42) == 42
    assert mask_secrets(None) is None
    assert mask_secrets([1, 2, 3]) == [1, 2, 3]


def test_does_not_mutate_source():
    src = {"token": "t", "nested": {"password": "p"}}
    original = {"token": "t", "nested": {"password": "p"}}
    _ = mask_secrets(src)
    assert src == original
