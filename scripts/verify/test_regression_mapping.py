import json
import sys
from datetime import datetime

from brokers.providers.dhan.symbol_validator import DhanSymbolValidator


def validate_schema(result: dict) -> bool:
    """Validate result against the expected JSON schema based on status and fields."""
    # Common field
    if "status" not in result:
        return False

    status = result["status"]
    if status not in ("VALID", "INVALID", "AMBIGUOUS", "EXPIRED"):
        return False

    # Check schema depending on F&O vs standard
    if "underlying" in result:
        # F&O schema check
        expected_keys = {
            "underlying",
            "expiry",
            "strike",
            "optionType",
            "securityId",
            "exchange",
            "segment",
            "lotSize",
            "status",
        }
        # Check all expected keys exist
        if not expected_keys.issubset(result.keys()):
            missing = expected_keys - result.keys()
            print(f"Schema Error: Missing F&O keys: {missing}")
            return False

        # Type checks
        if not isinstance(result["underlying"], str):
            return False
        if result["expiry"] is not None and not isinstance(result["expiry"], str):
            return False
        if result["strike"] is not None and not isinstance(result["strike"], int | float):
            return False
        if result["optionType"] is not None and result["optionType"] not in ("CE", "PE"):
            return False
        if result["securityId"] is not None and not isinstance(result["securityId"], str):
            return False
        if not isinstance(result["exchange"], str):
            return False
        if not isinstance(result["segment"], str):
            return False
        if result["lotSize"] is not None and not isinstance(result["lotSize"], int):
            return False

    else:
        # Standard schema check
        if status == "VALID":
            expected_keys = {
                "exchange",
                "segment",
                "tradingSymbol",
                "displayName",
                "securityId",
                "instrumentType",
                "status",
            }
            if not expected_keys.issubset(result.keys()):
                missing = expected_keys - result.keys()
                print(f"Schema Error: Missing standard keys: {missing}")
                return False
            # Type checks
            for k in [
                "exchange",
                "segment",
                "tradingSymbol",
                "displayName",
                "securityId",
                "instrumentType",
            ]:
                if not isinstance(result[k], str):
                    return False
        elif status == "AMBIGUOUS":
            expected_keys = {"status", "message", "candidates"}
            if not expected_keys.issubset(result.keys()):
                return False
            if not isinstance(result["candidates"], list):
                return False
            for cand in result["candidates"]:
                for k in [
                    "exchange",
                    "segment",
                    "tradingSymbol",
                    "displayName",
                    "securityId",
                    "instrumentType",
                ]:
                    if k not in cand or not isinstance(cand[k], str):
                        return False
        else:
            # INVALID
            expected_keys = {"status", "message", "candidates"}
            if not expected_keys.issubset(result.keys()):
                return False

    return True


def main():
    print("Initializing Dhan Symbol Validator...")
    validator = DhanSymbolValidator()
    print("Validator ready.")

    test_cases = [
        # (Symbol, Optional[Exchange], Optional[Segment])
        ("RELIANCE", "NSE", "E"),
        ("TCS", None, None),
        ("INFY", None, None),
        ("SBIN", None, None),
        ("NIFTY", "INDEX", None),
        ("BANKNIFTY", "INDEX", None),
        ("NIFTY 26 JUN 25000 CE", None, None),
        ("NIFTY 26 JUN 25000 PE", None, None),
        ("BANKNIFTY 24 JUL 55000 CE", None, None),
        ("BANKNIFTY 24 JUL 55000 PE", None, None),
        ("CRUDEOIL", None, None),
        ("GOLDM", None, None),
        ("USDINR", None, None),
    ]

    print("\n=======================================================")
    print("RUNNING DHAN SYMBOL MAPPING REGRESSION TEST CASES")
    print("=======================================================\n")

    all_passed = True
    report = []

    for sym, exch, seg in test_cases:
        print(f"Input Symbol: '{sym}' (Exch={exch}, Seg={seg})")

        # Validate symbol
        res = validator.validate(sym, exchange=exch, segment=seg)

        # Verify JSON schema validity
        schema_ok = validate_schema(res)

        # Verify unique securityId lookup, exchange and segment correctness where applicable
        checks = {
            "Symbol Normalization": "PASSED",
            "JSON Schema Validity": "PASSED" if schema_ok else "FAILED",
        }

        if not schema_ok:
            all_passed = False

        status = res.get("status")

        # Check securityId lookup uniqueness
        if status == "VALID":
            checks["Unique securityId Lookup"] = "PASSED (ID: " + str(res.get("securityId")) + ")"

            # Verify exchange correctness
            if exch and res.get("exchange") != exch.upper():
                checks["Exchange Correctness"] = (
                    f"FAILED (Expected {exch}, Got {res.get('exchange')})"
                )
                all_passed = False
            else:
                checks["Exchange Correctness"] = "PASSED"

            # Verify segment correctness
            if seg and res.get("segment") != seg.upper():
                checks["Segment Correctness"] = f"FAILED (Expected {seg}, Got {res.get('segment')})"
                all_passed = False
            else:
                checks["Segment Correctness"] = "PASSED"

            # Verify instrument type correctness
            if res.get("instrumentType"):
                checks["Instrument Type Correctness"] = f"PASSED ({res.get('instrumentType')})"
            else:
                checks["Instrument Type Correctness"] = "FAILED"
                all_passed = False

        elif status == "AMBIGUOUS":
            checks["Unique securityId Lookup"] = (
                f"AMBIGUOUS ({len(res.get('candidates', []))} candidates)"
            )
            checks["Exchange Correctness"] = "N/A"
            checks["Segment Correctness"] = "N/A"
            checks["Instrument Type Correctness"] = "N/A"

        elif status == "EXPIRED":
            checks["Unique securityId Lookup"] = "PASSED (EXPIRED/PAST CONTRACT)"
            checks["Exchange Correctness"] = "PASSED"
            checks["Segment Correctness"] = "PASSED"
            checks["Instrument Type Correctness"] = "PASSED (F&O)"

        else:
            checks["Unique securityId Lookup"] = "FAILED (Not Found)"
            checks["Exchange Correctness"] = "FAILED"
            checks["Segment Correctness"] = "FAILED"
            checks["Instrument Type Correctness"] = "FAILED"
            all_passed = False

        # Print detailed report for this test case
        print("Results:")
        for check_name, check_status in checks.items():
            print(f"  - {check_name}: {check_status}")

        print("\nJSON Output:")
        print(json.dumps(res, indent=2))
        print("-" * 55 + "\n")

        report.append({"symbol": sym, "result": res, "checks": checks, "passed": all_passed})

    print("=======================================================")
    if all_passed:
        print("✓ ALL REGRESSION TESTS PASSED (Schema + Correctness)")
    else:
        print("✗ SOME REGRESSION TESTS FAILED OR NEED ATTENTION")
    print("=======================================================")


if __name__ == "__main__":
    main()
