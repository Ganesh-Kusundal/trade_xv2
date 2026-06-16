"""Tests for BenchmarkSuite — mock gateway benchmarks."""

from unittest.mock import MagicMock

from brokers.common.services.benchmark import BenchmarkResult, BenchmarkSuite


class TestBenchmarkSuite:
    def _make_gw(self, latency_ms=10):
        gw = MagicMock()
        gw.history.return_value = MagicMock()
        gw.quote.return_value = MagicMock(ltp=100, volume=10000)
        gw.ltp.return_value = 100.0
        gw.depth.return_value = MagicMock(bids=[], asks=[])
        gw.option_chain.return_value = {"strikes": []}
        gw.future_chain.return_value = {"contracts": []}
        gw.search.return_value = [{"symbol": "RELIANCE"}]
        return gw

    def test_register_and_run(self):
        suite = BenchmarkSuite()
        gw = self._make_gw()
        suite.register("paper", gw)
        report = suite.run(symbols=["RELIANCE"], iterations=3)
        assert len(report.results) > 0
        assert all(r.success for r in report.results)

    def test_run_all_tests(self):
        suite = BenchmarkSuite()
        gw = self._make_gw()
        suite.register("paper", gw)
        report = suite.run(symbols=["RELIANCE"], iterations=2)
        test_names = {r.test_name for r in report.results}
        assert "historical" in test_names
        assert "quote" in test_names
        assert "ltp" in test_names
        assert "depth" in test_names
        assert "option_chain" in test_names
        assert "future_chain" in test_names
        assert "search" in test_names

    def test_run_specific_tests(self):
        suite = BenchmarkSuite()
        gw = self._make_gw()
        suite.register("paper", gw)
        report = suite.run(symbols=["RELIANCE"], iterations=2, tests=["quote", "ltp"])
        test_names = {r.test_name for r in report.results}
        assert test_names == {"quote", "ltp"}

    def test_multiple_symbols(self):
        suite = BenchmarkSuite()
        gw = self._make_gw()
        suite.register("paper", gw)
        report = suite.run(symbols=["RELIANCE", "TCS"], iterations=2, tests=["quote"])
        assert len(report.results) == 2
        symbols = {r.symbol for r in report.results}
        assert symbols == {"RELIANCE", "TCS"}

    def test_multiple_brokers(self):
        suite = BenchmarkSuite()
        gw1 = self._make_gw()
        gw2 = self._make_gw()
        suite.register("broker_a", gw1)
        suite.register("broker_b", gw2)
        report = suite.run(symbols=["RELIANCE"], iterations=2, tests=["quote"])
        assert len(report.results) == 2
        brokers = {r.broker for r in report.results}
        assert brokers == {"broker_a", "broker_b"}

    def test_failed_benchmark(self):
        suite = BenchmarkSuite()
        gw = self._make_gw()
        gw.quote.side_effect = Exception("API down")
        suite.register("paper", gw)
        report = suite.run(symbols=["RELIANCE"], iterations=2, tests=["quote"])
        assert all(not r.success for r in report.results)
        assert all("API down" in r.error for r in report.results)

    def test_broker_summaries(self):
        suite = BenchmarkSuite()
        gw = self._make_gw()
        suite.register("paper", gw)
        report = suite.run(symbols=["RELIANCE"], iterations=3)
        report.compute_summaries()
        assert "paper" in report.broker_summaries
        summary = report.broker_summaries["paper"]
        assert summary["tests"] > 0
        assert summary["passed"] > 0
        assert summary["avg_ms"] > 0
        assert summary["p50_ms"] > 0

    def test_print_report(self):
        suite = BenchmarkSuite()
        gw = self._make_gw()
        suite.register("paper", gw)
        report = suite.run(symbols=["RELIANCE"], iterations=2)
        output = suite.print_report(report)
        assert "BENCHMARK REPORT" in output
        assert "paper" in output
        assert "RELIANCE" in output

    def test_empty_gateways(self):
        suite = BenchmarkSuite()
        report = suite.run(symbols=["RELIANCE"], iterations=2)
        assert len(report.results) == 0

    def test_stats_calculation(self):
        stats = BenchmarkSuite._stats([10.0, 20.0, 30.0, 40.0, 50.0])
        assert stats["avg_ms"] == 30.0
        assert stats["min_ms"] == 10.0
        assert stats["max_ms"] == 50.0
        assert stats["p50_ms"] == 30.0
        assert stats["iterations"] == 5
        assert stats["throughput"] > 0

    def test_benchmark_result_defaults(self):
        r = BenchmarkResult(test_name="test", broker="paper", symbol="X")
        assert r.success is True
        assert r.latency_ms == 0.0
        assert r.error == ""
        assert r.metadata == {}
