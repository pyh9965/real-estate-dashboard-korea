"""
Region Code Mapper Module

This module provides mapping functionality for Korean administrative region codes
to human-readable region names. It focuses on Seoul metropolitan area districts.

Reference: https://www.code.go.kr (Administrative Standard Code Management System)
Region codes are the first 5 digits of the 10-digit legal dong code.
"""

from typing import Dict
import warnings


# Seoul metropolitan area region codes (5-digit sggCd)
# Format: {region_code: "시도명 시군구명"}
REGION_CODE_MAP: Dict[str, str] = {
    # Seoul (서울특별시) - 25 districts
    "11110": "서울특별시 종로구",
    "11140": "서울특별시 중구",
    "11170": "서울특별시 용산구",
    "11200": "서울특별시 성동구",
    "11215": "서울특별시 광진구",
    "11230": "서울특별시 동대문구",
    "11260": "서울특별시 중랑구",
    "11290": "서울특별시 성북구",
    "11305": "서울특별시 강북구",
    "11320": "서울특별시 도봉구",
    "11350": "서울특별시 노원구",
    "11380": "서울특별시 은평구",
    "11410": "서울특별시 서대문구",
    "11440": "서울특별시 마포구",
    "11470": "서울특별시 양천구",
    "11500": "서울특별시 강서구",
    "11530": "서울특별시 구로구",
    "11545": "서울특별시 금천구",
    "11560": "서울특별시 영등포구",
    "11590": "서울특별시 동작구",
    "11620": "서울특별시 관악구",
    "11650": "서울특별시 서초구",
    "11680": "서울특별시 강남구",
    "11710": "서울특별시 송파구",
    "11740": "서울특별시 강동구",
}


def get_sigungu_name(code: str) -> str:
    """
    Convert a 5-digit region code to its corresponding region name.

    Args:
        code: 5-digit region code (e.g., '11380')

    Returns:
        Region name (e.g., '서울특별시 은평구')
        If the code is not found in the mapping, returns the code as-is
        and logs a warning.

    Examples:
        >>> get_sigungu_name('11380')
        '서울특별시 은평구'
        >>> get_sigungu_name('11110')
        '서울특별시 종로구'
        >>> get_sigungu_name('99999')  # Unknown code
        '99999'
    """
    if code is None:
        return ""

    # Ensure code is a string and strip whitespace
    code_str = str(code).strip()

    # Handle potential float conversion issues (e.g., 11380.0 -> 11380)
    if "." in code_str:
        code_str = code_str.split(".")[0]

    # Look up the region name
    region_name = REGION_CODE_MAP.get(code_str)

    if region_name is None:
        warnings.warn(
            f"Region code '{code_str}' not found in mapping table. "
            f"Using code as-is. Consider updating REGION_CODE_MAP.",
            UserWarning
        )
        return code_str

    return region_name


def get_all_region_codes() -> Dict[str, str]:
    """
    Get all available region codes and their names.

    Returns:
        Dictionary of region codes to region names.
    """
    return REGION_CODE_MAP.copy()


def is_valid_region_code(code: str) -> bool:
    """
    Check if a region code exists in the mapping table.

    Args:
        code: Region code to check

    Returns:
        True if the code exists in the mapping, False otherwise.
    """
    if code is None:
        return False

    code_str = str(code).strip()
    if "." in code_str:
        code_str = code_str.split(".")[0]

    return code_str in REGION_CODE_MAP
