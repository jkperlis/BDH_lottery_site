# --- IMPORTS ---
import os
import csv
import re
import json
from datetime import datetime
from collections import defaultdict

# --- SETTINGS ---
SNAPSHOT_FOLDER = "/Users/jkperlis/Brown/Datadesk/Lottery Data"
SNAPSHOT_PREFIX = "spring_room_selection_"
SNAPSHOT_YEAR = 2025

# --- DIMENSION SETTINGS ---
BASE_GENDERS = ("COED", "MALE", "FEMALE")
GENDER_GROUPS = ("COED", "COEDMALE", "COEDFEMALE", "ALL")
SIZE_OPTIONS = ("ALL", 1, 2, 3, 4, 5, 9)

# --- HELPERS ---
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


def normalize_name(name):
    return (
        (name or "")
        .upper()
        .replace(".", "")
        .replace("#", "")
        .replace("-", " ")
        .replace("  ", " ")
        .strip()
    )


def parse_snapshot_time_from_filename(filename, year):
    """
    Expected filename pattern:
        spring_housing_selection_<month>_<day>_<HHMM>.csv
    Example:
        spring_housing_selection_04_08_0900.csv
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
    """
    g = (raw_gender or "").strip()
    if g in ("CoEd", "DynamicGender"):
        return "COED"
    if g == "Male":
        return "MALE"
    if g == "Female":
        return "FEMALE"
    return None


def get_lookup(snapshots):
    """
    Builds building lookup from snapshot files.
    """
    buildings = set()

    for _, snapshot_csv in snapshots:
        with open(snapshot_csv, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                profile = row.get("Room Profile")
                if profile != "25-26 Spring Selection (Room)":
                    continue

                building = normalize_name(row.get("Building"))
                if building:
                    buildings.add(building)

    building_lookup = {}
    building_id_to_name = {}

    for i, building in enumerate(sorted(buildings), start=1):
        building_lookup[building] = i
        building_id_to_name[i] = building.title()

    return building_lookup, building_id_to_name


# --- CORE AGGREGATION ---
def process_snapshot(snapshot_csv, building_lookup):
    """
    Computes AVAILABLE fully-available room/suite counts.

    Returns:
      avail_counts[building_id][base_gender][capacity]
      suite_avail_counts[building_id][base_gender][capacity]
    """
    rooms = {}        # non-suite rooms
    suite_rooms = {}  # true suites

    with open(snapshot_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            profile = row.get("Room Profile")
            if profile != "25-26 Spring Selection (Room)":
                continue

            building_name = normalize_name(row.get("Building"))
            if building_name not in building_lookup:
                print("NOT MATCHED:", building_name)
                continue

            building_id = building_lookup[building_name]
            base_gender = map_base_gender(row.get("Room Gender"))
            if base_gender is None:
                continue

            room_type = (row.get("Room Type") or "").strip()
            room_str = (row.get("Room") or "")

            # --- Grad Center: non-suite singles ---
            if "GRAD CENTER" in building_name:
                room_id = (row.get("Room") or "").strip()
                if not room_id:
                    continue

                key = (building_id, room_id, base_gender)
                if key not in rooms:
                    rooms[key] = {"capacity": 1, "available_beds": 1}
                continue

            # --- Greg A 125: treat as one suite-like 9-person unit ---
            if "GREG A 125" in room_str:
                key = (building_id, "GREG A 125", base_gender)
                if key not in suite_rooms:
                    suite_rooms[key] = {"capacity": 9, "available_beds": 9}
                continue

            # --- True suites ---
            if "Suite" in room_type:
                suite_size_raw = (row.get("Suite Size (if applicable)") or "").strip()
                suite_id = (row.get("Suite") or "").strip()

                # If missing valid suite info, fall back to standard room handling
                if (not suite_id) or (suite_size_raw == "") or (suite_size_raw.upper() in ("NA", "N/A", "-", "NONE")):
                    room_id = (row.get("Suite") or "").strip() or (row.get("Room") or "").strip()
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
                    print(f"Bad suite size for {building_name} {row.get('Room')}: {suite_size_raw!r}")
                    continue

                key = (building_id, suite_id, base_gender)
                if key not in suite_rooms:
                    suite_rooms[key] = {"capacity": capacity, "available_beds": 1}
                else:
                    suite_rooms[key]["available_beds"] += 1
                continue

            # --- Standard non-suite rooms ---
            room_id = (row.get("Suite") or "").strip() or (row.get("Room") or "").strip()
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
                print(f"Unknown room type for {building_name} {room_id}: {room_type}")
                continue

            key = (building_id, room_id, base_gender)
            if key not in rooms:
                rooms[key] = {"capacity": capacity, "available_beds": 1}
            else:
                rooms[key]["available_beds"] += 1

    avail_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (building_id, _room_id, base_gender), data in rooms.items():
        if data["available_beds"] == data["capacity"]:
            cap = data["capacity"]
            avail_counts[building_id][base_gender][cap] += 1
            avail_counts[building_id][base_gender]["ALL"] += 1

    suite_avail_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (building_id, _suite_id, base_gender), data in suite_rooms.items():
        if data["available_beds"] == data["capacity"]:
            cap = data["capacity"]
            suite_avail_counts[building_id][base_gender][cap] += 1
            suite_avail_counts[building_id][base_gender]["ALL"] += 1

    for _bname, bid in building_lookup.items():
        if bid not in avail_counts:
            _ = avail_counts[bid]
        if bid not in suite_avail_counts:
            _ = suite_avail_counts[bid]

    return avail_counts, suite_avail_counts


def totals_from_snapshot(snapshot_csv, building_lookup):
    """
    Computes TOTAL unique room/suite counts from a baseline snapshot.

    Returns:
      total_counts[building_id][base_gender][capacity]
      suite_total_counts[building_id][base_gender][capacity]
    """
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

            building_name = normalize_name(row.get("Building"))
            if building_name not in building_lookup:
                continue

            building_id = building_lookup[building_name]
            base_gender = map_base_gender(row.get("Room Gender"))
            if base_gender is None:
                continue

            room_type = (row.get("Room Type") or "").strip()
            room_str = (row.get("Room") or "")

            # --- Grad Center: non-suite singles ---
            if "GRAD CENTER" in building_name:
                room_id = (row.get("Room") or "").strip()
                if not room_id:
                    continue

                key = (building_id, room_id, base_gender)
                if key not in seen:
                    seen.add(key)
                    room_caps[key] = 1
                continue

            # --- Greg A 125 ---
            if "GREG A 125" in room_str:
                key = (building_id, "GREG A 125", base_gender)
                if key not in suite_seen:
                    suite_seen.add(key)
                    suite_caps[key] = 9
                continue

            # --- True suites ---
            if "Suite" in room_type:
                suite_size_raw = (row.get("Suite Size (if applicable)") or "").strip()
                suite_id = (row.get("Suite") or "").strip()

                if (not suite_id) or (suite_size_raw == "") or (suite_size_raw.upper() in ("NA", "N/A", "-", "NONE")):
                    room_id = (row.get("Suite") or "").strip() or (row.get("Room") or "").strip()
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

            # --- Standard rooms ---
            room_id = (row.get("Suite") or "").strip() or (row.get("Room") or "").strip()
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
    Converts base counts (COED/MALE/FEMALE) into dropdown gender groups.
    """
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for bid, by_base_gender in counts_by_base.items():
        def get(bg, cap):
            return by_base_gender.get(bg, {}).get(cap, 0)

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
    """
    if size_opt == "ALL":
        return counts_by_group.get(bid, {}).get(group, {}).get("ALL", 0)
    return counts_by_group.get(bid, {}).get(group, {}).get(int(size_opt), 0)


# --- JSON BUILD ---
def build_building_entry(
    bid,
    group_avail,
    group_totals,
    group_suite_avail,
    group_suite_totals,
):
    entry = {}

    for g in GENDER_GROUPS:
        for s in SIZE_OPTIONS:
            # Combined: non-suite + suite
            a_non = slice_value(group_avail, bid, g, s)
            a_sui = slice_value(group_suite_avail, bid, g, s)
            a = a_non + a_sui

            t_non = slice_value(group_totals, bid, g, s)
            t_sui = slice_value(group_suite_totals, bid, g, s)
            t = t_non + t_sui

            p = round((a / t) * 100.0, 1) if t > 0 else None

            entry[avail_field(g, s)] = a if t > 0 else None
            entry[total_field(g, s)] = t
            entry[pct_field(g, s)] = p

    for g in GENDER_GROUPS:
        for s in SIZE_OPTIONS:
            a = slice_value(group_suite_avail, bid, g, s)
            t = slice_value(group_suite_totals, bid, g, s)
            p = round((a / t) * 100.0, 1) if t > 0 else None

            entry[suite_avail_field(g, s)] = a if t > 0 else None
            entry[suite_total_field(g, s)] = t
            entry[suite_pct_field(g, s)] = p

    return entry


# --- MAIN ---
def main():
    snapshots = get_snapshot_files_with_times(SNAPSHOT_FOLDER)
    if not snapshots:
        raise FileNotFoundError(
            f"No snapshot CSVs found in {SNAPSHOT_FOLDER} matching {SNAPSHOT_PREFIX}<m>_<d>_<HHMM>.csv"
        )

    building_lookup, building_id_to_name = get_lookup(snapshots)

    # Baseline totals from first snapshot
    baseline_time, baseline_csv = snapshots[0]
    base_totals, base_suite_totals = process_snapshot(baseline_csv, building_lookup)
    group_totals = aggregate_to_groups(base_totals)
    group_suite_totals = aggregate_to_groups(base_suite_totals)

    output_data = {}

    for snapshot_time, snapshot_csv in snapshots:
        base_avail, base_suite_avail = process_snapshot(snapshot_csv, building_lookup)
        group_avail = aggregate_to_groups(base_avail)
        group_suite_avail = aggregate_to_groups(base_suite_avail)

        current_time = snapshot_time.isoformat()
        output_data[current_time] = {}

        for bid in building_lookup.values():
            building_name = building_id_to_name.get(bid)
            if not building_name:
                continue

            building_entry = build_building_entry(
                bid=bid,
                group_avail=group_avail,
                group_totals=group_totals,
                group_suite_avail=group_suite_avail,
                group_suite_totals=group_suite_totals,
            )

            output_data[current_time][building_name] = building_entry

    with open("housing_output.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print("JSON export complete.")


# --- RUN ---
if __name__ == "__main__":
    main()