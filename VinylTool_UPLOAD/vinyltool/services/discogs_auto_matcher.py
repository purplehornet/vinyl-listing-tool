"""
Enhanced Auto-matching helper for Deal Hunter
Uses multiple identifiers: country, label, catalog number, barcode, year
"""
from typing import Dict, List, Optional, Tuple
from vinyltool.services.discogs import DiscogsAPI
import re
import time

class DiscogsAutoMatcher:
    """Find Discogs releases for eBay items using multiple identifiers"""
    
    def __init__(self, discogs_api: DiscogsAPI, verbose: bool = False):
        self.dc = discogs_api
        self.verbose = verbose
        self.last_search = 0
        self.min_search_interval = 1.0  # Discogs rate limiting
    
    def find_best_match(self, ebay_item: Dict, format_hint: str = "Vinyl") -> Optional[Tuple[int, Dict, float]]:
        """
        Search Discogs for the best match using multiple identifiers.
        
        Returns: (release_id, release_data, confidence_score) or None
        """
        title = ebay_item.get("title", "")
        
        # Extract all possible identifiers from eBay title
        identifiers = self._extract_identifiers(title)
        
        if self.verbose:
            print(f"    🔍 Extracted: {identifiers}")
        
        if not identifiers.get("artist") or not identifiers.get("album"):
            return None
        
        # Try exact match first if we have strong identifiers
        if identifiers.get("catalog_number") or identifiers.get("barcode"):
            exact_match = self._try_exact_match(identifiers)
            if exact_match:
                return exact_match
        
        # Fall back to fuzzy search
        results = self._search_discogs(identifiers, format_hint)
        
        if not results:
            return None
        
        # Score each result using multiple factors
        scored = []
        for result in results[:15]:  # Check top 15 results
            score = self._calculate_match_score(identifiers, ebay_item, result)
            if score >= 0.70:  # Increased threshold - be more selective
                scored.append((score, result))
        
        if not scored:
            return None
        
        # Return best match
        scored.sort(reverse=True, key=lambda x: x[0])
        best_score, best_result = scored[0]
        
        release_id = best_result.get("id")
        if not release_id:
            return None
        
        # Get full release data
        try:
            release_data = self.dc.get_release(release_id)
            return (release_id, release_data, best_score)
        except Exception as e:
            if self.verbose:
                print(f"    ⚠️ Error fetching release {release_id}: {e}")
            return None
    
    def _extract_identifiers(self, title: str) -> Dict[str, Optional[str]]:
        """
        Extract multiple identifiers from eBay title.
        
        Returns dict with:
        - artist
        - album
        - year
        - country (UK, US, EU, etc.)
        - label
        - catalog_number (e.g., SHVL 804, 2C 068-04914)
        - barcode
        - pressing_note (1st press, original, etc.)
        """
        identifiers = {}
        
        # Artist and Album (from hyphen or colon separator)
        artist, album = self._parse_artist_album(title)
        identifiers["artist"] = artist
        identifiers["album"] = album
        
        # Year (4 digits: 1950-2025)
        year_match = re.search(r'\b(19[5-9]\d|20[0-2]\d)\b', title)
        identifiers["year"] = int(year_match.group(1)) if year_match else None
        
        # Country codes
        country_patterns = {
            "UK": r'\b(UK|United Kingdom|British)\b',
            "US": r'\b(US|USA|American)\b',
            "EU": r'\b(EU|Europe|European)\b',
            "DE": r'\b(German|Germany|Deutsche)\b',
            "FR": r'\b(French|France)\b',
            "JP": r'\b(Japan|Japanese)\b',
            "CA": r'\b(Canada|Canadian)\b',
            "AU": r'\b(Australia|Australian)\b',
        }
        for country, pattern in country_patterns.items():
            if re.search(pattern, title, re.IGNORECASE):
                identifiers["country"] = country
                break
        
        # Catalog number (various formats)
        # Examples: SHVL 804, 2C 068-04914, PCS 7169, ILPS 9085
        cat_patterns = [
            r'\b([A-Z]{2,4}[- ]?\d{3,6})\b',  # SHVL 804, PCS7169
            r'\b(\d[A-Z]\s?\d{3}-?\d{5})\b',  # 2C 068-04914
        ]
        for pattern in cat_patterns:
            match = re.search(pattern, title)
            if match:
                identifiers["catalog_number"] = match.group(1).replace(" ", "")
                break
        
        # Barcode (12-13 digits)
        barcode_match = re.search(r'\b(\d{12,13})\b', title)
        identifiers["barcode"] = barcode_match.group(1) if barcode_match else None
        
        # Record labels (common ones)
        labels = ["EMI", "Columbia", "Parlophone", "Capitol", "Atlantic", "Warner", 
                  "Polydor", "Island", "Virgin", "Apple", "RCA", "Decca", "Mercury"]
        for label in labels:
            if re.search(r'\b' + label + r'\b', title, re.IGNORECASE):
                identifiers["label"] = label
                break
        
        # Pressing notes
        pressing_patterns = {
            "first_press": r'\b(1st|first)\s+(press|pressing|edition)\b',
            "original": r'\b(original|orig)\s+(press|pressing)?\b',
            "reissue": r'\b(reissue|remaster|re-issue)\b',
            "promo": r'\b(promo|promotional|white label)\b',
            "test_pressing": r'\b(test pressing|TP)\b',
        }
        for key, pattern in pressing_patterns.items():
            if re.search(pattern, title, re.IGNORECASE):
                identifiers["pressing_note"] = key
                break
        
        return identifiers
    
    def _parse_artist_album(self, title: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract artist and album from title"""
        # Remove noise
        clean = title
        for noise in ["Vinyl", "LP", "12\"", "7\"", "Record", "Album", 
                      "NEW", "SEALED", "MINT", "VG", "EX", "***", "🔥"]:
            clean = re.sub(r'\b' + re.escape(noise) + r'\b', '', clean, flags=re.IGNORECASE)
        
        # Try separators
        for sep in [" - ", " – ", " — ", ":"]:
            if sep in clean:
                parts = clean.split(sep, 1)
                artist = parts[0].strip()
                album = parts[1].strip()
                
                # Clean album (remove extra info in parentheses/brackets)
                album = re.split(r'\s*[\(\[]', album)[0].strip()
                
                if len(artist) > 1 and len(album) > 1:
                    return (artist, album)
        
        return (None, None)
    
    def _try_exact_match(self, identifiers: Dict) -> Optional[Tuple[int, Dict, float]]:
        """STRICT exact match:
        - If catalog number present: require normalized equality (catno == candidate catno).
        - If barcode present: require exact barcode equality.
        - In both paths, require artist >= 0.80 and title >= 0.60.
        Returns (release_id, release_data, 0.98) on success, else None.
        """
        from difflib import SequenceMatcher
        import re as _re
        
        def _norm(x: str) -> str:
            return _re.sub(r'[^0-9A-Za-z]', '', x or '').lower()
        
        e_artist = (identifiers.get('artist') or '').strip()
        e_album  = (identifiers.get('album')  or '').strip()
        e_cat    = (identifiers.get('catalog_number') or '').strip()
        e_bar    = (identifiers.get('barcode') or '').strip()
        
        def _sim(a,b):
            a=(a or '').lower().strip(); b=(b or '').lower().strip()
            return SequenceMatcher(None, a, b).ratio() if a and b else 0.0
        
        want_cat = bool(e_cat)
        want_bar = bool(e_bar)
        if not (want_cat or want_bar):
            return None
        
        artist_min = 0.80
        title_min  = 0.60
        
        def _passes_strings(d_artist, d_title):
            a_sim = _sim(e_artist, d_artist)
            t_sim = _sim(e_album,  d_title)
            if __import__('os').getenv('VINYL_DEBUG_MATCHER') == '1':
                print(f"DEBUG exact(services): a_sim={a_sim:.2f} e='{e_artist}' d='{d_artist}'")
                print(f"DEBUG exact(services): t_sim={t_sim:.2f} e='{e_album}' d='{d_title}'")
            return (a_sim >= artist_min) and (t_sim >= title_min)
        
        # Query discogs using strong identifier(s)
        results = []
        try:
            if want_cat:
                results += list(self.dc.search_release(catalog_number=e_cat) or [])
            if want_bar:
                results += list(self.dc.search_release(barcode=e_bar) or [])
        except Exception:
            results = []
        
        for res in results:
            d_title  = (res.get('title') or '')
            d_artist = (res.get('artist') or res.get('artists_sort') or '')
            d_cat    = (res.get('catno') or '').strip()
            d_bar    = (res.get('barcode') or '').strip()
        
            ok = True
            if want_cat:
                equal = _norm(e_cat) == _norm(d_cat)
                if __import__('os').getenv('VINYL_DEBUG_MATCHER') == '1':
                    print(f"DEBUG exact(services): catno e='{e_cat}' d='{d_cat}' equal={equal} id={res.get('id')}")
                if not equal:
                    ok = False
        
            if want_bar and ok:
                if not e_bar or not d_bar or e_bar != d_bar:
                    if __import__('os').getenv('VINYL_DEBUG_MATCHER') == '1':
                        print(f"DEBUG exact(services): barcode mismatch e='{e_bar}' d='{d_bar}'")
                    ok = False
        
            if ok and not _passes_strings(d_artist, d_title):
                ok = False
        
            if not ok:
                continue
        
            rid = res.get('id')
            if rid:
                try:
                    rdata = self.dc.get_release(rid)
                except Exception:
                    rdata = None
                return (rid, rdata, 0.98)
        
        return None
        if __import__('os').getenv('VINYL_DEBUG_MATCHER') == '1':
            print('DEBUG exact(services): disabled fast-path; returning None')
        return None  # disabled_exact_services
        """Try exact match using catalog number or barcode"""
        # Catalog number search
        if identifiers.get("catalog_number"):
            results = self._search_by_catno(identifiers["catalog_number"])
            if results:
                # High confidence if catalog number matches
                result = results[0]
                release_id = result.get("id")
                if release_id:
                    release_data = self.dc.get_release(release_id)
                    return (release_id, release_data, 0.95)
        
        # Barcode search
        if identifiers.get("barcode"):
            results = self._search_by_barcode(identifiers["barcode"])
            if results:
                result = results[0]
                release_id = result.get("id")
                if release_id:
                    release_data = self.dc.get_release(release_id)
                    return (release_id, release_data, 0.98)  # Very high confidence
        
        return None
    
    def _search_by_catno(self, catno: str) -> List[Dict]:
        """Search by catalog number"""
        self._rate_limit()
        try:
            results = self.dc.search({"catno": catno, "type": "release"})
            return results if isinstance(results, list) else results.get("results", [])
        except:
            return []
    
    def _search_by_barcode(self, barcode: str) -> List[Dict]:
        """Search by barcode"""
        self._rate_limit()
        try:
            results = self.dc.search({"barcode": barcode, "type": "release"})
            return results if isinstance(results, list) else results.get("results", [])
        except:
            return []
    
    def _search_discogs(self, identifiers: Dict, format_hint: str) -> List[Dict]:
        """Search Discogs using available identifiers"""
        self._rate_limit()
        
        artist = identifiers.get("artist", "") or ""
        album = identifiers.get("album", "") or ""
        
        # Build structured search parameters when artist/album are available.
        # Using structured fields typically yields more precise results than a generic query.
        search_params = {"type": "release"}
        
        # Only include year if present and not zero
        year_value = identifiers.get("year")
        if year_value:
            search_params["year"] = year_value
        
        # Add country filter if present
        if identifiers.get("country"):
            search_params["country"] = identifiers["country"]
        
        # Use structured artist and release_title parameters when available
        if artist:
            search_params["artist"] = artist
        if album:
            search_params["release_title"] = album
        
        # If both artist and album are missing, fall back to generic query
        if not (artist or album):
            query_terms = ""
            # Combine whatever identifiers we have into a query string
            if artist:
                query_terms += artist + " "
            if album:
                query_terms += album + " "
            if year_value:
                query_terms += str(year_value)
            # Default to identifiers['title'] if present
            search_params["q"] = query_terms.strip()

        try:
            results = self.dc.search(search_params)
            return results if isinstance(results, list) else results.get("results", [])
        except Exception as e:
            if self.verbose:
                print(f"    ⚠️ Search error: {e}")
            return []
    
    def _calculate_match_score(self, identifiers: Dict, ebay_item: Dict, 
                                discogs_result: Dict) -> float:
        """
        Calculate match confidence using multiple factors.
        
        CRITICAL: Artist and Album must have reasonable similarity or score is 0.
        
        Scoring breakdown:
        - Artist name match: 30% (REQUIRED >= 60% similarity)
        - Album title match: 30% (REQUIRED >= 60% similarity)
        - Year match: 15%
        - Country match: 10%
        - Format match: 5%
        - Catalog number: 10%
        
        Returns: 0.0 - 1.0 confidence score
        """
        from difflib import SequenceMatcher
        
        score = 0.0
        
        ebay_title = ebay_item.get("title", "").lower()
        
        # Extract artist and album from identifiers
        artist = identifiers.get("artist", "").lower().strip()
        album = identifiers.get("album", "").lower().strip()
        
        # Get Discogs title and attempt to parse artist and album separately
        discogs_title = discogs_result.get("title", "").lower()
        discogs_artist = ""
        discogs_album = ""

        # Discogs search results often embed "Artist - Album" in the title.
        # Attempt to split on common separators. If no separator found,
        # treat the entire title as the album name and leave artist empty.
        # We check " - " first as that is the standard separator used by Discogs API.
        # Note: do not override parsed values later to avoid losing parsed data.
        if discogs_title:
            # Attempt split by common separators
            for sep in [" - ", " – ", " — "]:
                if sep in discogs_title:
                    parts = discogs_title.split(sep, 1)
                    discogs_artist = parts[0].strip()
                    discogs_album = parts[1].strip()
                    break
            else:
                # No separator found; entire title is treated as album
                discogs_album = discogs_title.strip()

        # Fallbacks: if artist still empty, try dedicated fields
        if not discogs_artist:
            if discogs_result.get("artist"):
                discogs_artist = str(discogs_result.get("artist", "")).lower().strip()
            elif discogs_result.get("artists"):
                # Full release object has artists list
                first_artist = discogs_result["artists"][0]
                if isinstance(first_artist, dict):
                    discogs_artist = first_artist.get("name", "").lower().strip()
                else:
                    discogs_artist = str(first_artist).lower().strip()

        # Fallback: if album still empty, use title
        if not discogs_album:
            discogs_album = discogs_title.strip()

        # Compute artist and album similarities using SequenceMatcher
        artist_similarity = 0.0
        album_similarity = 0.0
        if artist and discogs_artist:
            artist_similarity = SequenceMatcher(None, artist, discogs_artist).ratio()
        if album and discogs_album:
            album_similarity = SequenceMatcher(None, album, discogs_album).ratio()

        # Debug logging when enabled via environment variable
        import os
        if os.getenv("VINYL_DEBUG_MATCHER") == "1":
            print(f"DEBUG: Candidate id={discogs_result.get('id')}, eBay artist='{artist}', Discogs artist='{discogs_artist}', artist_similarity={artist_similarity:.3f}")
            print(f"DEBUG: Candidate id={discogs_result.get('id')}, eBay album='{album}', Discogs album='{discogs_album}', album_similarity={album_similarity:.3f}")

        # 1. CRITICAL: Artist name match (30 points) - REQUIRED
        if artist:
            if discogs_artist and artist_similarity >= 0.6:
                score += artist_similarity * 0.30
            elif discogs_artist:
                # Artist doesn't match well enough - reject this match
                if os.getenv("VINYL_DEBUG_MATCHER") == "1":
                    print("DEBUG: Artist similarity below threshold; rejecting candidate.")
                return 0.0
            else:
                # Discogs artist missing; cannot verify
                score += 0.05
        else:
            # No eBay artist extracted - can't verify, be cautious
            score += 0.05

        # 2. CRITICAL: Album title match (30 points) - REQUIRED
        if album:
            if discogs_album and album_similarity >= 0.6:
                score += album_similarity * 0.30
            elif discogs_album:
                # Album doesn't match well enough - reject this match
                if os.getenv("VINYL_DEBUG_MATCHER") == "1":
                    print("DEBUG: Album similarity below threshold; rejecting candidate.")
                return 0.0
            else:
                # Discogs album missing; cannot verify
                score += 0.05
        else:
            # No album extracted - can't verify, be cautious
            score += 0.05
        
        # If we got here, artist and album passed minimum requirements
        # Now add bonus points for other matching fields
        
        # 3. Year match (15 points)
        year_points = 0.0
        if identifiers.get("year") and discogs_result.get("year"):
            try:
                disc_year = int(discogs_result.get("year", 0))
            except Exception:
                disc_year = 0
            if disc_year:
                year_diff = abs(identifiers["year"] - disc_year)
                if year_diff == 0:
                    year_points = 0.15
                elif year_diff == 1:
                    year_points = 0.10
                elif year_diff <= 2:
                    year_points = 0.05
        score += year_points

        # 4. Country match (10 points)
        country_points = 0.0
        if identifiers.get("country"):
            discogs_country = discogs_result.get("country", "")
            if identifiers["country"] == discogs_country:
                country_points = 0.10
            elif discogs_country in ["Europe", "EU"] and identifiers["country"] in ["UK", "DE", "FR"]:
                country_points = 0.05  # Partial match
        score += country_points

        # 5. Format match (5 points)
        format_points = 0.0
        discogs_formats = [f.lower() for f in discogs_result.get("format", [])]
        if any(("lp" in f) or ("vinyl" in f) for f in discogs_formats):
            if ("vinyl" in ebay_title) or ("lp" in ebay_title):
                format_points = 0.05
        score += format_points

        # 6. Catalog number match (10 points)
        catno_points = 0.0
        if identifiers.get("catalog_number"):
            discogs_catno = str(discogs_result.get("catno", "")).replace(" ", "").lower()
            ebay_catno = identifiers["catalog_number"].lower()
            if ebay_catno and discogs_catno:
                # Exact or substring match yields points
                if ebay_catno == discogs_catno or ebay_catno in discogs_catno or discogs_catno in ebay_catno:
                    catno_points = 0.10
                else:
                    # Conflict: if both exist but don't match at all, heavily penalize by rejecting
                    if os.getenv("VINYL_DEBUG_MATCHER") == "1":
                        print("DEBUG: Catalog numbers conflict; rejecting candidate.")
                    return 0.0
        score += catno_points

        # Debug summary of scoring factors
        if os.getenv("VINYL_DEBUG_MATCHER") == "1":
            print(
                f"DEBUG: Candidate id={discogs_result.get('id')} scoring details -> "
                f"year_points={year_points:.3f}, country_points={country_points:.3f}, "
                f"format_points={format_points:.3f}, catno_points={catno_points:.3f}, total_score={score:.3f}"
            )

        return score

    def _rate_limit(self):
        """Respect Discogs rate limits"""
        elapsed = time.time() - self.last_search
        if elapsed < self.min_search_interval:
            time.sleep(self.min_search_interval - elapsed)
        self.last_search = time.time()
