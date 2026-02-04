#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Excel file structure analysis script"""
import pandas as pd
import sys

def analyze_excel(file_path):
    print(f"Analyzing: {file_path}")
    print("=" * 80)

    try:
        xl = pd.ExcelFile(file_path)
        print(f"\n=== Sheet List ===")
        print(xl.sheet_names)

        for sheet in xl.sheet_names:
            print(f"\n{'='*80}")
            print(f"=== Sheet: {sheet} ===")
            print("="*80)

            # Read without header first to see raw structure
            df_raw = pd.read_excel(file_path, sheet_name=sheet, header=None)
            print(f"\nRows: {len(df_raw)}, Columns: {len(df_raw.columns)}")

            print("\n--- First 25 rows (raw) ---")
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', None)
            pd.set_option('display.max_colwidth', 30)
            print(df_raw.head(25).to_string())

            print("\n--- Column names at different header positions ---")
            for header_row in range(5):
                try:
                    df_test = pd.read_excel(file_path, sheet_name=sheet, header=header_row)
                    print(f"\nHeader at row {header_row}: {list(df_test.columns)}")
                except:
                    pass

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    file_path = r"D:\ai_program\실거래가분석대시보드\서대문구 아파트(매매)_실거래가_20260108121130.xlsx"
    analyze_excel(file_path)
