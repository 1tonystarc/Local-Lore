from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import asyncio
from typing import List, Dict, Any, Optional
import json
import re
from urllib.parse import quote
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Local Lore API",
    description="Discover India's Hidden Heritage through Wikimedia APIs",
    version="1.0.0"
)

# Enable CORS for PWA
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Wikimedia API endpoints
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"

# Language mapping for multilingual support
LANGUAGE_CODES = {
    "en": "en",
    "hi": "hi", 
    "ta": "ta",
    "te": "te",
    "bn": "bn"
}

class WikimediaClient:
    def __init__(self):
        self.session = httpx.AsyncClient(timeout=30.0)
    
    async def search_wikipedia(self, query: str, lang: str = "en", limit: int = 10) -> List[Dict]:
        """Search Wikipedia articles for a location"""
        try:
            wiki_lang = LANGUAGE_CODES.get(lang, "en")
            api_url = f"https://{wiki_lang}.wikipedia.org/w/api.php"
            
            params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": f"{query} India",
                "srlimit": limit,
                "srprop": "snippet|titlesnippet|size"
            }
            
            response = await self.session.get(api_url, params=params)
            data = response.json()
            
            if "query" in data and "search" in data["query"]:
                return data["query"]["search"]
            return []
            
        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            return []
    
    async def get_article_content(self, title: str, lang: str = "en") -> Dict[str, Any]:
        """Get full article content and extract"""
        try:
            wiki_lang = LANGUAGE_CODES.get(lang, "en")
            api_url = f"https://{wiki_lang}.wikipedia.org/w/api.php"
            
            params = {
                "action": "query",
                "format": "json",
                "titles": title,
                "prop": "extracts|pageimages|coordinates|categories",
                "exintro": True,
                "explaintext": True,
                "exsectionformat": "plain",
                "piprop": "original",
                "coprop": "lat|lon",
                "cllimit": 10
            }
            
            response = await self.session.get(api_url, params=params)
            data = response.json()
            
            if "query" in data and "pages" in data["query"]:
                page_data = list(data["query"]["pages"].values())[0]
                return page_data
            return {}
            
        except Exception as e:
            logger.error(f"Article content error: {e}")
            return {}
    
    async def get_commons_images(self, search_term: str, limit: int = 10) -> List[Dict]:
        """Get images from Wikimedia Commons"""
        try:
            params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srnamespace": 6,  # File namespace
                "srsearch": f"{search_term} India",
                "srlimit": limit,
                "srprop": "snippet|titlesnippet"
            }
            
            response = await self.session.get(COMMONS_API, params=params)
            data = response.json()
            
            if "query" in data and "search" in data["query"]:
                images = []
                for item in data["query"]["search"]:
                    # Get image info
                    img_params = {
                        "action": "query",
                        "format": "json",
                        "titles": item["title"],
                        "prop": "imageinfo",
                        "iiprop": "url|size|mime|extmetadata",
                        "iiurlwidth": 400
                    }
                    
                    img_response = await self.session.get(COMMONS_API, params=img_params)
                    img_data = img_response.json()
                    
                    if "query" in img_data and "pages" in img_data["query"]:
                        page = list(img_data["query"]["pages"].values())[0]
                        if "imageinfo" in page:
                            img_info = page["imageinfo"][0]
                            images.append({
                                "title": item["title"].replace("File:", ""),
                                "url": img_info.get("thumburl", img_info.get("url")),
                                "full_url": img_info.get("url"),
                                "width": img_info.get("thumbwidth", img_info.get("width")),
                                "height": img_info.get("thumbheight", img_info.get("height")),
                                "description": img_info.get("extmetadata", {}).get("ImageDescription", {}).get("value", "")
                            })
                
                return images[:limit]
            return []
            
        except Exception as e:
            logger.error(f"Commons images error: {e}")
            return []
    
    async def get_wikivoyage_content(self, location: str, lang: str = "en") -> Dict[str, Any]:
        """Get travel and cultural information from Wikivoyage"""
        try:
            wiki_lang = LANGUAGE_CODES.get(lang, "en")
            api_url = f"https://{wiki_lang}.wikivoyage.org/w/api.php"
            
            params = {
                "action": "query",
                "format": "json",
                "titles": location,
                "prop": "extracts|pageimages",
                "exintro": True,
                "explaintext": True,
                "exsectionformat": "plain",
                "piprop": "original"
            }
            
            response = await self.session.get(api_url, params=params)
            data = response.json()
            
            if "query" in data and "pages" in data["query"]:
                page_data = list(data["query"]["pages"].values())[0]
                return page_data
            return {}
            
        except Exception as e:
            logger.error(f"Wikivoyage content error: {e}")
            return {}

# Initialize Wikimedia client
wikimedia = WikimediaClient()

@app.get("/")
async def root():
    return {"message": "Local Lore API - Discover India's Hidden Heritage"}

@app.get("/api/search")
async def search_locations(
    query: str = Query(..., description="Location to search for"),
    lang: str = Query("en", description="Language code (en, hi, ta, te, bn)"),
    limit: int = Query(10, ge=1, le=20, description="Number of results")
):
    """Search for locations across Wikipedia and Wikivoyage"""
    try:
        # Search Wikipedia
        wiki_results = await wikimedia.search_wikipedia(query, lang, limit)
        
        # Format results
        locations = []
        for result in wiki_results:
            locations.append({
                "id": result["title"].replace(" ", "_"),
                "title": result["title"],
                "snippet": result.get("snippet", ""),
                "source": "wikipedia"
            })
        
        return {
            "query": query,
            "language": lang,
            "total": len(locations),
            "locations": locations
        }
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail="Search service unavailable")

@app.get("/api/heritage/{location_id}")
async def get_heritage_content(
    location_id: str,
    lang: str = Query("en", description="Language code (en, hi, ta, te, bn)")
):
    """Get comprehensive heritage content for a location"""
    try:
        # Convert location_id back to title
        location_title = location_id.replace("_", " ")
        
        # Fetch data from multiple sources concurrently
        wiki_content, images, wikivoyage_content = await asyncio.gather(
            wikimedia.get_article_content(location_title, lang),
            wikimedia.get_commons_images(location_title),
            wikimedia.get_wikivoyage_content(location_title, lang),
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(wiki_content, Exception):
            wiki_content = {}
        if isinstance(images, Exception):
            images = []
        if isinstance(wikivoyage_content, Exception):
            wikivoyage_content = {}
        
        # Extract key information
        heritage_data = {
            "location_id": location_id,
            "title": location_title,
            "language": lang,
            "wikipedia": {
                "extract": wiki_content.get("extract", ""),
                "coordinates": wiki_content.get("coordinates", []),
                "categories": [cat.get("title", "") for cat in wiki_content.get("categories", [])],
                "page_image": wiki_content.get("pageimage", "")
            },
            "travel_info": {
                "extract": wikivoyage_content.get("extract", ""),
                "page_image": wikivoyage_content.get("pageimage", "")
            },
            "images": images,
            "summary": {
                "heritage_facts": extract_heritage_facts(wiki_content.get("extract", "")),
                "cultural_significance": extract_cultural_info(wiki_content.get("extract", "")),
                "historical_timeline": extract_historical_dates(wiki_content.get("extract", ""))
            }
        }
        
        return heritage_data
        
    except Exception as e:
        logger.error(f"Heritage content error: {e}")
        raise HTTPException(status_code=500, detail="Heritage content service unavailable")

@app.get("/api/nearby")
async def get_nearby_heritage(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius: int = Query(10, ge=1, le=50, description="Search radius in km"),
    lang: str = Query("en", description="Language code")
):
    """Find heritage sites near given coordinates"""
    try:
        # Use Wikipedia's geosearch API
        params = {
            "action": "query",
            "format": "json",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": radius * 1000,  # Convert to meters
            "gslimit": 20,
            "gsnamespace": 0
        }
        
        wiki_lang = LANGUAGE_CODES.get(lang, "en")
        api_url = f"https://{wiki_lang}.wikipedia.org/w/api.php"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, params=params)
            data = response.json()
        
        nearby_places = []
        if "query" in data and "geosearch" in data["query"]:
            for place in data["query"]["geosearch"]:
                nearby_places.append({
                    "id": place["title"].replace(" ", "_"),
                    "title": place["title"],
                    "distance": place.get("dist", 0),
                    "coordinates": {
                        "lat": place.get("lat", 0),
                        "lon": place.get("lon", 0)
                    }
                })
        
        return {
            "center": {"lat": lat, "lon": lon},
            "radius_km": radius,
            "total": len(nearby_places),
            "places": nearby_places
        }
        
    except Exception as e:
        logger.error(f"Nearby search error: {e}")
        raise HTTPException(status_code=500, detail="Nearby search service unavailable")

def extract_heritage_facts(text: str) -> List[str]:
    """Extract interesting heritage facts from text using simple NLP"""
    if not text:
        return []
    
    facts = []
    sentences = text.split('. ')
    
    # Look for sentences with heritage-related keywords
    heritage_keywords = [
        'built', 'constructed', 'established', 'founded', 'century', 
        'ancient', 'historical', 'heritage', 'monument', 'temple',
        'fort', 'palace', 'architecture', 'dynasty', 'empire'
    ]
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 20 and any(keyword in sentence.lower() for keyword in heritage_keywords):
            facts.append(sentence + '.')
    
    return facts[:5]  # Return top 5 facts

def extract_cultural_info(text: str) -> List[str]:
    """Extract cultural significance information"""
    if not text:
        return []
    
    cultural_info = []
    sentences = text.split('. ')
    
    cultural_keywords = [
        'culture', 'tradition', 'festival', 'ritual', 'worship',
        'pilgrimage', 'sacred', 'religious', 'spiritual', 'art',
        'craft', 'music', 'dance', 'cuisine', 'custom'
    ]
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 20 and any(keyword in sentence.lower() for keyword in cultural_keywords):
            cultural_info.append(sentence + '.')
    
    return cultural_info[:3]

def extract_historical_dates(text: str) -> List[Dict[str, str]]:
    """Extract historical dates and events"""
    if not text:
        return []
    
    # Simple regex to find years and centuries
    import re
    
    timeline = []
    
    # Find 4-digit years
    year_pattern = r'\b(1[0-9]{3}|20[0-2][0-9])\b'
    years = re.findall(year_pattern, text)
    
    # Find century mentions
    century_pattern = r'\b(\d{1,2})(st|nd|rd|th)\s+century\b'
    centuries = re.findall(century_pattern, text, re.IGNORECASE)
    
    for year in set(years):
        timeline.append({
            "period": year,
            "type": "year"
        })
    
    for century, suffix in centuries:
        timeline.append({
            "period": f"{century}{suffix} century",
            "type": "century"
        })
    
    return sorted(timeline, key=lambda x: x["period"])[:5]

@app.get("/api/languages")
async def get_supported_languages():
    """Get list of supported languages"""
    return {
        "languages": [
            {"code": "en", "name": "English", "native": "English"},
            {"code": "hi", "name": "Hindi", "native": "हिंदी"},
            {"code": "ta", "name": "Tamil", "native": "தமிழ்"},
            {"code": "te", "name": "Telugu", "native": "తెలుగు"},
            {"code": "bn", "name": "Bengali", "native": "বাংলা"}
        ]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))  # Use Render's PORT env var or default to 8000
    uvicorn.run(app, host="0.0.0.0", port=port)
