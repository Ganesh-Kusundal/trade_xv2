"""Unit tests for PnlExitAdapter (Trader's Control /pnlExit)."""

from decimal import Decimal

import pytest

from brokers.dhan.exceptions import PnlExitError
from brokers.dhan.execution.pnl_exit import PnlExitAdapter


def test_configure_pnl_exit_success(fake_client):
    fake_client.set_response(
        "POST",
        "/pnlExit",
        {
            "pnlExitStatus": "ACTIVE",
            "message": "P&L based exit configured successfully",
        },
    )
    adapter = PnlExitAdapter(fake_client)
    result = adapter.configure(
        profit_value=Decimal("1500"),
        loss_value=Decimal("500"),
        product_types=["INTRADAY", "CNC"],
        enable_kill_switch=True,
    )

    assert result.status == "ACTIVE"
    assert "configured" in result.message.lower() or result.message

    payload = fake_client.calls_for("POST", "/pnlExit")[0]
    assert payload["profitValue"] == "1500"
    assert payload["lossValue"] == "500"
    assert payload["productType"] == ["INTRADAY", "CNC"]
    assert payload["enableKillSwitch"] is True


def test_configure_requires_threshold(fake_client):
    adapter = PnlExitAdapter(fake_client)
    with pytest.raises(ValueError, match="profit_value or loss_value"):
        adapter.configure()


def test_configure_profit_only(fake_client):
    fake_client.set_response(
        "POST",
        "/pnlExit",
        {"pnlExitStatus": "ACTIVE", "message": "ok"},
    )
    adapter = PnlExitAdapter(fake_client)
    result = adapter.configure(profit_value=1000)
    assert result.status == "ACTIVE"
    payload = fake_client.calls_for("POST", "/pnlExit")[0]
    assert "profitValue" in payload
    assert "lossValue" not in payload


def test_stop_pnl_exit(fake_client):
    fake_client.set_response(
        "DELETE",
        "/pnlExit",
        {"pnlExitStatus": "DISABLED", "message": "P&L based exit stopped successfully"},
    )
    adapter = PnlExitAdapter(fake_client)
    result = adapter.stop()
    assert result.status == "DISABLED"
    assert fake_client.calls_for("DELETE", "/pnlExit")


def test_get_pnl_exit(fake_client):
    fake_client.set_response(
        "GET",
        "/pnlExit",
        {
            "pnlExitStatus": "ACTIVE",
            "profit": "1500.00",
            "loss": "500.00",
            "productType": ["INTRADAY", "DELIVERY"],
            "enable_kill_switch": True,
        },
    )
    adapter = PnlExitAdapter(fake_client)
    cfg = adapter.get()

    assert cfg.status == "ACTIVE"
    assert cfg.profit_value == Decimal("1500.00")
    assert cfg.loss_value == Decimal("500.00")
    assert cfg.product_types == ("INTRADAY", "DELIVERY")
    assert cfg.enable_kill_switch is True


def test_configure_api_error(fake_client):
    fake_client.set_side_effect("POST", "/pnlExit", RuntimeError("network"))
    adapter = PnlExitAdapter(fake_client)
    with pytest.raises(PnlExitError, match="network"):
        adapter.configure(loss_value=100)
