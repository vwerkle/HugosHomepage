import json
import re
import statsapi

def parse_player_data(text):
    data = {}
    lines = text.strip().split("\n")
    current_group = None

    for line in lines:
        line = line.strip()
        if not line:
            continue  # Skip empty lines
        
        if line.endswith(":"):  # Detect group names
            current_group = line[:-1].strip()
            data[current_group] = {}  # Initialize the group
        elif current_group:  # Process players
            player_name = line
            player_id = get_mlb_player_id(player_name)
            if player_id is not None:  # Ensure we store valid IDs
                data[current_group][player_name] = player_id

    return data

def get_mlb_player_id(player_name):
    try:
        search_results = statsapi.lookup_player(player_name)
        if search_results:
            return search_results[0]['id']  # Return first matched player ID
        else:
            print(f"No player found with the name {player_name}.")
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# Sample input text
input_text = """
Seamo:
Mike Trout
Ozzie Albies
Fernando Tatis Jr.
Kyle Tucker
Triston Casas
Kyle Schwarber
Austin Riley
Matt Olson

Moran:
Mike Trout
Alex Bregman
Cody Bellinger
Fernando Tatis
Isaac Paredes
Matt Olson
Mark Vientos
Austin Wells

Jonnie:
Kerry Carpenter
Luis Robert Jr.
Matt Olson
Wyatt Langford
Mike Trout
Julio Rodriguez
Austin Riley
Yordan Alvarez

Christian:
Fernando Tatis Jr.
Mike Trout
Luis Robert Jr.
Vladimir Guerrero Jr.
Bryce Harper
Matt Olson
Christian Yelich
Cody Bellinger

Tony:
Gunnar Henderson
Francisco Lindor
Christopher Morel
CJ Abrams
Kerry Carpenter
Luis Robert Jr. 
Tyler Soderstrom
Pavin Smith

Austin:
Kyle Schwarber
Gunnar Henderson
Fernando Tatis Jr.
Austin Riley
Luis Robert Jr.
Triston Casas
Mike Trout
Ozzie Albies

Bobby D:
Royce Lewis
Triston Casas
Kyle Tucker
Fernando Tatis Jr.
Cody Bellinger
Mookie Betts
Juan Soto
Mike Trout

Andy:
Juan Soto
Kyle Schwarber
Matt Olson
JT Realmuto
Anthony Volpe
Mike Trout
Gavin Sheets
J.P Crawford

Glancy:
Gunnar Henderson
Francisco Lindor
Bryan Reynolds
Will Smith 
Mitch Garver
Alex Bohm
Mike Trout
Carson Kelly
"""

# Parse and convert to JSON
parsed_data = parse_player_data(input_text)
json_output = json.dumps(parsed_data, indent=4)

# Save to a file
with open("players_seamo.json", "w") as f:
    f.write(json_output)

print("JSON file created successfully.")
