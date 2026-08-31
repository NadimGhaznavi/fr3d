"""MCP entry point for validated Open-Meteo weather data."""

from mcp.server import MCPServer

from weather_tool.weather import get_weather

mcp = MCPServer("weather")


@mcp.tool()
def tool(location: str) -> str:
    """Get current weather and a three-day forecast for a city or postal code."""
    return get_weather(location)
