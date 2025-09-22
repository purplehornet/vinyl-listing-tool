import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_discogs_collection(username, token):
    """
    Fetches a user's Discogs collection.
    """
    url = f"https://api.discogs.com/users/{username}/collection/folders/0/releases"
    headers = {"Authorization": f"Discogs token={token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["releases"]

def get_vinyl_details(release):
    """
    Extracts details for a vinyl record.
    """
    basic_info = release["basic_information"]
    title = basic_info["title"]
    artist = basic_info["artists"][0]["name"]
    year = basic_info.get("year", "N/A")
    
    # Get median price from Discogs marketplace
    marketplace_url = f"https://www.discogs.com/sell/release/{release['id']}"
    try:
        response = requests.get(marketplace_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        price_stats = soup.find('div', class_='price_stats')
        if price_stats:
            median_price_text = price_stats.find('li', text=lambda t: t and 'Median:' in t)
            if median_price_text:
                median_price = median_price_text.text.split(':')[1].strip()
            else:
                median_price = "N/A"
        else:
            median_price = "N/A"

    except requests.exceptions.RequestException as e:
        print(f"Could not fetch marketplace data for {title}: {e}")
        median_price = "Error"

    return {
        "Artist": artist,
        "Title": title,
        "Year": year,
        "Median Price (Discogs)": median_price
    }

def main():
    """
    Main function to run the script.
    """
    discogs_username = os.getenv("DISCOGS_USERNAME")
    discogs_token = os.getenv("DISCOGS_TOKEN")

    if not discogs_username or not discogs_token:
        print("Error: DISCOGS_USERNAME and DISCOGS_TOKEN must be set in .env file.")
        return

    print("Fetching your Discogs collection...")
    collection = get_discogs_collection(discogs_username, discogs_token)
    
    print(f"Found {len(collection)} releases. Fetching details and prices...")
    vinyl_data = [get_vinyl_details(release) for release in collection]
    
    df = pd.DataFrame(vinyl_data)
    
    # Save to CSV
    df.to_csv("vinyl_collection_prices.csv", index=False)
    print("Data saved to vinyl_collection_prices.csv")

if __name__ == "__main__":
    main()