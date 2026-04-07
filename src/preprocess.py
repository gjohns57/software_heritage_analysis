"""
Phase 4: Merge visit + language data, clean, and engineer features.

Merges visit_data.csv and language_data.csv, filters to projects with
both language and snapshot data, computes lifecycle features, and
classifies projects as active/inactive/abandoned.

Usage:
    python src/preprocess.py

Output:
    data/analysis_dataset.csv — clean, analysis-ready dataset
"""

import pandas as pd
import numpy as np
from datetime import datetime

VISIT_FILE = "data/visit_data.csv"
LANGUAGE_FILE = "data/language_data.csv"
OUTPUT_FILE = "data/analysis_dataset.csv"

# Language metadata: year introduced, category flags
LANGUAGE_INFO = {
    "Assembly":         {"year": 1949, "generation": 1, "compiled": True,  "memory_safe": False, "garbage_collected": False, "paradigm": "imperative"},
    "Fortran":          {"year": 1957, "generation": 1, "compiled": True,  "memory_safe": False, "garbage_collected": False, "paradigm": "imperative"},
    "C":                {"year": 1972, "generation": 1, "compiled": True,  "memory_safe": False, "garbage_collected": False, "paradigm": "imperative"},
    "C++":              {"year": 1985, "generation": 2, "compiled": True,  "memory_safe": False, "garbage_collected": False, "paradigm": "multi"},
    "Objective-C":      {"year": 1984, "generation": 2, "compiled": True,  "memory_safe": False, "garbage_collected": False, "paradigm": "oop"},
    "Perl":             {"year": 1987, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Python":           {"year": 1991, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Ruby":             {"year": 1995, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Java":             {"year": 1995, "generation": 2, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "oop"},
    "JavaScript":       {"year": 1995, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "PHP":              {"year": 1995, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "R":                {"year": 1993, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Lua":              {"year": 1993, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Haskell":          {"year": 1990, "generation": 2, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "functional"},
    "HTML":             {"year": 1993, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": False, "paradigm": "markup"},
    "CSS":              {"year": 1996, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": False, "paradigm": "markup"},
    "Shell":            {"year": 1989, "generation": 2, "compiled": False, "memory_safe": True,  "garbage_collected": False, "paradigm": "scripting"},
    "C#":               {"year": 2000, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Scala":            {"year": 2004, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Groovy":           {"year": 2003, "generation": 3, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Clojure":          {"year": 2007, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "functional"},
    "Go":               {"year": 2009, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Rust":             {"year": 2010, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": False, "paradigm": "multi"},
    "Kotlin":           {"year": 2011, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "TypeScript":       {"year": 2012, "generation": 3, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Swift":            {"year": 2014, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": False, "paradigm": "multi"},
    "Dart":             {"year": 2011, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "oop"},
    "Elixir":           {"year": 2011, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "functional"},
    "Julia":            {"year": 2012, "generation": 3, "compiled": True,  "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Vue":              {"year": 2014, "generation": 3, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "Jupyter Notebook": {"year": 2014, "generation": 3, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "multi"},
    "PowerShell":       {"year": 2006, "generation": 3, "compiled": False, "memory_safe": True,  "garbage_collected": True,  "paradigm": "scripting"},
}

GENERATION_LABELS = {1: "1st gen (pre-1980)", 2: "2nd gen (1980s-1990s)", 3: "3rd gen (2000s+)"}


def main():
    print("Loading data...")
    visits = pd.read_csv(VISIT_FILE)
    languages = pd.read_csv(LANGUAGE_FILE)

    print(f"  Visit data: {len(visits):,} records")
    print(f"  Language data: {len(languages):,} records")

    # --- Merge ---
    merged = pd.merge(visits, languages, on="url", how="inner")
    print(f"  Merged: {len(merged):,} records")

    # --- Filter to usable projects ---
    # Must have: detected language + at least 1 snapshot
    clean = merged[
        (merged["primary_language"].notna()) &
        (merged["num_snapshots"] > 0)
    ].copy()
    print(f"  After filtering (language + snapshots): {len(clean):,} records")

    # Remove markup/config-only projects (HTML, CSS) — optional, keep for now but flag them
    code_languages = set(LANGUAGE_INFO.keys()) - {"HTML", "CSS"}

    # --- Parse dates ---
    clean["first_visit_date"] = pd.to_datetime(clean["first_visit_date"], format="ISO8601", utc=True)
    clean["last_visit_date"] = pd.to_datetime(clean["last_visit_date"], format="ISO8601", utc=True)

    # --- Compute lifespan ---
    clean["lifespan_days"] = (clean["last_visit_date"] - clean["first_visit_date"]).dt.days
    clean["lifespan_months"] = clean["lifespan_days"] / 30.44  # avg days per month
    clean["lifespan_years"] = clean["lifespan_days"] / 365.25

    # --- Classify project status ---
    now = pd.Timestamp.now(tz="UTC")
    clean["days_since_last_visit"] = (now - clean["last_visit_date"]).dt.days

    def classify_status(days_since):
        if days_since <= 365:
            return "active"
        elif days_since <= 730:
            return "inactive"
        else:
            return "abandoned"

    clean["project_status"] = clean["days_since_last_visit"].apply(classify_status)

    # --- For survival analysis: event indicator ---
    # "event" = project became abandoned (1) vs still alive/right-censored (0)
    clean["is_abandoned"] = (clean["project_status"] == "abandoned").astype(int)

    # Observation time = lifespan in days (for survival analysis)
    # For active/inactive projects, this is right-censored
    clean["observation_time_days"] = clean["lifespan_days"].clip(lower=1)  # minimum 1 day

    # --- Activity density ---
    clean["visits_per_year"] = clean["num_visits"] / clean["lifespan_years"].clip(lower=0.01)

    # --- Add language metadata ---
    clean["language_year"] = clean["primary_language"].map(
        lambda x: LANGUAGE_INFO.get(x, {}).get("year"))
    clean["language_generation"] = clean["primary_language"].map(
        lambda x: LANGUAGE_INFO.get(x, {}).get("generation"))
    clean["generation_label"] = clean["language_generation"].map(GENERATION_LABELS)
    clean["is_compiled"] = clean["primary_language"].map(
        lambda x: LANGUAGE_INFO.get(x, {}).get("compiled"))
    clean["is_memory_safe"] = clean["primary_language"].map(
        lambda x: LANGUAGE_INFO.get(x, {}).get("memory_safe"))
    clean["is_garbage_collected"] = clean["primary_language"].map(
        lambda x: LANGUAGE_INFO.get(x, {}).get("garbage_collected"))
    clean["paradigm"] = clean["primary_language"].map(
        lambda x: LANGUAGE_INFO.get(x, {}).get("paradigm"))
    clean["is_code_language"] = clean["primary_language"].isin(code_languages)

    # --- Select and order columns for output ---
    output_cols = [
        "url", "repo_full_name", "primary_language", "primary_language_ratio",
        "language_year", "language_generation", "generation_label",
        "is_compiled", "is_memory_safe", "is_garbage_collected", "paradigm",
        "is_code_language",
        "first_visit_date", "last_visit_date",
        "lifespan_days", "lifespan_months", "lifespan_years",
        "days_since_last_visit", "project_status", "is_abandoned",
        "observation_time_days",
        "num_visits", "num_snapshots", "visits_per_year",
        "has_full_visit", "github_languages",
    ]
    output = clean[output_cols]

    # --- Save ---
    output.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(output):,} records to {OUTPUT_FILE}")

    # --- Summary statistics ---
    print("\n" + "=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)

    print(f"\nTotal clean projects: {len(output):,}")
    print(f"\nProject status:")
    print(output["project_status"].value_counts().to_string())

    print(f"\nTop 15 languages:")
    print(output["primary_language"].value_counts().head(15).to_string())

    print(f"\nGeneration breakdown:")
    print(output["generation_label"].value_counts().to_string())

    print(f"\nLifespan statistics (days):")
    print(output["lifespan_days"].describe().to_string())

    print(f"\nAbandonment rate by generation:")
    gen_abandon = output.groupby("generation_label")["is_abandoned"].mean()
    print((gen_abandon * 100).round(1).to_string())

    code_only = output[output["is_code_language"]]
    print(f"\nCode-only projects (excluding HTML/CSS): {len(code_only):,}")


if __name__ == "__main__":
    main()
