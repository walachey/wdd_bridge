import datetime
import numpy as np
import pandas
import pytz


class ExperimentalControl:

    def __init__(self, config, print_fn, log_fn):
        
        self.print_fn = print_fn
        self.log_fn = log_fn
        
        self.tolerance_deg = config["tolerance_deg"]
        self.tolerance_rad = self.tolerance_deg / 180.0 * np.pi

        timetable = []
        for slot_info in config["timeslots"]:
            angle_deg = np.nan
            if "angle_deg" in slot_info:
                angle_deg = slot_info["angle_deg"]
            timestamp_from = datetime.datetime.fromisoformat(slot_info["from"])
            timestamp_to = datetime.datetime.fromisoformat(slot_info["to"])
            timetable.append(dict(
                angle_rad=angle_deg / 180.0 * np.pi,
                ts_from=timestamp_from.astimezone(pytz.UTC),
                ts_to=timestamp_to.astimezone(pytz.UTC),
                rule=slot_info["rule"]
            ))

        self.timetable = pandas.DataFrame(timetable)
        valid_angles = ~pandas.isnull(self.timetable.angle_rad.values)
        self.timetable.angle_rad[valid_angles] = (self.timetable.angle_rad[valid_angles].values + 2.0 * np.pi) % (2.0 * np.pi)

        today = datetime.datetime.now().astimezone(pytz.UTC).date()
        today_start = pytz.UTC.localize(datetime.datetime.combine(today, datetime.time(0)))
        today_end = today_start + datetime.timedelta(days=1)
        today_rules = self.timetable[(
            (self.timetable.ts_from >= today_start) & (self.timetable.ts_from < today_end)
            | (self.timetable.ts_to >= today_start) & (self.timetable.ts_to < today_end)
            | (self.timetable.ts_from < today_start) & (self.timetable.ts_to >= today_end))]
        self.print_fn("Loaded {} experiment rules ({} valid today).".format(self.timetable.shape[0], today_rules.shape[0]))

    def filter_message(self, message, world_angle):

        now = datetime.datetime.now().astimezone(pytz.UTC)
        world_angle = (world_angle + 2.0 * np.pi) % (2.0 * np.pi)

        current_ruleset = self.timetable[(self.timetable.ts_from <= now) & (self.timetable.ts_to >= now)]
        if current_ruleset.empty:
            self.print_fn("No rule set for current time.")
            return message

        # Any rule for this specific angle?
        concrete_indices = ~pandas.isnull(current_ruleset.angle_rad)
        concrete_rules = current_ruleset[concrete_indices]
        diff0 = np.abs(concrete_rules.angle_rad.values - world_angle)
        diff1 = (2.0 * np.pi) - diff0
        matches = (diff0 < self.tolerance_rad) | (diff1 < self.tolerance_rad)
        concrete_rules = concrete_rules[matches]

        def handle_action_set(action_set):
            action_set = set(action_set)
            should_allow_message = "vibrate" in action_set
            should_prevent_message = "no_vibrate" in action_set
            if should_allow_message and should_prevent_message:
                self.print_fn("Warning: Two concrete, opposing rules for this world angle.")
            if should_prevent_message:
                self.log_fn("prevented vibration")
                return True, None
            elif should_allow_message:
                self.log_fn("allowed vibration")
                return True, message
            return False, message

        if not concrete_rules.empty:
            
            handled, message = handle_action_set(concrete_rules.rule.values)
            if handled:
                return message

        # Any general rules?
        general_rules = current_ruleset[~concrete_indices]
        if not general_rules.empty:
            handled, message = handle_action_set(general_rules.rule.values)
            if handled:
                return message

        self.print_fn("Warning: No rule handled current experiment.")
        return None


