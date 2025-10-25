"""
Smart Matcher - Intelligent eBay to Discogs Release Matching
Prevents false positives from bundles, wrong formats, and mismatches
"""
from __future__ import annotations
from difflib import SequenceMatcher
import re
from typing import Dict, Tuple, Optional

class SmartMatcher:
    """Validates eBay listing against Discogs release"""
    
    # Phase 1: Pre-filter reject patterns
    BUNDLE_KEYWORDS = [
        'lot', 'bundle', 'job lot', 'collection', 
        'box set', 'boxset', 'box-set'
    ]
    
    MULTI_ALBUM_INDICATORS = ['&', ' + ']  # Only clear indicators, not 'and'
    
    DAMAGED_KEYWORDS = [
        'spares', 'repair', 'case only', 'inlay only', 
        'cover only', 'for parts', 'not working', 'damaged'
    ]
    
    # Phase 2: Format mappings
    EBAY_FORMAT_TERMS = {
        'cassette': ['cassette', 'tape', 'mc'],
        'vinyl': ['vinyl', 'lp', '12"', '12 inch', '7"', '7 inch', 'record'],
        'cd': ['cd', 'compact disc']
    }
    
    DISCOGS_FORMAT_TERMS = {
        'cassette': 'Cassette',
        'vinyl': 'Vinyl',
        'cd': 'CD'
    }
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.rejection_reasons = []
        
    def match(
        self, 
        ebay_item: Dict, 
        discogs_release: Dict,
        discogs_title: str
    ) -> Tuple[bool, float, list]:
        """
        Match eBay item against Discogs release
        
        Returns:
            (is_valid, confidence_score, rejection_reasons)
        """
        self.rejection_reasons = []
        confidence = 100.0
        
        ebay_title = ebay_item.get('title', '').lower()
        ebay_price = ebay_item.get('price', 0)
        
        # PHASE 1: Pre-filter
        if not self._phase1_prefilter(ebay_title):
            return False, 0.0, self.rejection_reasons
        
        # PHASE 2: Format validation
        format_match, format_confidence = self._phase2_format_validation(
            ebay_title, 
            discogs_release.get('format', '')
        )
        if not format_match:
            return False, 0.0, self.rejection_reasons
        confidence *= format_confidence
        
        # PHASE 3: Title fuzzy matching
        title_match, title_confidence = self._phase3_title_matching(
            ebay_title,
            discogs_title
        )
        if not title_match:
            return False, 0.0, self.rejection_reasons
        confidence *= title_confidence
        
        # PHASE 4: Price sanity check (warning only, not rejection)
        price_warning = self._phase4_price_sanity(
            ebay_price,
            discogs_release.get('median_price', 0)
        )
        if price_warning:
            self.rejection_reasons.append(f"WARNING: {price_warning}")
            confidence *= 0.9
        
        return True, confidence / 100, self.rejection_reasons
    
    def _phase1_prefilter(self, ebay_title: str) -> bool:
        """Reject obvious non-matches"""
        
        for keyword in self.BUNDLE_KEYWORDS:
            if keyword in ebay_title:
                self.rejection_reasons.append(
                    f"REJECT: Bundle indicator found: '{keyword}'"
                )
                return False
        
        for indicator in self.MULTI_ALBUM_INDICATORS:
            if indicator in ebay_title:
                self.rejection_reasons.append(
                    f"REJECT: Multiple albums detected: '{indicator}' found"
                )
                return False
        
        for keyword in self.DAMAGED_KEYWORDS:
            if keyword in ebay_title:
                self.rejection_reasons.append(
                    f"REJECT: Damaged/incomplete indicator: '{keyword}'"
                )
                return False
        
        return True
    
    def _phase2_format_validation(
        self, 
        ebay_title: str, 
        discogs_format: str
    ) -> Tuple[bool, float]:
        """Validate format matches"""
        
        ebay_format = None
        for format_type, terms in self.EBAY_FORMAT_TERMS.items():
            if any(term in ebay_title for term in terms):
                ebay_format = format_type
                break
        
        if not ebay_format:
            self.rejection_reasons.append(
                "WARNING: Could not detect format from eBay title"
            )
            return True, 0.8
        
        required_discogs_term = self.DISCOGS_FORMAT_TERMS.get(ebay_format)
        if required_discogs_term and required_discogs_term not in discogs_format:
            self.rejection_reasons.append(
                f"REJECT: Format mismatch: eBay '{ebay_format}' vs Discogs '{discogs_format}'"
            )
            return False, 0.0
        
        if self.verbose:
            print(f"Format match: {ebay_format}")
        
        return True, 1.0
    
    def _phase3_title_matching(
        self, 
        ebay_title: str, 
        discogs_title: str,
        threshold: float = 0.70
    ) -> Tuple[bool, float]:
        """Fuzzy match titles"""
        
        ebay_clean = self._clean_title(ebay_title)
        discogs_clean = self._clean_title(discogs_title.lower())
        
        similarity = SequenceMatcher(None, ebay_clean, discogs_clean).ratio()
        
        if similarity < threshold:
            self.rejection_reasons.append(
                f"REJECT: Title similarity too low: {similarity*100:.1f}% (threshold {threshold*100:.0f}%)"
            )
            self.rejection_reasons.append(
                f"  eBay: '{ebay_clean}'"
            )
            self.rejection_reasons.append(
                f"  Discogs: '{discogs_clean}'"
            )
            return False, 0.0
        
        if self.verbose:
            print(f"Title match: {similarity*100:.1f}%")
        
        return True, similarity
    
    def _phase4_price_sanity(
        self, 
        ebay_price: float, 
        discogs_price: float
    ) -> Optional[str]:
        """Check for suspicious pricing"""
        
        if not discogs_price or discogs_price == 0:
            return None
        
        ratio = ebay_price / discogs_price
        
        if ratio < 0.10:
            return f"Suspiciously cheap: GBP{ebay_price:.2f} vs GBP{discogs_price:.2f} ({ratio*100:.0f}%)"
        
        if ratio > 1.50:
            return f"Overpriced: GBP{ebay_price:.2f} vs GBP{discogs_price:.2f} ({ratio*100:.0f}%)"
        
        if ratio < 0.50:
            return f"Very cheap: GBP{ebay_price:.2f} vs GBP{discogs_price:.2f} ({ratio*100:.0f}%) - verify item"
        
        return None
    
    def _clean_title(self, title: str) -> str:
        """Clean title for comparison"""
        
        title = title.lower()
        
        noise = [
            'vinyl', 'lp', 'cassette', 'tape', 'cd', 'album', 
            '12"', '7"', 'inch', 'record', 'the', 'a', 'an'
        ]
        for word in noise:
            title = title.replace(word, ' ')
        
        title = re.sub(r'\b[a-z]*\d+[a-z]*\b', '', title)
        title = re.sub(r'\b(19|20)\d{2}\b', '', title)
        title = re.sub(r'[^\w\s]', ' ', title)
        title = ' '.join(title.split())
        
        return title.strip()
