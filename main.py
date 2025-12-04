import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# ============================================
# STAGE 1: VIDEO ANALYSIS
# ============================================

def analyze_video(video_path, home_type="apartment", room_count=3):
    """
    Analyze home video and extract furniture/items inventory
    
    Args:
        video_path: Path to video file or YouTube URL
        home_type: "apartment" or "house"
        room_count: Number of rooms in the home
    
    Returns:
        dict: Inventory with items, volume, and special handling needs
    """
    
    # Determine if it's a file or YouTube URL
    is_youtube = video_path.startswith('http')
    
    # Create the prompt for video analysis
    prompt = f"""
Analyze this home moving video and create an inventory list.

Context:
- Home type: {home_type}
- Number of rooms: {room_count}

Instructions:
1. Identify ALL furniture, appliances, and household items visible in the video
2. Count the quantity of each item
3. Categorize size as: large, medium, or small
4. Categorize type as: furniture, appliance, box, or other
5. Estimate total volume in cubic feet
6. Flag any items needing special handling (piano, large wardrobe, fragile electronics, etc.)

Return ONLY a valid JSON object in this exact format (no markdown, no explanation):
{{
  "items": [
    {{"name": "sofa", "quantity": 1, "size": "large", "category": "furniture"}},
    {{"name": "dining table", "quantity": 1, "size": "large", "category": "furniture"}}
  ],
  "total_volume_cubic_feet": 800,
  "needs_special_handling": ["piano", "large_wardrobe"]
}}
"""
    
    try:
        if is_youtube:
            # YouTube URL
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=types.Content(
                    parts=[
                        types.Part(
                            file_data=types.FileData(file_uri=video_path)
                        ),
                        types.Part(text=prompt)
                    ]
                )
            )
        else:
            # Local video file (for small files < 20MB)
            if os.path.getsize(video_path) < 20 * 1024 * 1024:
                # Inline video
                with open(video_path, 'rb') as f:
                    video_bytes = f.read()
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=types.Content(
                        parts=[
                            types.Part(
                                inline_data=types.Blob(
                                    data=video_bytes,
                                    mime_type='video/mp4'
                                )
                            ),
                            types.Part(text=prompt)
                        ]
                    )
                )
            else:
                # Use File API for larger files
                print("Uploading video file...")
                myfile = client.files.upload(file=video_path)
                
                # Wait for file to be processed and become ACTIVE
                print(f"Waiting for file {myfile.name} to be processed...")
                while myfile.state.name == "PROCESSING":
                    time.sleep(2)
                    myfile = client.files.get(name=myfile.name)
                
                if myfile.state.name == "FAILED":
                    raise Exception(f"File processing failed: {myfile.name}")
                
                print(f"File {myfile.name} is ready (state: {myfile.state.name})")
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[myfile, prompt]
                )
        
        # Parse the response
        result_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        inventory = json.loads(result_text)
        return inventory
        
    except Exception as e:
        print(f"Error analyzing video: {e}")
        raise


# ============================================
# STAGE 2: COST ESTIMATION
# ============================================

# Pricing configuration (store these in your database)
PRICING_CONFIG = {
    "labor_rate_per_hour": 35,
    "truck_rates": {
        "small": 75,
        "medium": 120,
        "large": 180
    },
    "fuel_cost_per_km": 0.5,
    "stairs_fee_per_floor": 25,
    "packing_material_per_cubic_feet": 0.20,
    "base_hours": 4,
    "hour_per_100_cubic_feet": 0.5
}


def calculate_move_cost(inventory, distance_km, origin_floor, destination_floor, 
                       has_elevator_origin=False, has_elevator_destination=False):
    """
    Calculate moving cost based on inventory and move details
    
    Args:
        inventory: Output from Stage 1 (analyze_video)
        distance_km: Distance between origin and destination
        origin_floor: Floor number at origin
        destination_floor: Floor number at destination
        has_elevator_origin: Whether origin has elevator
        has_elevator_destination: Whether destination has elevator
    
    Returns:
        dict: Cost breakdown and moving details
    """
    
    # Prepare AI input for intelligent estimation
    prompt = f"""
Analyze this moving inventory and provide intelligent estimates.

Inventory:
{json.dumps(inventory, indent=2)}

Move Details:
- Distance: {distance_km} km
- Origin floor: {origin_floor} (Elevator: {has_elevator_origin})
- Destination floor: {destination_floor} (Elevator: {has_elevator_destination})

Based on the items, especially heavy/special items, provide:
1. Recommended number of movers (2-6 people)
2. Truck type needed: small (up to 400 cubic feet), medium (400-900), large (900+)
3. Additional hours needed beyond base time due to item complexity
4. Any special handling notes

Return ONLY a valid JSON object:
{{
  "recommended_movers": 3,
  "truck_type": "medium",
  "complexity_hours_add": 1.5,
  "special_notes": "Piano requires extra care and time"
}}
"""
    
    try:
        # Get AI recommendations
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        result_text = response.text.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        ai_estimate = json.loads(result_text)
        
    except Exception as e:
        print(f"AI estimation failed, using fallback: {e}")
        # Fallback to simple rules
        volume = inventory.get('total_volume_cubic_feet', 500)
        ai_estimate = {
            "recommended_movers": 2 if volume < 400 else (3 if volume < 800 else 4),
            "truck_type": "small" if volume < 400 else ("medium" if volume < 900 else "large"),
            "complexity_hours_add": len(inventory.get('needs_special_handling', [])) * 0.5,
            "special_notes": ""
        }
    
    # Calculate costs using formulas
    volume = inventory.get('total_volume_cubic_feet', 500)
    movers = ai_estimate['recommended_movers']
    truck_type = ai_estimate['truck_type']
    
    # Time estimation
    base_hours = PRICING_CONFIG['base_hours']
    volume_hours = (volume / 100) * PRICING_CONFIG['hour_per_100_cubic_feet']
    complexity_hours = ai_estimate.get('complexity_hours_add', 0)
    estimated_hours = round(base_hours + volume_hours + complexity_hours, 1)
    
    # Labor cost
    labor_cost = round(movers * estimated_hours * PRICING_CONFIG['labor_rate_per_hour'], 2)
    
    # Truck cost
    truck_base = PRICING_CONFIG['truck_rates'][truck_type]
    fuel_cost = round(distance_km * PRICING_CONFIG['fuel_cost_per_km'], 2)
    truck_total = truck_base + fuel_cost
    
    # Stairs fee
    stairs_floors = 0
    if not has_elevator_origin and origin_floor > 1:
        stairs_floors += (origin_floor - 1)
    if not has_elevator_destination and destination_floor > 1:
        stairs_floors += (destination_floor - 1)
    stairs_fee = stairs_floors * PRICING_CONFIG['stairs_fee_per_floor']
    
    # Materials
    materials_cost = round(volume * PRICING_CONFIG['packing_material_per_cubic_feet'], 2)
    
    # Other fees (insurance, supplies, etc.)
    other_fees = round((labor_cost + truck_total) * 0.05, 2)
    
    # Total
    total_cost = round(labor_cost + truck_total + stairs_fee + materials_cost + other_fees, 2)
    
    # Cost range (+/- 10%)
    cost_min = round(total_cost * 0.9, 2)
    cost_max = round(total_cost * 1.1, 2)
    
    return {
        "total_cost": total_cost,
        "cost_range": [cost_min, cost_max],
        "movers_needed": movers,
        "truck_type": truck_type,
        "estimated_hours": estimated_hours,
        "breakdown": {
            "labor": labor_cost,
            "truck": truck_base,
            "fuel": fuel_cost,
            "materials": materials_cost,
            "stairs_fee": stairs_fee,
            "other": other_fees
        },
        "special_notes": ai_estimate.get('special_notes', '')
    }


# ============================================
# COMPLETE WORKFLOW
# ============================================

def estimate_moving_cost(video_path, distance_km, origin_floor, destination_floor,
                        has_elevator_origin=False, has_elevator_destination=False,
                        home_type="apartment", room_count=3):
    """
    Complete workflow: Analyze video and calculate moving cost
    
    Args:
        video_path: Path to video file or YouTube URL
        distance_km: Distance in kilometers
        origin_floor: Origin floor number
        destination_floor: Destination floor number
        has_elevator_origin: Origin has elevator
        has_elevator_destination: Destination has elevator
        home_type: "apartment" or "house"
        room_count: Number of rooms
    
    Returns:
        dict: Complete analysis with inventory and cost estimate
    """
    
    print("Stage 1: Analyzing video...")
    inventory = analyze_video(video_path, home_type, room_count)
    print(f"✓ Found {len(inventory['items'])} items")
    print(f"✓ Total volume: {inventory['total_volume_cubic_feet']} cubic feet")
    
    print("\nStage 2: Calculating cost...")
    cost_estimate = calculate_move_cost(
        inventory, 
        distance_km, 
        origin_floor, 
        destination_floor,
        has_elevator_origin,
        has_elevator_destination
    )
    print(f"✓ Estimated cost: ${cost_estimate['total_cost']}")
    
    return {
        "inventory": inventory,
        "cost_estimate": cost_estimate
    }


# ============================================
# USAGE EXAMPLE
# ============================================

if __name__ == "__main__":
    # Example 1: Using local video file
    result = estimate_moving_cost(
        video_path="C:/SM_TECH/Running_Projects/Gino+melik/meilika/trial/videos/video1.mp4",
        distance_km=45,
        origin_floor=3,
        destination_floor=2,
        has_elevator_origin=False,
        has_elevator_destination=True,
        home_type="apartment",
        room_count=3
    )
    
    print("\n" + "="*50)
    print("COMPLETE ESTIMATE")
    print("="*50)
    print(json.dumps(result, indent=2))
    
    # Example 2: Using YouTube URL
    # result = estimate_moving_cost(
    #     video_path="https://www.youtube.com/watch?v=YOUR_VIDEO_ID",
    #     distance_km=30,
    #     origin_floor=1,
    #     destination_floor=1,
    #     home_type="house",
    #     room_count=4
    # )