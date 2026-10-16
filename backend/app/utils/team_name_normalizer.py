"""Team name normalization utilities for matching external provider names.

Handles Turkish characters, club suffixes, and common variations.
"""

import re
from typing import Tuple


def normalize_team_name(name: str) -> str:
    """Normalize team name for comparison.
    
    Args:
        name: Team name to normalize
        
    Returns:
        Normalized name (lowercase, no special chars, no suffixes)
    """
    if not name:
        return ""
    
    # Convert to lowercase
    normalized = name.lower()
    
    # Turkish character normalization
    turkish_map = {
        'ç': 'c', 'ğ': 'g', 'ı': 'i', 'İ': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
        'Ç': 'c', 'Ğ': 'g', 'Ö': 'o', 'Ş': 's', 'Ü': 'u'
    }
    for turkish, latin in turkish_map.items():
        normalized = normalized.replace(turkish, latin)
    
    # Remove common club suffixes and prefixes (but preserve team-specific names)
    suffixes = [
        r'\s+fc$', r'\s+fk$', r'\s+sk$', r'\s+as$', r'\s+aş$', r'\s+jk$',
        r'\s+kulübü$', r'\s+kulubu$', r'\s+spor$',
        r'\s+football\s+club$', r'\s+futbol\s+kulübü$',
        r'\s+ac$', r'\s+cf$', r'\s+sc$'
        # Removed 'united' and 'city' as they are often part of team names
    ]
    for suffix in suffixes:
        normalized = re.sub(suffix, '', normalized)
    
    # Remove common prefixes
    prefixes = [r'^fc\s+', r'^fk\s+', r'^sk\s+', r'^ac\s+', r'^cf\s+']
    for prefix in prefixes:
        normalized = re.sub(prefix, '', normalized)
    
    # Remove punctuation and extra spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def teams_match(name1: str, name2: str, threshold: float = 0.6) -> bool:
    """Check if two team names match.
    
    Args:
        name1: First team name
        name2: Second team name
        threshold: Similarity threshold (0-1)
        
    Returns:
        True if names match
    """
    norm1 = normalize_team_name(name1)
    norm2 = normalize_team_name(name2)
    
    if not norm1 or not norm2:
        return False
    
    # Exact match after normalization
    if norm1 == norm2:
        return True
    
    # One contains the other
    if norm1 in norm2 or norm2 in norm1:
        # Check similarity to avoid false positives like "Manchester" matching "Manchester United" and "Manchester City"
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if not words1 or not words2:
            return False
        
        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return False
        
        similarity = intersection / union
        return similarity >= threshold
    
    return False


def extract_key_words(name: str) -> set:
    """Extract key words from team name for matching.
    
    Args:
        name: Team name
        
    Returns:
        Set of key words
    """
    normalized = normalize_team_name(name)
    
    # Remove common words that don't help matching
    stop_words = {'de', 'del', 'la', 'le', 'los', 'las', 'the', 'of', 'and', 'real', 'athletic'}
    
    words = normalized.split()
    key_words = {w for w in words if w not in stop_words and len(w) > 2}
    
    return key_words


def calculate_team_similarity(name1: str, name2: str) -> float:
    """Calculate similarity score between two team names.
    
    Args:
        name1: First team name
        name2: Second team name
        
    Returns:
        Similarity score (0-1)
    """
    words1 = extract_key_words(name1)
    words2 = extract_key_words(name2)
    
    if not words1 or not words2:
        return 0.0
    
    # Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


# Common team name mappings (can be extended)
TEAM_NAME_ALIASES = {
    'galatasaray': ['galatasaray sk', 'galatasaray as'],
    'fenerbahce': ['fenerbahce sk', 'fenerbahçe'],
    'besiktas': ['besiktas jk', 'beşiktaş'],
    'trabzonspor': ['trabzonspor as', 'trabzonspor kulübü'],
    'manchester united': ['man united', 'manchester utd', 'man utd'],
    'manchester city': ['man city'],
    'tottenham': ['tottenham hotspur', 'spurs'],
    'newcastle': ['newcastle united'],
    'west ham': ['west ham united'],
    'brighton': ['brighton and hove albion', 'brighton & hove albion'],
    'wolves': ['wolverhampton', 'wolverhampton wanderers'],
}


def get_canonical_name(name: str) -> str:
    """Get canonical team name if alias is found.
    
    Args:
        name: Team name to canonicalize
        
    Returns:
        Canonical name or original if not found
    """
    normalized = normalize_team_name(name)
    
    # Check if it's a canonical name
    if normalized in TEAM_NAME_ALIASES:
        return normalized
    
    # Check if it's an alias
    for canonical, aliases in TEAM_NAME_ALIASES.items():
        for alias in aliases:
            if normalize_team_name(alias) == normalized:
                return canonical
    
    return normalized
