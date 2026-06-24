"""BrokerService integration with BrokerInfrastructure."""

from cli.services.broker_service import BrokerService


def test_broker_service_builds_infrastructure_with_paper():
    service = BrokerService()
    service.set_active_broker("paper")
    infra = service.broker_infrastructure
    assert infra is not None
    assert infra.registry.get_gateway("paper") is not None
    service.close()
