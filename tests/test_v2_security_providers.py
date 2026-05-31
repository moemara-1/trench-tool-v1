import pytest

from trench_v2.core.models import Chain, RiskLevel, RiskReport
from trench_v2.providers.security import CompositeRiskProvider, GoPlusRiskProvider, HoneypotRiskProvider


class FakeGetClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def get_json(self, url: str, params: dict[str, str] | None = None):
        self.calls.append((url, params or {}))
        return self.response


@pytest.mark.asyncio
async def test_goplus_provider_normalizes_contract_and_tax_risk():
    client = FakeGetClient(
        {
            "result": {
                "0xabc": {
                    "is_honeypot": "0",
                    "buy_tax": "0.025",
                    "sell_tax": "0.125",
                    "is_blacklisted": "1",
                    "is_mintable": "1",
                    "is_proxy": "1",
                    "is_open_source": "0",
                    "lp_holders": [
                        {"is_locked": 0, "percent": "0.72"},
                    ],
                }
            }
        }
    )
    provider = GoPlusRiskProvider(client=client, api_key="key")

    report = await provider.fetch_risk(Chain.BASE, "0xAbC")

    assert report.level is RiskLevel.HIGH
    assert report.buy_tax_bps == 250
    assert report.sell_tax_bps == 1250
    assert report.liquidity_locked is False
    assert report.malicious_contract is True
    assert report.liquidity_pull_risk is True
    assert "blacklist control" in report.reasons
    assert client.calls[0][0].endswith("/api/v1/token_security/8453")
    assert client.calls[0][1]["contract_addresses"] == "0xabc"


@pytest.mark.asyncio
async def test_goplus_provider_marks_zero_holders_as_unindexed_caution():
    client = FakeGetClient(
        {
            "result": {
                "0xabc": {
                    "is_honeypot": "0",
                    "buy_tax": "0",
                    "sell_tax": "0",
                    "holder_count": "0",
                    "is_open_source": "1",
                }
            }
        }
    )
    provider = GoPlusRiskProvider(client=client)

    report = await provider.fetch_risk(Chain.BSC, "0xAbC")

    assert report.level is RiskLevel.MEDIUM
    assert report.malicious_contract is False
    assert "holder data missing or zero holders reported" in report.reasons


@pytest.mark.asyncio
async def test_honeypot_provider_normalizes_simulation_tax_and_honeypot_flags():
    client = FakeGetClient(
        {
            "honeypotResult": {"isHoneypot": True},
            "simulationResult": {"buyTax": 4.5, "sellTax": 22.0},
            "summary": {"risk": "high"},
        }
    )
    provider = HoneypotRiskProvider(client=client, api_key="key")

    report = await provider.fetch_risk(Chain.BSC, "0xdef")

    assert report.level is RiskLevel.CRITICAL
    assert report.is_honeypot is True
    assert report.buy_tax_bps == 450
    assert report.sell_tax_bps == 2200
    assert "honeypot simulation failed" in report.reasons
    assert client.calls[0][0] == "https://api.honeypot.is/v2/IsHoneypot"
    assert client.calls[0][1]["chainID"] == "56"


@pytest.mark.asyncio
async def test_honeypot_provider_marks_zero_holders_as_unindexed_caution():
    client = FakeGetClient(
        {
            "token": {"totalHolders": 0},
            "honeypotResult": {"isHoneypot": False},
            "simulationResult": {"buyTax": 0, "sellTax": 0},
            "summary": {"risk": "low"},
        }
    )
    provider = HoneypotRiskProvider(client=client)

    report = await provider.fetch_risk(Chain.BSC, "0xdef")

    assert report.level is RiskLevel.MEDIUM
    assert report.malicious_contract is False
    assert "holder data missing or zero holders reported" in report.reasons


@pytest.mark.asyncio
async def test_composite_risk_provider_keeps_highest_risk_and_combines_reasons():
    go_plus = GoPlusRiskProvider(
        client=FakeGetClient(
            {
                "result": {
                    "0xabc": {
                        "buy_tax": "0.00",
                        "sell_tax": "0.04",
                        "is_open_source": "0",
                    }
                }
            }
        )
    )
    honeypot = HoneypotRiskProvider(
        client=FakeGetClient(
            {
                "honeypotResult": {"isHoneypot": False},
                "simulationResult": {"buyTax": 1.0, "sellTax": 8.0},
            }
        )
    )
    provider = CompositeRiskProvider([go_plus, honeypot])

    report = await provider.fetch_risk(Chain.ETHEREUM, "0xAbC")

    assert report.level is RiskLevel.MEDIUM
    assert report.is_honeypot is False
    assert report.buy_tax_bps == 100
    assert report.sell_tax_bps == 800
    assert "contract source is not verified" in report.reasons
    assert "sell tax 8.00%" in report.reasons


@pytest.mark.asyncio
async def test_composite_risk_provider_ignores_provider_outage_when_another_provider_is_clean():
    class StaticProvider:
        def __init__(self, report: RiskReport):
            self.report = report

        async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
            return self.report

    provider = CompositeRiskProvider(
        [
            StaticProvider(RiskReport(level=RiskLevel.LOW, reasons=["GoPlus found no high-risk flags"])),
            StaticProvider(RiskReport(level=RiskLevel.MEDIUM, reasons=["Honeypot.is unavailable: 404 Not Found"])),
        ]
    )

    report = await provider.fetch_risk(Chain.BASE, "0xabc")

    assert report.level is RiskLevel.LOW
    assert report.reasons == ["GoPlus found no high-risk flags"]
