"""Unit tests for infrastructure core tools and ToolRegistry."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.domain.exceptions import InvalidToolSelectionError
from app.domain.protocols.tool import AgentToolProtocol
from app.domain.value_objects.enums import ToolName
from app.infrastructure.tools import (
    CalculatorTool,
    CsvLookupTool,
    CurrentDateTool,
    ToolRegistry,
    WeatherHttpTool,
    get_tool_registry,
)

SAMPLE_SHIP_SPARES_CSV = """part_number,name,category,stock,unit_price_usd
SP-101,Main Fuel Injector,fuel_system,14,420.50
SP-102,High Pressure Fuel Pump,fuel_system,3,1850.00
SP-201,Cylinder Head Gasket,engine,25,95.00
SP-301,Bilge Submersible Pump,bilge,8,310.00
"""


@pytest.mark.unit
def test_all_tools_satisfy_agent_tool_protocol() -> None:
    """All core tools must conform to AgentToolProtocol."""
    tools = [
        CalculatorTool(),
        CurrentDateTool(),
        WeatherHttpTool(),
        CsvLookupTool(),
    ]
    for tool in tools:
        assert isinstance(tool, AgentToolProtocol)
        assert isinstance(tool.name, ToolName)
        assert isinstance(tool.description, str) and tool.description
        assert isinstance(tool.parameters_schema, dict)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 3 * 4", "14"),
        ("(2 + 3) * 4", "20"),
        ("10 / 4", "2.5"),
        ("2 ** 10", "1024"),
        ("17 % 5", "2"),
        ("-5 + +8", "3"),
        ("1.5 * 2", "3.0"),
    ],
)
async def test_calculator_evaluates_safe_math(expression: str, expected: str) -> None:
    """CalculatorTool evaluates supported arithmetic expressions safely."""
    tool = CalculatorTool()
    assert tool.name == ToolName.CALCULATOR
    result = await tool.execute(expression=expression)
    assert result == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "unsafe_expr",
    [
        "__import__('os').system('echo pwned')",
        "eval('1+1')",
        "open('/etc/passwd').read()",
        "(1).__class__.__mro__",
        "x + 1",
        "True + 1",
        "1 / 0",
        "2 ** 10000",
        "",
        "   ",
        "2 + * 3",
    ],
)
async def test_calculator_rejects_unsafe_or_invalid_expressions(unsafe_expr: str) -> None:
    """CalculatorTool rejects function calls, imports, attributes, and invalid math."""
    tool = CalculatorTool()
    with pytest.raises(ValueError):
        await tool.execute(expression=unsafe_expr)


@pytest.mark.unit
async def test_current_date_deterministic_utc_and_offsets() -> None:
    """CurrentDateTool formats deterministic ISO-8601 UTC and offset timestamps."""
    fixed_now = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
    tool = CurrentDateTool(clock=lambda: fixed_now)
    assert tool.name == ToolName.CURRENT_DATE

    assert await tool.execute() == "2026-11-25T12:00:00+00:00"
    assert await tool.execute(timezone_offset="Z") == "2026-11-25T12:00:00+00:00"
    assert await tool.execute(timezone_offset="+05:30") == "2026-11-25T17:30:00+05:30"
    assert await tool.execute(timezone_offset="-04:00") == "2026-11-25T08:00:00-04:00"


@pytest.mark.unit
async def test_current_date_invalid_offset_raises() -> None:
    """CurrentDateTool rejects malformed timezone offsets."""
    tool = CurrentDateTool()
    with pytest.raises(ValueError):
        await tool.execute(timezone_offset="UTC+5")


@pytest.mark.unit
async def test_current_date_default_clock_returns_iso8601() -> None:
    """CurrentDateTool uses UTC now by default and returns parseable ISO-8601."""
    tool = CurrentDateTool()
    raw = await tool.execute()
    parsed = datetime.fromisoformat(raw)
    assert parsed.tzinfo is not None


@pytest.mark.unit
@respx.mock
async def test_weather_http_queries_open_meteo() -> None:
    """WeatherHttpTool queries Open-Meteo and returns structured weather JSON."""
    route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200,
            json={
                "latitude": 51.5,
                "longitude": -0.12,
                "current_weather": {
                    "temperature": 11.4,
                    "windspeed": 14.2,
                    "weathercode": 3,
                    "time": "2026-11-25T12:00",
                },
                "current_weather_units": {
                    "temperature": "°C",
                    "windspeed": "km/h",
                },
            },
        )
    )

    tool = WeatherHttpTool()
    assert tool.name == ToolName.WEATHER_HTTP

    result = await tool.execute(latitude=51.5, longitude=-0.12)
    payload = json.loads(result)

    assert route.called
    assert payload["latitude"] == 51.5
    assert payload["longitude"] == -0.12
    assert payload["current_weather"]["temperature"] == 11.4


@pytest.mark.unit
@respx.mock
async def test_weather_http_raises_on_http_error() -> None:
    """WeatherHttpTool propagates HTTPStatusError when Open-Meteo fails."""
    respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(503, json={"error": "unavailable"})
    )
    tool = WeatherHttpTool()
    with pytest.raises(httpx.HTTPStatusError):
        await tool.execute(latitude=35.68, longitude=139.69)


@pytest.mark.unit
async def test_weather_http_validates_coordinates() -> None:
    """WeatherHttpTool validates latitude and longitude bounds."""
    tool = WeatherHttpTool()
    with pytest.raises(ValueError):
        await tool.execute(latitude=95.0, longitude=0.0)
    with pytest.raises(ValueError):
        await tool.execute(latitude=0.0, longitude=-185.0)


@pytest.mark.unit
async def test_csv_lookup_filters_and_searches_rows() -> None:
    """CsvLookupTool filters ship-spares CSV rows by keyword and column filters."""
    tool = CsvLookupTool()
    assert tool.name == ToolName.CSV_LOOKUP
    tool.load_csv_text(SAMPLE_SHIP_SPARES_CSV)

    # Keyword search across columns
    pump_res = json.loads(await tool.execute(query="pump"))
    assert pump_res["count"] == 2
    assert {row["part_number"] for row in pump_res["rows"]} == {"SP-102", "SP-301"}

    # Column filter (case-insensitive)
    fuel_res = json.loads(await tool.execute(filters={"category": "FUEL_SYSTEM"}))
    assert fuel_res["count"] == 2

    # Combined filter + keyword + limit
    combined = json.loads(
        await tool.execute(query="injector", filters={"category": "fuel_system"}, limit=5)
    )
    assert combined["count"] == 1
    assert combined["rows"][0]["part_number"] == "SP-101"

    # No matches
    empty = json.loads(await tool.execute(query="nonexistent_part"))
    assert empty == {"count": 0, "rows": []}


@pytest.mark.unit
def test_tool_registry_lru_cache_and_subset() -> None:
    """get_tool_registry is cached via @lru_cache and returns requested subsets."""
    get_tool_registry.cache_clear()
    reg_a = get_tool_registry()
    reg_b = get_tool_registry()
    assert reg_a is reg_b
    assert isinstance(reg_a, ToolRegistry)

    assert len(reg_a.available_names()) == 4
    calc = reg_a.get(ToolName.CALCULATOR)
    assert isinstance(calc, CalculatorTool)

    subset = reg_a.get_subset([ToolName.CSV_LOOKUP, ToolName.CURRENT_DATE, ToolName.CSV_LOOKUP])
    assert [t.name for t in subset] == [ToolName.CSV_LOOKUP, ToolName.CURRENT_DATE]


@pytest.mark.unit
def test_tool_registry_rejects_unregistered_tool() -> None:
    """ToolRegistry raises InvalidToolSelectionError for missing tools."""
    registry = ToolRegistry(tools=[CalculatorTool()])
    with pytest.raises(InvalidToolSelectionError):
        registry.get(ToolName.WEATHER_HTTP)
    with pytest.raises(InvalidToolSelectionError):
        registry.get_subset([ToolName.CALCULATOR, ToolName.CSV_LOOKUP])
