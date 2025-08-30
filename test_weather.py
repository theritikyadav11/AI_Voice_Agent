#!/usr/bin/env python3
"""
Test script for the Weather Skill functionality
"""

import asyncio
import json
from main import get_coordinates, get_weather, weather_skill, is_weather_query, format_weather_response

async def test_weather_functions():
    """Test all weather-related functions."""
    
    print("🧪 Testing Weather Skill Functions...\n")
    
    # Test 1: Weather query detection
    print("1. Testing weather query detection:")
    test_queries = [
        "What's the weather in Paris?",
        "How hot is it in London?",
        "Tell me about the temperature in Tokyo",
        "What's the forecast for New York?",
        "Hello, how are you today?",  # Non-weather query
        "Weather in Berlin",
        "Temperature in Sydney"
    ]
    
    for query in test_queries:
        is_weather, city = is_weather_query(query)
        print(f"   Query: '{query}'")
        print(f"   Is weather: {is_weather}, City: '{city}'")
        print()
    
    # Test 2: Coordinates retrieval
    print("2. Testing coordinates retrieval:")
    test_cities = ["Paris", "London", "Tokyo", "New York", "InvalidCity123"]
    
    for city in test_cities:
        coords = await get_coordinates(city)
        if coords:
            lat, lon = coords
            print(f"   {city}: {lat}, {lon}")
        else:
            print(f"   {city}: Not found")
    print()
    
    # Test 3: Weather data retrieval
    print("3. Testing weather data retrieval:")
    # Test with Paris coordinates
    paris_coords = await get_coordinates("Paris")
    if paris_coords:
        lat, lon = paris_coords
        weather_data = await get_weather(lat, lon)
        if weather_data:
            print(f"   Paris weather: {json.dumps(weather_data, indent=2)}")
        else:
            print("   Failed to get weather data")
    print()
    
    # Test 4: Complete weather skill
    print("4. Testing complete weather skill:")
    test_cities = ["Paris", "London", "InvalidCity123"]
    
    for city in test_cities:
        result = await weather_skill(city)
        print(f"   {city}: {json.dumps(result, indent=2)}")
        print()
    
    # Test 5: Weather response formatting
    print("5. Testing weather response formatting:")
    sample_weather_data = {
        "city": "Paris",
        "temperature": 23.4,
        "wind_speed": 11.2,
        "description": "Partly cloudy",
        "humidity": 65
    }
    
    formatted_response = format_weather_response(sample_weather_data)
    print(f"   Formatted response: {formatted_response}")
    print()
    
    # Test 6: Error handling
    print("6. Testing error handling:")
    error_data = {"error": "Sorry, I couldn't find the city 'InvalidCity'."}
    error_response = format_weather_response(error_data)
    print(f"   Error response: {error_response}")
    print()
    
    print("✅ Weather Skill testing completed!")

if __name__ == "__main__":
    asyncio.run(test_weather_functions())