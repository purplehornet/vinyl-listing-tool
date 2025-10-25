#!/usr/bin/env python3
"""
Pricing suggestion service for vinyl records
"""
import logging
import statistics
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class PricingSuggester:
    """Suggests prices for vinyl records based on market data"""
    
    def __init__(self, config, discogs_api, db_manager):
        self.config = config
        self.discogs = discogs_api
        self.db = db_manager
        
        # Grade multipliers (compared to VG+)
        self.grade_multipliers = {
            'Mint (M)': 1.4,
            'Near Mint (NM or M-)': 1.3,
            'Very Good Plus (VG+)': 1.0,  # baseline
            'Very Good (VG)': 0.7,
            'Good Plus (G+)': 0.5,
            'Good (G)': 0.3,
            'Fair (F)': 0.15,
            'Poor (P)': 0.1
        }
    
    def suggest_price(self, release_id: int, media_condition: str, sleeve_condition: str = None) -> Dict:
        """
        Suggest a price for a vinyl record based on market data
        
        Returns:
            Dict with keys: suggested_price, confidence, reasoning, market_data
        """
        try:
            # Get market data from Discogs
            market_data = self._get_market_data(release_id)
            
            if not market_data:
                return {
                    'suggested_price': None,
                    'confidence': 'low',
                    'reasoning': 'No market data available',
                    'market_data': {}
                }
            
            # Calculate base price from market data
            base_price = self._calculate_base_price(market_data)
            
            # Apply condition adjustments
            adjusted_price = self._apply_condition_adjustment(
                base_price, media_condition, sleeve_condition
            )
            
            # Determine confidence level
            confidence = self._determine_confidence(market_data)
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                market_data, base_price, adjusted_price, media_condition
            )
            
            return {
                'suggested_price': round(adjusted_price, 2) if adjusted_price else None,
                'confidence': confidence,
                'reasoning': reasoning,
                'market_data': market_data
            }
            
        except Exception as e:
            logger.error(f"Error suggesting price for release {release_id}: {e}")
            return {
                'suggested_price': None,
                'confidence': 'low',
                'reasoning': f'Error: {str(e)}',
                'market_data': {}
            }
    
    def _get_market_data(self, release_id: int) -> Dict:
        """Get market data from Discogs API"""
        try:
            # Try to get price suggestions from Discogs
            if hasattr(self.discogs, 'get_price_suggestions'):
                suggestions = self.discogs.get_price_suggestions(release_id)
                if suggestions:
                    return {
                        'source': 'discogs_suggestions',
                        'data': suggestions,
                        'sample_size': len(suggestions)
                    }
            
            # Fallback: try to get release data and estimate from similar releases
            release_data = self.discogs.get_release(release_id)
            if release_data:
                return {
                    'source': 'release_data',
                    'data': release_data,
                    'sample_size': 1
                }
                
            return {}
            
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return {}
    
    def _calculate_base_price(self, market_data: Dict) -> Optional[float]:
        """Calculate base price from market data"""
        try:
            if market_data.get('source') == 'discogs_suggestions':
                # Use Discogs price suggestions
                suggestions = market_data.get('data', {})
                prices = []
                
                for condition, price_data in suggestions.items():
                    if isinstance(price_data, dict) and 'value' in price_data:
                        prices.append(float(price_data['value']))
                    elif isinstance(price_data, (int, float)):
                        prices.append(float(price_data))
                
                if prices:
                    # Use median price as base
                    return statistics.median(prices)
            
            elif market_data.get('source') == 'release_data':
                # Estimate based on release data (this is very basic)
                release_data = market_data.get('data', {})
                
                # Very rough estimation based on year and format
                year = release_data.get('year', 2000)
                current_year = datetime.now().year
                age = current_year - year
                
                # Base price estimation (this is quite rough)
                if age > 40:
                    base_price = 25.0  # Vintage
                elif age > 20:
                    base_price = 15.0  # Classic
                elif age > 10:
                    base_price = 10.0  # Modern
                else:
                    base_price = 8.0   # Recent
                
                return base_price
            
            return None
            
        except Exception as e:
            logger.error(f"Error calculating base price: {e}")
            return None
    
    def _apply_condition_adjustment(self, base_price: float, media_condition: str, sleeve_condition: str = None) -> Optional[float]:
        """Apply condition adjustments to base price"""
        if not base_price:
            return None
            
        try:
            # Get media condition multiplier
            media_multiplier = self.grade_multipliers.get(media_condition, 0.7)  # Default to VG
            
            # Apply media condition
            adjusted_price = base_price * media_multiplier
            
            # If sleeve condition is significantly different, adjust slightly
            if sleeve_condition and sleeve_condition != media_condition:
                sleeve_multiplier = self.grade_multipliers.get(sleeve_condition, 0.7)
                # Sleeve has less impact than media - use 20% weighting
                sleeve_adjustment = (sleeve_multiplier - media_multiplier) * 0.2
                adjusted_price = adjusted_price * (1 + sleeve_adjustment)
            
            return max(adjusted_price, 1.0)  # Minimum £1
            
        except Exception as e:
            logger.error(f"Error applying condition adjustment: {e}")
            return base_price
    
    def _determine_confidence(self, market_data: Dict) -> str:
        """Determine confidence level based on market data quality"""
        if not market_data:
            return 'low'
        
        sample_size = market_data.get('sample_size', 0)
        source = market_data.get('source', '')
        
        if source == 'discogs_suggestions' and sample_size >= 5:
            return 'high'
        elif source == 'discogs_suggestions' and sample_size >= 2:
            return 'medium'
        elif source == 'release_data':
            return 'low'
        else:
            return 'very_low'
    
    def _generate_reasoning(self, market_data: Dict, base_price: float, adjusted_price: float, condition: str) -> str:
        """Generate human-readable reasoning for the price suggestion"""
        try:
            parts = []
            
            source = market_data.get('source', '')
            sample_size = market_data.get('sample_size', 0)
            
            if source == 'discogs_suggestions':
                parts.append(f"Based on {sample_size} Discogs price suggestions")
            elif source == 'release_data':
                parts.append("Estimated from release data (limited market info)")
            
            if base_price and adjusted_price:
                if abs(base_price - adjusted_price) > 0.01:
                    adjustment = ((adjusted_price / base_price) - 1) * 100
                    if adjustment > 0:
                        parts.append(f"Increased {adjustment:.0f}% for {condition} condition")
                    else:
                        parts.append(f"Reduced {abs(adjustment):.0f}% for {condition} condition")
            
            return ". ".join(parts) if parts else "Basic estimation"
            
        except Exception as e:
            logger.error(f"Error generating reasoning: {e}")
            return "Price calculated using available data"