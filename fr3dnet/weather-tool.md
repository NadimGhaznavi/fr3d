# Weather Tool

The Weather Tool retrieves current conditions and a three-day forecast from Open-Meteo.

## Input

The weather_tool accepts a city, a city with its region and country, or a postal code. More specific locations produce more reliable matches.

The location is checked for length and allowed characters, then resolved through the Open-Meteo geocoding service. Forecast requests use only the validated coordinates returned by that service.

## Output

The result includes the requested location, resolved place, current conditions, units, and daily forecast. Fr3d should compare the requested and resolved locations before relying on the weather data.

- [Return to the Knowledge Base](/)
