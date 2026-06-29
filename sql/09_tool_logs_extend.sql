-- VinoSage 2.0: the tool_call_logs.tool_name CHECK in 01_schema.sql lists exactly
-- the original 5 tools. Inserting a log row for a new tool would violate it and
-- (because logging swallows exceptions) silently drop the log. Widen the CHECK.
-- Per project convention we never edit an applied file — this ALTER lives here.
alter table tool_call_logs drop constraint if exists tool_call_logs_tool_name_check;
alter table tool_call_logs add constraint tool_call_logs_tool_name_check
  check (tool_name in (
    'filter_wines','pair_with_food','calculate_budget','compare_wines','wine_stats',
    'explain_wine_concept','recommend_for_me'
  ));
