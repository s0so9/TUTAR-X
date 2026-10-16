"""Inspect FotMob API response structure for statistics extraction."""
import httpx
import json

# Fetch a real finished match
match_id = "4193741"
response = httpx.get(f"https://www.fotmob.com/api/data/matchDetails?matchId={match_id}")
data = response.json()

print("=== TOP LEVEL KEYS ===")
print(list(data.keys()))

print("\n=== CONTENT KEYS ===")
content = data.get("content", {})
print(list(content.keys()))

print("\n=== STATS STRUCTURE ===")
stats = content.get("stats", {})
periods = stats.get("Periods", {})
all_period = periods.get("All", {})
stat_groups = all_period.get("stats", [])

print(f"Number of stat groups: {len(stat_groups)}")

# Extract all stats
all_stats = {}
for group in stat_groups:
    group_title = group.get("title", "Unknown")
    group_stats = group.get("stats", [])
    
    for stat in group_stats:
        key = stat.get("key")
        title = stat.get("title")
        raw_stats = stat.get("rawStats", [])
        
        if len(raw_stats) >= 2 and raw_stats[0] and raw_stats[1]:
            home_value = raw_stats[0].get("value")
            away_value = raw_stats[1].get("value")
            all_stats[key] = {
                "title": title,
                "home": home_value,
                "away": away_value
            }

print("\n=== EXTRACTED STATS ===")
for key, values in all_stats.items():
    print(f"{key:30} {values['title']:30} H:{values['home']} A:{values['away']}")

print("\n=== SHOTMAP STRUCTURE ===")
shotmap = content.get("shotmap", {})
if shotmap:
    print("Shotmap keys:", list(shotmap.keys()))
    shots = shotmap.get("shots", [])
    print(f"Total shots: {len(shots)}")
    if shots:
        print("\nFirst shot sample:")
        print(json.dumps(shots[0], indent=2))
