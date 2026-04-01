# --- IMPORTS ---
import arcpy
import os
import csv
import re
from datetime import datetime
from collections import defaultdict
# ==========================================================
# --- USER SETTINGS ---
# ==========================================================
RESET = True
GDB_PATH = r"C:\Users\jperlis\OneDrive - Brown University\Documents\ArcGIS\Projects\DataDesk_housing_automatedTEST1\DataDesk_housing_automatedTEST1.gdb"
# Folder containing files like: spring_room_selection_4_8_0900.csv
SNAPSHOT_FOLDER = r"C:\Users\jperlis\Downloads\Data"
SNAPSHOT_PREFIX = "spring_room_selection_"
SNAPSHOT_YEAR = 2025
LOOKUP_CSV = r"C:\Users\jperlis\Downloads\bdh_datadesk_lottery_ref_1.csv"
DORM_POLYGONS = "brown_basemap"
TIME_SERIES_FC = "Dorm_RoomAvailability_TimeSeries"
INVENTORY_TABLE = "Dorm_RoomInventory"
# ---- FULL PATHS INSIDE GDB ----
TIME_SERIES_FC_PATH = os.path.join(GDB_PATH, TIME_SERIES_FC)
INVENTORY_TABLE_PATH = os.path.join(GDB_PATH, INVENTORY_TABLE)
# ==========================================================
# --- DIMENSION SETTINGS ---
# ==========================================================
# Base genders in the raw data; we aggregate these into 4 groups
BASE_GENDERS = ("COED", "MALE", "FEMALE")
# Dropdown gender groupings
GENDER_GROUPS = ("COED", "COEDMALE", "COEDFEMALE", "ALL")
# Dropdown room-size options
SIZE_OPTIONS = ("ALL", 1, 2, 3, 4, 5)
# ==========================================================
# --- FIELD NAME HELPERS ---
# ==========================================================
def size_label(size_opt):
    return "ALL" if size_opt == "ALL" else str(int(size_opt))
def avail_field(g, s):
    return f"Avail_{g}_{size_label(s)}"
def total_field(g, s):
    return f"Total_{g}_{size_label(s)}"
def pct_field(g, s):
    return f"Pct_{g}_{size_label(s)}"
def suite_avail_field(g, s):
    return f"Avail_S_{g}_{size_label(s)}"
def suite_total_field(g, s):
    return f"Total_S_{g}_{size_label(s)}"
def suite_pct_field(g, s):
    return f"Pct_S_{g}_{size_label(s)}"
def all_slice_fields():
    fields = []
    for g in GENDER_GROUPS:
        for s in SIZE_OPTIONS:
            fields.append(avail_field(g, s))
            fields.append(total_field(g, s))
            fields.append(pct_field(g, s))
    # Suite-only fields
    for g in GENDER_GROUPS:
        for s in SIZE_OPTIONS:
            fields.append(suite_avail_field(g, s))
            fields.append(suite_total_field(g, s))
            fields.append(suite_pct_field(g, s))
    return fields
def all_total_fields():
    fields = []
    for g in GENDER_GROUPS:
        for s in SIZE_OPTIONS:
            fields.append(total_field(g, s))
    # Suite-only totals
    for g in GENDER_GROUPS:
        for s in SIZE_OPTIONS:
            fields.append(suite_total_field(g, s))
    return fields
# ==========================================================
# --- HELPER FUNCTIONS ---
# ==========================================================
def normalize_name(name):
    return (
        (name or "")
        .upper()
        .replace(".", "")
        .replace("#", "")
        .replace("-", " ")
        .replace(" ", " ")
        .strip()
    )
def load_building_lookup(csv_path):
    lookup = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lottery_name = normalize_name(row["Lottery_sheet_name"])
            building_id = int(row["Building_ID"])
            lookup[lottery_name] = building_id
    return lookup
def load_building_id_to_name(csv_path):
    """
    Returns dict: {Building_ID (int): Lottery_sheet_name (original casing from CSV)}
    """
    out = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bid = int(row["Building_ID"])
            # Use the human-readable name for display; keep as-is (or normalize if you prefer)
            out[bid] = row["Lottery_sheet_name"].strip()
    return out
def parse_snapshot_time_from_filename(filename, year):
    """
    Expected filename pattern:
        spring_room_selection_<month>_<day>_<HHMM>.csv
    Example:
        spring_room_selection_4_8_0900.csv  -> April 8, 09:00
    Returns: datetime
    """
    fn = os.path.basename(filename)
    pattern = r"^" + re.escape(SNAPSHOT_PREFIX) + r"(\d{1,2})_(\d{1,2})_(\d{4})\.csv$"
    m = re.match(pattern, fn)
    if not m:
        raise ValueError(f"Filename does not match expected pattern: {fn}")
    month = int(m.group(1))
    day = int(m.group(2))
    hhmm = m.group(3)
    hour = int(hhmm[:2])
    minute = int(hhmm[2:])
    return datetime(year, month, day, hour, minute, 0)
def get_snapshot_files_with_times(folder):
    """
    Returns list of (snapshot_time, full_path) sorted by snapshot_time.
    """
    snapshots = []
    for fn in os.listdir(folder):
        if not fn.startswith(SNAPSHOT_PREFIX) or not fn.endswith(".csv"):
            continue
        full_path = os.path.join(folder, fn)
        try:
            t = parse_snapshot_time_from_filename(fn, SNAPSHOT_YEAR)
        except ValueError:
            continue
        snapshots.append((t, full_path))
    snapshots.sort(key=lambda x: x[0])
    return snapshots
def map_base_gender(raw_gender):
    """
    Maps raw Room Gender values to base categories:
      COED includes CoEd + DynamicGender
      MALE includes Male
      FEMALE includes Female
    Returns None if not recognized.
    """
    g = (raw_gender or "").strip()
    if g in ("CoEd", "DynamicGender"):
        return "COED"
    if g == "Male":
        return "MALE"
    if g == "Female":
        return "FEMALE"
    return None
def create_inventory_table():
    """
    Inventory table stores baseline totals for each (gender_group, size_option) slice.
    """
    if not arcpy.Exists(INVENTORY_TABLE_PATH):
        arcpy.management.CreateTable(GDB_PATH, INVENTORY_TABLE)
        arcpy.management.AddField(INVENTORY_TABLE_PATH, "Building", "LONG")
    # Ensure required total fields exist
    existing = {f.name for f in arcpy.ListFields(INVENTORY_TABLE_PATH)}
    for fld in all_total_fields():
        if fld not in existing:
            arcpy.management.AddField(INVENTORY_TABLE_PATH, fld, "LONG")
def create_time_series_fc():
    """
    Time-series FC stores 84 fields for each (gender_group, size_option) slice:
      Avail_*, Total_*, Pct_*
    """
    if not arcpy.Exists(TIME_SERIES_FC_PATH):
        arcpy.management.CopyFeatures(DORM_POLYGONS, TIME_SERIES_FC_PATH)
        arcpy.management.AddField(TIME_SERIES_FC_PATH, "Snapshot_Time", "DATE")
    # Ensure required fields exist
    existing = {f.name for f in arcpy.ListFields(TIME_SERIES_FC_PATH)}
    if "Building_Name" not in existing:
        arcpy.management.AddField(TIME_SERIES_FC_PATH, "Building_Name", "TEXT", field_length=100)
        existing.add("Building_Name")
    # Keep legacy fields if you want; not required for the new system
    legacy_fields = [
        ("Rooms_Available", "LONG"),
        ("Total_Rooms", "LONG"),
        ("Percent_Available", "DOUBLE"),
    ]
    for fname, ftype in legacy_fields:
        if fname not in existing:
            arcpy.management.AddField(TIME_SERIES_FC_PATH, fname, ftype)
    for g in GENDER_GROUPS:
        for s in SIZE_OPTIONS:
            a = avail_field(g, s)
            t = total_field(g, s)
            p = pct_field(g, s)
            if a not in existing:
                arcpy.management.AddField(TIME_SERIES_FC_PATH, a, "LONG")
            if t not in existing:
                arcpy.management.AddField(TIME_SERIES_FC_PATH, t, "LONG")
            if p not in existing:
                arcpy.management.AddField(TIME_SERIES_FC_PATH, p, "DOUBLE")
    for g in GENDER_GROUPS:
        for s in SIZE_OPTIONS:
            a = suite_avail_field(g, s)
            t = suite_total_field(g, s)
            p = suite_pct_field(g, s)
            if a not in existing:
                arcpy.management.AddField(TIME_SERIES_FC_PATH, a, "LONG")
            if t not in existing:
                arcpy.management.AddField(TIME_SERIES_FC_PATH, t, "LONG")
            if p not in existing:
                arcpy.management.AddField(TIME_SERIES_FC_PATH, p, "DOUBLE")
def get_max_existing_timestamp():
    if not arcpy.Exists(TIME_SERIES_FC_PATH):
        return None
    max_time = None
    with arcpy.da.SearchCursor(TIME_SERIES_FC_PATH, ["Snapshot_Time"]) as cursor:
        for (t,) in cursor:
            if t and (max_time is None or t > max_time):
                max_time = t
    return max_time
# ==========================================================
# --- CORE AGGREGATION ---
# ==========================================================
def process_snapshot(snapshot_csv, building_lookup):
    rooms = {}        # non-suite rooms
    suite_rooms = {}  # suite rooms
    counted_suites = set()  # tracks suite IDs already initialized
    greg_a_125_counted = False
    with open(snapshot_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            profile = row.get("Room Profile")
            if profile != "25-26 Spring Selection (Room)":
                continue
            Building_Name = normalize_name(row.get("Building"))
            if Building_Name not in building_lookup:
                print("NOT MATCHED:", Building_Name)
                continue
            building_id = building_lookup[Building_Name]
            base_gender = map_base_gender(row.get("Room Gender"))
            if base_gender is None:
                continue
            room_type = (row.get("Room Type") or "").strip()
            room_str = (row.get("Room") or "")
            # --- Grad Center: non-suite singles ---
            if "GRAD CENTER" in Building_Name:
                room_id = (row.get("Room") or "").strip()
                if not room_id:
                    continue
                key = (building_id, room_id, base_gender)
                if key not in rooms:
                    rooms[key] = {"capacity": 1, "available_beds": 1}
                continue
            # --- Greg A 125: treat each room individually as non-suite ---
            if "GREG A 125" in room_str:
                room_id = (row.get("Room") or "").strip()
                if not room_id:
                    continue
                if "Triple" in room_type:
                    capacity = 3
                elif "Double" in room_type:
                    capacity = 2
                elif "Single" in room_type:
                    capacity = 1
                else:
                    continue
                key = (building_id, room_id, base_gender)
                if key not in rooms:
                    rooms[key] = {"capacity": capacity, "available_beds": 1}
                else:
                    rooms[key]["available_beds"] += 1
                continue
            # --- True suites (Suite/Apartment with valid suite size) ---
            if "Suite" in room_type:
                suite_size_raw = (row.get("Suite Size (if applicable)") or "").strip()
                suite_id = (row.get("Suite") or "").strip()
                if (not suite_id) or (suite_size_raw == "") or (suite_size_raw.upper() in ("NA", "N/A", "-", "NONE")):
                    # No valid suite size — treat as non-suite standard room
                    room_id = (row.get("Suite") or "").strip()
                    if not room_id:
                        continue
                    if "Single" in room_type:
                        capacity = 1
                    elif "Double" in room_type:
                        capacity = 2
                    elif "Triple" in room_type:
                        capacity = 3
                    elif "Quad" in room_type:
                        capacity = 4
                    else:
                        continue
                    key = (building_id, room_id, base_gender)
                    if key not in rooms:
                        rooms[key] = {"capacity": capacity, "available_beds": 1}
                    else:
                        rooms[key]["available_beds"] += 1
                    continue
                try:
                    capacity = int(float(suite_size_raw))
                except ValueError:
                    print(f"Bad suite size for {Building_Name} {row.get('Room')}: {suite_size_raw!r}")
                    continue
                key = (building_id, suite_id, base_gender)
                if key not in suite_rooms:
                    suite_rooms[key] = {"capacity": capacity, "available_beds": 1}
                else:
                    suite_rooms[key]["available_beds"] += 1
                continue
            # --- Standard non-suite rooms ---
            room_id = (row.get("Suite") or "").strip()
            if not room_id:
                continue
            if "Single" in room_type:
                capacity = 1
            elif "Double" in room_type:
                capacity = 2
            elif "Triple" in room_type:
                capacity = 3
            elif "Quad" in room_type:
                capacity = 4
            else:
                print(f"Unknown room type for {Building_Name} {room_id}: {room_type}")
                continue
            key = (building_id, room_id, base_gender)
            if key not in rooms:
                rooms[key] = {"capacity": capacity, "available_beds": 1}
            else:
                rooms[key]["available_beds"] += 1
    # Aggregate fully-available non-suite rooms
    avail_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (building_id, _room_id, base_gender), data in rooms.items():
        if data["available_beds"] == data["capacity"]:
            cap = data["capacity"]
            avail_counts[building_id][base_gender][cap] += 1
            avail_counts[building_id][base_gender]["ALL"] += 1
    # Aggregate fully-available suite rooms
    suite_avail_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (building_id, _suite_id, base_gender), data in suite_rooms.items():
        if data["available_beds"] == data["capacity"]:
            cap = data["capacity"]
            suite_avail_counts[building_id][base_gender][cap] += 1
            suite_avail_counts[building_id][base_gender]["ALL"] += 1
    # Ensure all buildings appear
    for _bname, bid in building_lookup.items():
        if bid not in avail_counts:
            _ = avail_counts[bid]
        if bid not in suite_avail_counts:
            _ = suite_avail_counts[bid]
    return avail_counts, suite_avail_counts
def totals_from_snapshot(snapshot_csv, building_lookup):
    seen = set()
    suite_seen = set()
    room_caps = {}
    suite_caps = {}
    with open(snapshot_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            profile = row.get("Room Profile")
            if profile != "25-26 Spring Selection (Room)":
                continue
            Building_Name = normalize_name(row.get("Building"))
            if Building_Name not in building_lookup:
                continue
            building_id = building_lookup[Building_Name]
            base_gender = map_base_gender(row.get("Room Gender"))
            if base_gender is None:
                continue
            room_type = (row.get("Room Type") or "").strip()
            room_str = (row.get("Room") or "")
            # Grad Center: non-suite singles
            if "GRAD CENTER" in Building_Name:
                room_id = (row.get("Room") or "").strip()
                if not room_id:
                    continue
                key = (building_id, room_id, base_gender)
                if key not in seen:
                    seen.add(key)
                    room_caps[key] = 1
                continue
            # Greg A 125: individual non-suite rooms
            if "GREG A 125" in room_str:
                room_id = (row.get("Room") or "").strip()
                if not room_id:
                    continue
                if "Triple" in room_type:
                    capacity = 3
                elif "Double" in room_type:
                    capacity = 2
                elif "Single" in room_type:
                    capacity = 1
                else:
                    continue
                key = (building_id, room_id, base_gender)
                if key not in seen:
                    seen.add(key)
                    room_caps[key] = capacity
                continue
            # True suites
            if "Suite" in room_type:
                suite_size_raw = (row.get("Suite Size (if applicable)") or "").strip()
                suite_id = (row.get("Suite") or "").strip()
                if (not suite_id) or (suite_size_raw == "") or (suite_size_raw.upper() in ("NA", "N/A", "-", "NONE")):
                    room_id = (row.get("Suite") or "").strip()
                    if not room_id:
                        continue
                    if "Single" in room_type:
                        capacity = 1
                    elif "Double" in room_type:
                        capacity = 2
                    elif "Triple" in room_type:
                        capacity = 3
                    elif "Quad" in room_type:
                        capacity = 4
                    else:
                        continue
                    key = (building_id, room_id, base_gender)
                    if key not in seen:
                        seen.add(key)
                        room_caps[key] = capacity
                    continue
                try:
                    capacity = int(float(suite_size_raw))
                except ValueError:
                    continue
                key = (building_id, suite_id, base_gender)
                if key not in suite_seen:
                    suite_seen.add(key)
                    suite_caps[key] = capacity
                continue
            # Standard rooms
            room_id = (row.get("Suite") or "").strip()
            if not room_id:
                continue
            if "Single" in room_type:
                capacity = 1
            elif "Double" in room_type:
                capacity = 2
            elif "Triple" in room_type:
                capacity = 3
            elif "Quad" in room_type:
                capacity = 4
            else:
                continue
            key = (building_id, room_id, base_gender)
            if key not in seen:
                seen.add(key)
                room_caps[key] = capacity
    total_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (building_id, _room_id, base_gender), cap in room_caps.items():
        total_counts[building_id][base_gender][cap] += 1
        total_counts[building_id][base_gender]["ALL"] += 1
    suite_total_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (building_id, _suite_id, base_gender), cap in suite_caps.items():
        suite_total_counts[building_id][base_gender][cap] += 1
        suite_total_counts[building_id][base_gender]["ALL"] += 1
    for _bname, bid in building_lookup.items():
        if bid not in total_counts:
            _ = total_counts[bid]
        if bid not in suite_total_counts:
            _ = suite_total_counts[bid]
    return total_counts, suite_total_counts
def aggregate_to_groups(counts_by_base):
    """
    Converts base counts (COED/MALE/FEMALE) into the 4 dropdown gender groups:
      COED, COEDMALE, COEDFEMALE, ALL
    Input:
      counts_by_base[building_id][base_gender][cap_or_ALL] = count
    Output:
      counts_by_group[building_id][group][cap_or_ALL] = count
    """
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for bid, by_base_gender in counts_by_base.items():
        # helper to get count safely
        def get(bg, cap):
            return by_base_gender.get(bg, {}).get(cap, 0)
        # Determine which capacity keys exist (include "ALL" plus any integers)
        cap_keys = set()
        for bg in BASE_GENDERS:
            cap_keys.update(by_base_gender.get(bg, {}).keys())
        if "ALL" not in cap_keys:
            cap_keys.add("ALL")
        for cap in cap_keys:
            coed = get("COED", cap)
            male = get("MALE", cap)
            female = get("FEMALE", cap)
            out[bid]["COED"][cap] = coed
            out[bid]["COEDMALE"][cap] = coed + male
            out[bid]["COEDFEMALE"][cap] = coed + female
            out[bid]["ALL"][cap] = coed + male + female
    return out
def slice_value(counts_by_group, bid, group, size_opt):
    """
    Returns the count for a (group, size_opt) slice.
    size_opt can be "ALL" or an int capacity.
    For size_opt="ALL", uses the precomputed "ALL" cap bucket.
    For numeric size_opt, uses that exact capacity bucket.
    """
    if size_opt == "ALL":
        return counts_by_group.get(bid, {}).get(group, {}).get("ALL", 0)
    return counts_by_group.get(bid, {}).get(group, {}).get(int(size_opt), 0)
# ==========================================================
# --- MAIN WORKFLOW ---
# ==========================================================
def main():
    # --- ARCPY SETUP ---
    arcpy.env.workspace = GDB_PATH
    arcpy.ClearWorkspaceCache_management()
    # --- RESET OUTPUTS IF REQUESTED ---
    if RESET:
        if arcpy.Exists(TIME_SERIES_FC_PATH):
            arcpy.management.Delete(TIME_SERIES_FC_PATH)
            print("Deleted old time-series feature class")
        if arcpy.Exists(INVENTORY_TABLE_PATH):
            arcpy.management.Delete(INVENTORY_TABLE_PATH)
            print("Deleted old inventory table")
    # --- DISCOVER SNAPSHOTS ---
    snapshots = get_snapshot_files_with_times(SNAPSHOT_FOLDER)
    if len(snapshots) == 0:
        raise FileNotFoundError(
            f"No snapshot CSVs found in {SNAPSHOT_FOLDER} matching {SNAPSHOT_PREFIX}<m>_<d>_<HHMM>.csv"
        )
    # --- LOAD LOOKUP ---
    building_lookup = load_building_lookup(LOOKUP_CSV)
    building_id_to_name = load_building_id_to_name(LOOKUP_CSV)
    # --- CREATE OUTPUTS IF NEEDED ---
    create_inventory_table()
    create_time_series_fc()
    # --- LOAD INVENTORY TOTALS (28 total fields) ---
    total_fields = all_total_fields()
    inv_fields = ["Building"] + total_fields
    totals_by_building = {}  # bid -> {Total_*: value}
    with arcpy.da.SearchCursor(INVENTORY_TABLE_PATH, inv_fields) as cursor:
        for row in cursor:
            bid = row[0]
            totals_by_building[bid] = {}
            for i, fld in enumerate(total_fields, start=1):
                totals_by_building[bid][fld] = row[i] if row[i] is not None else 0
    # --- INIT INVENTORY TOTALS ON FIRST RUN ---
    if not totals_by_building:
        baseline_time, baseline_csv = snapshots[0]
        base_totals, base_suite_totals = process_snapshot(baseline_csv, building_lookup)
        group_totals = aggregate_to_groups(base_totals)
        group_suite_totals = aggregate_to_groups(base_suite_totals)
        with arcpy.da.InsertCursor(INVENTORY_TABLE_PATH, inv_fields) as icur:
            for _bname, bid in building_lookup.items():
                row_vals = [bid]
                totals_by_building[bid] = {}
                for g in GENDER_GROUPS:
                    for s in SIZE_OPTIONS:
                        tot = slice_value(group_totals, bid, g, s)
                        fld = total_field(g, s)
                        totals_by_building[bid][fld] = tot
                        row_vals.append(tot)
                # Suite totals
                for g in GENDER_GROUPS:
                    for s in SIZE_OPTIONS:
                        tot = slice_value(group_suite_totals, bid, g, s)
                        fld = suite_total_field(g, s)
                        totals_by_building[bid][fld] = tot
                        row_vals.append(tot)
                icur.insertRow(row_vals)
        print(f"Inventory initialized from {os.path.basename(baseline_csv)} ({baseline_time})")
    # --- SKIP ALREADY-INGESTED SNAPSHOTS (IF NOT RESET) ---
    max_existing = get_max_existing_timestamp()
    # --- INSERT FIELDS FOR TIME SERIES ---
    # Include geometry + Building + Snapshot_Time, then 84 slice fields.
    slice_fields = all_slice_fields()
    insert_fields = [
        "SHAPE@",
        "Building",
        "Building_Name",
        "Snapshot_Time",
        # legacy fields (optional)
        "Rooms_Available",
        "Total_Rooms",
        "Percent_Available",
    ] + slice_fields
    # --- APPEND TIME SERIES FOR EACH SNAPSHOT ---
    print(f"Snapshots found: {len(snapshots)}")
    print(f"Max existing timestamp: {max_existing}")
    for snapshot_time, snapshot_csv in snapshots:
        print(f"Considering: {snapshot_time} - {os.path.basename(snapshot_csv)}")
        if max_existing is not None and snapshot_time <= max_existing:
            continue
        base_avail, suite_avail = process_snapshot(snapshot_csv, building_lookup)
        group_avail = aggregate_to_groups(base_avail)
        group_suite_avail = aggregate_to_groups(suite_avail)
        with arcpy.da.InsertCursor(TIME_SERIES_FC_PATH, insert_fields) as icursor:
            with arcpy.da.SearchCursor(DORM_POLYGONS, ["SHAPE@", "Building"]) as dorms:
                for shape, bid in dorms:
    		    # Normalize polygon Building IDs to match inventory keys (prevents “skip everything”)
                    try:
                        bid = int(bid)
                    except Exception:
                        continue
    		    # If we don't have totals for this building, skip
                    if bid not in totals_by_building:
                        continue
                    # Legacy "ALL / ALL" convenience
                    legacy_avail = slice_value(group_avail, bid, "ALL", "ALL")
                    legacy_total = totals_by_building[bid].get(total_field("ALL", "ALL"), 0)
                    legacy_pct = (legacy_avail / legacy_total * 100.0) if legacy_total > 0 else None
                    bname = building_id_to_name.get(bid, None)
                    row_out = [
                        shape,
                        bid,
                        bname,
                        snapshot_time,
                        legacy_avail,
                        legacy_total,
                        legacy_pct,
                    ]
                    # Fill 84 slice fields
                    # Combined fields (existing)
                    for g in GENDER_GROUPS:
                        for s in SIZE_OPTIONS:
                            a_non = slice_value(group_avail, bid, g, s)
                            a_sui = slice_value(group_suite_avail, bid, g, s)
                            a = a_non + a_sui
                            t_non = totals_by_building[bid].get(total_field(g, s), 0)
                            t_sui = totals_by_building[bid].get(suite_total_field(g, s), 0)
                            t = t_non + t_sui
                            if t > 0:
                                p = min((a / t) * 100.0, 100.0)
                                a_out = a
                            else:
                                p = None
                                a_out = None
                            row_out.append(a_out)
                            row_out.append(t)
                            row_out.append(p)
                    # Suite-only fields (new)
                    for g in GENDER_GROUPS:
                        for s in SIZE_OPTIONS:
                            a = slice_value(group_suite_avail, bid, g, s)
                            t_fld = suite_total_field(g, s)
                            t = totals_by_building[bid].get(t_fld, 0)
                            if t > 0:
                                p = min((a / t) * 100.0, 100.0)
                                a_out = a
                            else:
                                p = None
                                a_out = None
                            row_out.append(a_out)
                            row_out.append(t)
                            row_out.append(p)
                    icursor.insertRow(row_out)
        print(f"Snapshot appended for {snapshot_time} from {os.path.basename(snapshot_csv)}")
# ==========================================================
# --- RUN ---
# ==========================================================
main()
