"""BrokerService integration with broker gateways."""

from interface.ui.services.broker_service import BrokerService


def test_broker_service_builds_infrastructure_with_paper():
    service = BrokerService()
    service.set_active_broker("paper")
    # Verify the paper broker is available through the current API
    assert service.active_broker_name == "paper"
    assert "paper" in service.gateways or service.active_broker is not None
    service.close()
