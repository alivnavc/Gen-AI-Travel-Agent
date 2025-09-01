import re
import asyncio
import subprocess
import time
import logging
import traceback
import json
import requests
from textwrap import dedent
from agno.agent import Agent
from agno.tools.mcp import MultiMCPTools
from agno.tools.googlesearch import GoogleSearchTools
from agno.models.openai import OpenAIChat
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import streamlit as st
from datetime import date
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('travel_planner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TravelPlannerApp:
    """Main application class for Travel Planner with MCP integration."""
    
    def __init__(self):
        """Initialize the application."""
        pass
    

        


def generate_ics_content(plan_text: str, start_date: datetime = None) -> bytes:
    """
    Generate an ICS calendar file from a travel itinerary text.

    Args:
        plan_text: The travel itinerary text
        start_date: Optional start date for the itinerary (defaults to today)

    Returns:
        bytes: The ICS file content as bytes
    """
    cal = Calendar()
    cal.add('prodid','-//AI Travel Planner//github.com//')
    cal.add('version', '2.0')

    if start_date is None:
        start_date = datetime.today()

    # Split the plan into days
    day_pattern = re.compile(r'Day (\d+)[:\s]+(.*?)(?=Day \d+|$)', re.DOTALL)
    days = day_pattern.findall(plan_text)

    if not days:  # If no day pattern found, create a single all-day event with the entire content
        event = Event()
        event.add('summary', "Travel Itinerary")
        event.add('description', plan_text)
        event.add('dtstart', start_date.date())
        event.add('dtend', start_date.date())
        event.add("dtstamp", datetime.now())
        cal.add_component(event)
    else:
        # Process each day
        for day_num, day_content in days:
            day_num = int(day_num)
            current_date = start_date + timedelta(days=day_num - 1)

            # Create a single event for the entire day
            event = Event()
            event.add('summary', f"Day {day_num} Itinerary")
            event.add('description', day_content.strip())

            # Make it an all-day event
            event.add('dtstart', current_date.date())
            event.add('dtend', current_date.date())
            event.add("dtstamp", datetime.now())
            cal.add_component(event)

    return cal.to_ical()

async def run_mcp_travel_planner(source: str, destination: str, num_days: int, preferences: str, budget: int, start_date: str, return_date: str = None):
    """Run the MCP-based travel planner agent with real-time data access."""

    try:
        # Get API keys from environment variables
        openai_key = os.getenv("OPENAI_API_KEY")
        google_maps_key = os.getenv("GOOGLE_MAPS_API_KEY")
        
        if not openai_key or not google_maps_key:
            raise ValueError("Missing required API keys in environment variables")

        # Initialize MultiMCPTools with built-in MCP servers and our custom Flight Search MCP
        multi_mcp_tools = MultiMCPTools(
            commands=[
                "npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt",
                "npx @gongrzhe/server-travelplanner-mcp"
            ],
            urls=["http://localhost:8001/mcp"],  # Our custom Flight Search MCP server
            urls_transports=["streamable-http"],
            env={
                "GOOGLE_MAPS_API_KEY": google_maps_key,
                "SERPAPI_KEY": os.getenv("SERPAPI_KEY", ""),
            },
            timeout_seconds=60,
        )   

        # Connect to all MCP servers
        await multi_mcp_tools.connect()

        travel_planner = Agent(
            name="Travel Planner",
            role="Creates comprehensive travel itineraries using Airbnb, Google Maps, and Flight Search MCP servers",
            model=OpenAIChat(id="gpt-4o", api_key=openai_key),
            description=dedent(
                """\
                You are a professional travel consultant AI that creates highly detailed travel itineraries with real flight data, accommodation options, and location services.

                You have access to:
                ✈️ Flight Search MCP with these tools:
                   - search_flights: Find real flights with prices, airlines, departure/arrival times, and booking links
                   - search_airports: Search for airport information and IATA codes
                   - get_flight_prices: Get price trends and insights for flights
                🏨 Airbnb listings with real availability and current pricing
                🗺️ Google Maps MCP for location services, directions, distance calculations, and local navigation
                🔍 Web search capabilities for current information, reviews, and travel updates

                ALWAYS create a complete, detailed itinerary immediately without asking for clarification or additional information.
                Use Flight Search MCP tools extensively to find real flights, airport information, and price trends.
                Use Google Maps MCP extensively to calculate distances between all locations and provide precise travel times.
                Use Airbnb MCP to find real accommodation options with current pricing.
                If information is missing, use your best judgment and available tools to fill in the gaps.
                """
            ),
            instructions=[
                "IMPORTANT: Never ask questions or request clarification - always generate a complete itinerary",
                "Use Flight Search MCP tools extensively:",
                "  - Use search_flights to find real flights with prices, airlines, departure/arrival times, and booking links",
                "  - Use search_airports to find airport information and IATA codes for the destination",
                "  - Use get_flight_prices to analyze price trends and find the best time to book",
                "Research the destination thoroughly using all available tools to gather comprehensive current information",
                "Find suitable accommodation options within the budget using Airbnb MCP with real prices and availability",
                "Create an extremely detailed day-by-day itinerary with specific activities, locations, exact timing, and distances",
                "Use Google Maps MCP extensively to calculate distances between ALL locations and provide travel times",
                "Include detailed transportation options and turn-by-turn navigation tips using Google Maps MCP",
                "Research dining options with specific restaurant names, addresses, price ranges, and distance from accommodation",
                "Check current weather conditions, seasonal factors, and provide detailed packing recommendations",
                "Calculate precise estimated costs for EVERY aspect of the trip and ensure recommendations fit within budget",
                "Include detailed information about each attraction: opening hours, ticket prices, best visiting times, and distance from accommodation",
                "Add practical information including local transportation costs, currency exchange, safety tips, and cultural norms",
                "Structure the itinerary with clear sections, detailed timing for each activity, and include buffer time between activities",
                "Use all available tools proactively without asking for permission",
                "Generate the complete, detailed itinerary in one response without follow-up questions"
            ],
            tools=[multi_mcp_tools, GoogleSearchTools()],
            add_datetime_to_instructions=True,
            markdown=True,
            show_tool_calls=False,
        )

        # Create the planning prompt
        prompt = f"""
        IMMEDIATELY create an extremely detailed and comprehensive travel itinerary for:

        **Source Airport:** {source}
        **Destination Airport:** {destination}
        **Departure Date:** {start_date}
        **Return Date:** {return_date if return_date else "One-way trip"}
        **Duration:** {num_days} days
        **Budget:** ${budget} USD total
        **Preferences:** {preferences}

        DO NOT ask any questions. Generate a complete, highly detailed itinerary now using all available tools.

        **CRITICAL REQUIREMENTS:**
        - Use Flight Search MCP tools extensively:
          * Use search_flights with source="{source}", destination="{destination}", departure_date="{start_date}" to find real flights with prices, airlines, departure/arrival times, and booking links
          * Use search_airports to find airport information and IATA codes for both source and destination
          * Use get_flight_prices with source="{source}", destination="{destination}", departure_date="{start_date}" to analyze price trends and find the best time to book
        - Use Google Maps MCP to calculate distances and travel times between ALL locations
        - Use Airbnb MCP to find real accommodation options with current pricing and availability
        - Include specific addresses for every location, restaurant, and attraction
        - Provide detailed timing for each activity with buffer time between locations
        - Calculate precise costs for transportation between each location
        - Include opening hours, ticket prices, and best visiting times for all attractions
        - Provide detailed weather information and specific packing recommendations

        **REQUIRED OUTPUT FORMAT:**
        1. **Flight Information** - Real flight options from {source} to {destination} with prices, airlines, times, and booking links (use search_flights tool)
        2. **Airport Information** - Airport details and IATA codes for both {source} and {destination} (use search_airports tool)
        3. **Price Analysis** - Price trends and best booking times for {source} to {destination} route (use get_flight_prices tool)
        4. **Trip Overview** - Summary, total estimated cost breakdown, detailed weather forecast
        5. **Accommodation** - 3 specific Airbnb options with real prices, addresses, amenities, and distance from city center (use Airbnb MCP)
        6. **Transportation Overview** - Detailed transportation options, costs, and recommendations (use Google Maps MCP)
        7. **Day-by-Day Itinerary** - Extremely detailed schedule with:
           - Specific start/end times for each activity
           - Exact distances and travel times between locations (use Google Maps MCP)
           - Detailed descriptions of each location with addresses
           - Opening hours, ticket prices, and best visiting times
           - Estimated costs for each activity and transportation
           - Buffer time between activities for unexpected delays
        8. **Dining Plan** - Specific restaurants with addresses, price ranges, cuisine types, and distance from accommodation
        9. **Detailed Practical Information**:
           - Weather forecast with clothing recommendations
           - Currency exchange rates and costs
           - Local transportation options and costs
           - Safety information and emergency contacts
           - Cultural norms and etiquette tips
           - Communication options (SIM cards, WiFi, etc.)
           - Health and medical considerations
           - Shopping and souvenir recommendations

        Use Flight Search MCP tools (search_flights, search_airports, get_flight_prices) for real flight data, Airbnb MCP for real accommodation data, Google Maps MCP for ALL distance calculations and location services, and web search for current information.
        Make reasonable assumptions and fill in any gaps with your knowledge.
        Generate the complete, highly detailed itinerary in one response without asking for clarification.
        """

        response = await travel_planner.arun(prompt)
        return response.content

    except Exception as e:
        logger.error(f"Error in MCP travel planner: {str(e)}\n{traceback.format_exc()}")
        raise e
    finally:
        try:
            await multi_mcp_tools.close()
        except Exception as e:
            logger.error(f"Error closing MCP tools: {str(e)}")

def run_travel_planner(source: str, destination: str, num_days: int, preferences: str, budget: int, start_date: str, return_date: str = None):
    """Synchronous wrapper for the async MCP travel planner."""
    return asyncio.run(run_mcp_travel_planner(source, destination, num_days, preferences, budget, start_date, return_date))

# Initialize the app
app = TravelPlannerApp()

# -------------------- Streamlit App --------------------
    
# Configure the page
st.set_page_config(
    page_title="MCP AI Travel Planner",
    page_icon="✈️",
    layout="wide"
)

# Initialize session state
if 'itinerary' not in st.session_state:
    st.session_state.itinerary = None

# Title and description
st.title("✈️ MCP AI Travel Planner")
st.caption("Plan your next adventure with AI Travel Planner using multiple MCP servers for real-time data access")

if 1:
    # Main input section
    st.header("🌍 Trip Details")

    col1, col2, col3 = st.columns(3)

    with col1:
        source = st.text_input("Departure Airport (IATA Code)", placeholder="e.g., BOM, DEL, JFK", value="SFO")
        num_days = st.number_input("Number of Days", min_value=1, max_value=30, value=7)

    with col2:
        destination = st.text_input("Destination Airport (IATA Code)", placeholder="e.g., DEL, BLR, LAX")
        budget = st.number_input("Budget (USD)", min_value=100, max_value=10000, step=100, value=2000)

    with col3:
        start_date = st.date_input("Start Date", min_value=date.today(), value=date.today())
        return_date = st.date_input("Return Date (Optional)", min_value=date.today(), value=date.today() + timedelta(days=7))

    # Preferences section
    st.subheader("🎯 Travel Preferences")
    preferences_input = st.text_area(
        "Describe your travel preferences",
        placeholder="e.g., adventure activities, cultural sites, food, relaxation, nightlife...",
        height=100
    )

    # Quick preference buttons
    quick_prefs = st.multiselect(
        "Quick Preferences (optional)",
        ["Adventure", "Relaxation", "Sightseeing", "Cultural Experiences",
         "Beach", "Mountain", "Luxury", "Budget-Friendly", "Food & Dining",
         "Shopping", "Nightlife", "Family-Friendly"],
        help="Select multiple preferences or describe in detail above"
    )

    # Combine preferences
    all_preferences = []
    if preferences_input:
        all_preferences.append(preferences_input)
    if quick_prefs:
        all_preferences.extend(quick_prefs)

    preferences = ", ".join(all_preferences) if all_preferences else "General sightseeing"

    # Generate button
    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("🎯 Generate Itinerary", type="primary"):
            if not destination:
                st.error("Please enter a destination.")
            elif not preferences:
                st.warning("Please describe your preferences or select quick preferences.")
            else:
                tools_message = "✈️ Connecting to Flight Search MCP, 🏨 Airbnb MCP, and 🗺️ Google Maps MCP, creating comprehensive itinerary..."

                with st.spinner(tools_message):
                    try:
                        # Calculate number of days from start date
                        response = run_travel_planner(
                            source=source,
                            destination=destination,
                            num_days=num_days,
                            preferences=preferences,
                            budget=budget,
                            start_date=start_date.strftime("%Y-%m-%d"),
                            return_date=return_date.strftime("%Y-%m-%d") if return_date else None
                        )

                        # Store the response in session state
                        st.session_state.itinerary = response

                        # Show MCP connection status
                        mcp_status = []
                        if any(term in response.lower() for term in ["search_flights", "search_airports", "get_flight_prices", "serpapi_response", "flight data", "airline", "booking link"]):
                            mcp_status.append("✈️ Flight Search MCP")
                        if "airbnb" in response.lower() and ("listing" in response.lower() or "accommodation" in response.lower()):
                            mcp_status.append("🏨 Airbnb MCP")
                        if "distance" in response.lower() and ("maps" in response.lower() or "location" in response.lower()):
                            mcp_status.append("🗺️ Google Maps MCP")
                        
                        if mcp_status:
                            st.success("✅ Your comprehensive travel itinerary is ready!")
                            st.info(f"Used: {', '.join(mcp_status)} for real-time data")
                        else:
                            st.success("✅ Your travel itinerary is ready!")
                            st.info("📝 Used general knowledge for recommendations (some MCP servers may have failed to connect)")

                    except Exception as e:
                        logger.error(f"Error generating itinerary: {str(e)}\n{traceback.format_exc()}")
                        st.error(f"Error: {str(e)}")
                        st.info("Please try again or check your internet connection and API keys.")

    with col2:
        if st.session_state.itinerary:
            # Generate the ICS file
            ics_content = generate_ics_content(st.session_state.itinerary, datetime.combine(start_date, datetime.min.time()))

            # Provide the file for download
            st.download_button(
                label="📅 Download as Calendar",
                data=ics_content,
                file_name="travel_itinerary.ics",
                mime="text/calendar"
            )

    # Display itinerary
    if st.session_state.itinerary:
        st.header("📋 Your Comprehensive Travel Itinerary")
        st.markdown(st.session_state.itinerary)

