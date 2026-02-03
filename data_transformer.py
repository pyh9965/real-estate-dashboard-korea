"""
Data Transformer Module

This module provides functionality to transform new MOLIT API format Excel data
to the legacy format expected by the apartment real transaction dashboard.

The new MOLIT API format (released 2024-07-17) uses different column names
and data structures compared to the legacy format. This module provides
transparent transformation to maintain backward compatibility.
"""

import pandas as pd
import warnings
from typing import Literal

from region_code_mapper import get_sigungu_name


# Column mapping from new API format to legacy format
NEW_API_COLUMNS = {
    "sggCd",       # Region code (5 digits)
    "umdNm",       # Legal dong name
    "aptNm",       # Apartment name
    "excluUseAr",  # Exclusive area (sq meters)
    "dealYear",    # Transaction year
    "dealMonth",   # Transaction month
    "dealDay",     # Transaction day
    "dealAmount",  # Transaction amount (with commas)
    "floor",       # Floor number
    "buildYear",   # Year built
    "cdealDay",    # Cancellation date (if applicable)
}

LEGACY_COLUMNS = {
    "NO",              # Row number
    "시군구",           # Region name
    "단지명",           # Apartment name
    "전용면적(㎡)",     # Exclusive area
    "계약년월",         # Contract year-month (YYYYMM)
    "계약일",           # Contract day
    "거래금액(만원)",   # Transaction amount
    "층",              # Floor
    "건축년도",         # Year built
    "해제사유발생일",   # Cancellation date
}


def detect_format(df: pd.DataFrame) -> Literal["old", "new"]:
    """
    Detect the format of the input DataFrame.

    The function checks for the presence of specific columns to determine
    whether the data is in the legacy format or the new MOLIT API format.

    Args:
        df: DataFrame loaded from an Excel file

    Returns:
        'old': Legacy format (columns like 시군구, 단지명, 거래금액(만원))
        'new': New MOLIT API format (columns like sggCd, aptNm, dealAmount)

    Raises:
        ValueError: If the format cannot be determined (unknown column structure)

    Examples:
        >>> df_old = pd.DataFrame({'시군구': [], '단지명': [], '거래금액(만원)': []})
        >>> detect_format(df_old)
        'old'
        >>> df_new = pd.DataFrame({'sggCd': [], 'aptNm': [], 'dealAmount': []})
        >>> detect_format(df_new)
        'new'
    """
    columns = set(df.columns)

    # Check for legacy format indicators
    legacy_indicators = {"시군구", "단지명", "거래금액(만원)"}
    if legacy_indicators.issubset(columns):
        return "old"

    # Check for new API format indicators
    new_api_indicators = {"sggCd", "aptNm", "dealAmount"}
    if new_api_indicators.issubset(columns):
        return "new"

    # If neither format is detected, raise an error with helpful message
    available_cols = ", ".join(sorted(columns)[:10])
    if len(columns) > 10:
        available_cols += f", ... ({len(columns) - 10} more)"

    raise ValueError(
        f"Unable to determine file format. "
        f"Expected either legacy format columns (시군구, 단지명, 거래금액(만원)) "
        f"or new API format columns (sggCd, aptNm, dealAmount). "
        f"Found columns: {available_cols}"
    )


def transform_to_legacy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform new MOLIT API format DataFrame to legacy format.

    This function performs the following transformations:
    - NO: Generate row numbers (1-based index)
    - 시군구: Combine sggCd lookup + umdNm (e.g., "서울특별시 은평구 불광동")
    - 단지명: Direct mapping from aptNm
    - 전용면적(㎡): Direct mapping from excluUseAr
    - 계약년월: Combine dealYear + dealMonth as YYYYMM
    - 계약일: Direct mapping from dealDay
    - 거래금액(만원): Remove commas from dealAmount and convert to integer
    - 층: Direct mapping from floor
    - 건축년도: Direct mapping from buildYear
    - 해제사유발생일: Direct mapping from cdealDay

    Args:
        df: DataFrame in new MOLIT API format

    Returns:
        DataFrame transformed to legacy format

    Raises:
        KeyError: If required columns are missing from the input DataFrame
    """
    # Verify required columns exist
    required_columns = ["sggCd", "aptNm", "excluUseAr", "dealYear", "dealMonth",
                        "dealDay", "dealAmount", "floor", "buildYear"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise KeyError(
            f"Missing required columns for transformation: {missing_columns}. "
            f"Available columns: {list(df.columns)}"
        )

    # Create a new DataFrame for the transformed data
    result = pd.DataFrame()

    # 1. NO: Generate 1-based row numbers
    result["NO"] = range(1, len(df) + 1)

    # 2. 시군구: Combine region code lookup with dong name
    result["시군구"] = df.apply(_generate_sigungu, axis=1)

    # 3. 단지명: Direct mapping
    result["단지명"] = df["aptNm"]

    # 4. 전용면적(㎡): Direct mapping (ensure numeric)
    result["전용면적(㎡)"] = pd.to_numeric(df["excluUseAr"], errors="coerce")

    # 5. 계약년월: Combine year and month as YYYYMM
    result["계약년월"] = df.apply(_generate_contract_yearmonth, axis=1)

    # 6. 계약일: Direct mapping
    result["계약일"] = df["dealDay"]

    # 7. 거래금액(만원): Remove commas and convert to integer
    result["거래금액(만원)"] = df["dealAmount"].apply(_clean_deal_amount)

    # 8. 층: Direct mapping
    result["층"] = df["floor"]

    # 9. 건축년도: Direct mapping
    result["건축년도"] = df["buildYear"]

    # 10. 해제사유발생일: Direct mapping (handle missing column)
    if "cdealDay" in df.columns:
        result["해제사유발생일"] = df["cdealDay"].fillna("")
    else:
        result["해제사유발생일"] = ""

    return result


def _generate_sigungu(row: pd.Series) -> str:
    """
    Generate the 시군구 field by combining region name lookup with dong name.

    Args:
        row: A row from the DataFrame

    Returns:
        Combined string like "서울특별시 은평구 불광동"
    """
    sgg_code = row.get("sggCd", "")
    umd_name = row.get("umdNm", "")

    # Get region name from code
    region_name = get_sigungu_name(sgg_code)

    # Combine with dong name if available
    if umd_name and pd.notna(umd_name):
        return f"{region_name} {str(umd_name).strip()}"

    return region_name


def _generate_contract_yearmonth(row: pd.Series) -> int:
    """
    Generate the 계약년월 field as YYYYMM format.

    Args:
        row: A row from the DataFrame

    Returns:
        Contract year-month as integer in YYYYMM format (e.g., 202407)
    """
    try:
        year = int(row.get("dealYear", 0))
        month = int(row.get("dealMonth", 0))
        return year * 100 + month
    except (ValueError, TypeError):
        warnings.warn(
            f"Failed to parse year/month: {row.get('dealYear')}/{row.get('dealMonth')}",
            UserWarning
        )
        return 0


def _clean_deal_amount(value) -> int:
    """
    Clean the deal amount by removing commas and converting to integer.

    Args:
        value: The deal amount value (may contain commas)

    Returns:
        Integer value representing the amount in 만원 (10,000 KRW)
    """
    if pd.isna(value):
        return 0

    try:
        # Convert to string and remove commas
        cleaned = str(value).replace(",", "").strip()
        return int(cleaned)
    except (ValueError, TypeError):
        warnings.warn(
            f"Failed to parse deal amount: {value}. Using 0.",
            UserWarning
        )
        return 0


def auto_transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Automatically detect format and transform to legacy format if necessary.

    This is a convenience function that combines format detection and
    transformation into a single call.

    Args:
        df: DataFrame loaded from an Excel file (any format)

    Returns:
        DataFrame in legacy format (either original if already legacy,
        or transformed if new API format)

    Raises:
        ValueError: If the format cannot be determined
    """
    file_format = detect_format(df)

    if file_format == "old":
        return df

    # file_format == "new"
    return transform_to_legacy(df)
