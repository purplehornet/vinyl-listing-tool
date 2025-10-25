"""
VinylTool Validation
====================
Validation functions for listing data.
"""
from typing import List
from vinyltool.core.config import Config

def validate_listing(target: str, record: dict, config: Config = None) -> List[str]:
    """
    Validate a record for publishing to a target platform
    
    Args:
        target: Platform name ('ebay' or 'discogs')
        record: Record dictionary containing listing data
        config: Configuration object
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    config = config or cfg
    
    # Common validations
    required_fields = ["artist", "title", "format", "media_condition"]
    for field in required_fields:
        value = str(record.get(field, "")).strip() if record.get(field) else ""
        if not value:
            errors.append(f"Missing {field.replace('_', ' ')}")
    
    # Price validation
    try:
        price = float(record.get("price", 0))
        if price <= 0:
            errors.append("Price must be greater than 0")
    except (TypeError, ValueError):
        errors.append("Price must be a valid number")
    
    # Target-specific validations
    if target.lower() == "ebay":
        if not record.get("categoryId") and not record.get("category_id"):
            errors.append("Missing eBay category")
        
        # Check for required policy IDs
        if not config.get("ebay_payment_policy_id"):
            errors.append("Missing eBay payment policy ID in configuration")
        if not config.get("ebay_return_policy_id"):
            errors.append("Missing eBay return policy ID in configuration")
        if not config.get("ebay_shipping_policy_id"):
            errors.append("Missing eBay shipping policy ID in configuration")
    
    elif target.lower() == "discogs":
        if not record.get("discogs_release_id"):
            errors.append("No Discogs release linked")
        
        media_condition = record.get("media_condition", "")
        if media_condition not in REVERSE_GRADE_MAP:
            errors.append("Invalid media condition for Discogs")
    
    return errors

