from __future__ import annotations
from typing import *
from typing import Tuple
from vinyltool.core.logging import setup_logging
logger = setup_logging('parse')
import re

# Extracted helpers

def _extract_barcode_and_cat_no(app, release_data: dict) -> Tuple[str, str]:

    """
    Extracts and robustly separates barcodes from catalog numbers from Discogs release data.
    """
    if not release_data:
        return "", ""

    explicit_barcodes = {
        identifier.get('value', '').strip()
        for identifier in release_data.get('identifiers', [])
        if identifier.get('type', '').lower() == 'barcode' and identifier.get('value')
    }

    barcode_pattern = re.compile(r'^\s*[\d\s]{10,13}\s*$')

    potential_cat_nos = {
        label.get('catno', '').strip()
        for label in release_data.get('labels', [])
        if label.get('catno') and label.get('catno', '').strip().lower() != 'none'
    }

    heuristic_barcodes = {pcn for pcn in potential_cat_nos if barcode_pattern.match(pcn)}
    
    true_cat_nos = potential_cat_nos - explicit_barcodes - heuristic_barcodes
    
    all_barcodes = explicit_barcodes.union(heuristic_barcodes)

    main_barcode = sorted(list(explicit_barcodes))[0] if explicit_barcodes else \
                   sorted(list(all_barcodes))[0] if all_barcodes else ""

    if not true_cat_nos and potential_cat_nos:
         final_cat_nos = potential_cat_nos - all_barcodes
    else:
         final_cat_nos = true_cat_nos
    
    final_cat_no_str = ", ".join(sorted(list(final_cat_nos)))

    return main_barcode.replace(" ", ""), final_cat_no_str




def _extract_matrix_info(release_data: dict) -> str:
        """
        [NEW & ROBUST] Extracts matrix/runout information from a Discogs release.
        It prioritizes the structured `identifiers` field and falls back to parsing
        the unstructured `notes` field if necessary.
        """
        if not release_data:
            return ""

        # --- Stage 1: Prioritize the structured `identifiers` field ---
        structured_matrix = []
        for identifier in release_data.get('identifiers', []):
            if identifier.get('type') == 'Matrix / Runout':
                desc = identifier.get('description', '').strip()
                value = identifier.get('value', '').strip()
                if value:
                    # Format nicely: "Side A, variant 1: XXX-123"
                    line = f"{desc}: {value}" if desc else value
                    structured_matrix.append(line)
        
        if structured_matrix:
            logger.info(f"Found {len(structured_matrix)} structured matrix entries.")
            return "\n".join(structured_matrix)

        # --- Stage 2: Fallback to parsing the unstructured `notes` field ---
        logger.info("No structured matrix data found, falling back to parsing 'notes' field.")
        notes_text = release_data.get('notes', '')
        if not notes_text:
            return ""

        lines = notes_text.splitlines()
        matrix_lines = []
        in_matrix_block = False

        # Keywords that indicate a line is likely matrix/runout info
        matrix_keywords = ['matrix', 'runout', 'etched', 'stamped', 'side a', 'side b', 'side c', 'side d']

        for line in lines:
            line_lower = line.lower().strip()
            if not line_lower:
                in_matrix_block = False  # Blank line ends a block
                continue

            # Check for the explicit "Matrix / Runout:" header
            if line_lower.startswith('matrix / runout'):
                in_matrix_block = True
                # Add the line itself, but strip the label
                matrix_part = line.split(':', 1)[-1].strip()
                if matrix_part:
                    matrix_lines.append(matrix_part)
                continue

            if in_matrix_block:
                matrix_lines.append(line.strip())
            else:
                # Check if a line contains any of our keywords, but not as part of a larger word
                if any(re.search(r'\b' + re.escape(kw) + r'\b', line_lower) for kw in matrix_keywords):
                    matrix_lines.append(line.strip())

        return "\n".join(matrix_lines).strip()

