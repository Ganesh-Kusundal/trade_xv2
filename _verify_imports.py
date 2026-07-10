"""Quick import verification for the decomposed BrokerService."""
import sys
sys.path.insert(0, "/Users/apple/Downloads/Trade_XV2")

try:
    from cli.services.oms_bootstrap import OmsBootstrap
    print("OmsBootstrap import: OK")
except Exception as e:
    print(f"OmsBootstrap import: FAIL - {e}")

try:
    from cli.services.cli_broker_facade import CliBrokerFacade
    print("CliBrokerFacade import: OK")
except Exception as e:
    print(f"CliBrokerFacade import: FAIL - {e}")

try:
    from cli.services.broker_manager import BrokerManager
    print("BrokerManager import: OK")
except Exception as e:
    print(f"BrokerManager import: FAIL - {e}")

try:
    from cli.services.broker_service import BrokerService
    print("BrokerService import: OK")
except Exception as e:
    print(f"BrokerService import: FAIL - {e}")
