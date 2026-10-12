#!/bin/bash
# limits.sh — machine-wide Claude Code quota snapshot for the orchestrator skill.
#
#   limits.sh claude   exact Claude Code windows via `claude -p "/usage"` (burn-rate fallback)
#   limits.sh burn     transcript burn-rate only
#   limits.sh parked   live entries of the shared park-file
#   limits.sh all      claude + parked, as one JSON object (default)
#
# `claude -p "/usage"` prints the real server-side windows as text (session 5h, weekly
# all-models, weekly current-model). The client makes the authenticated call itself — a
# plain curl to claude.ai/api/oauth/usage is Cloudflare-blocked. It spins a short-lived
# claude process (~15-20s), so call it once per cycle, not per dispatch. On any failure
# it falls back to the transcript burn-rate (consumption, not remaining).
set -euo pipefail

claude_usage() {
  # Exact Claude windows from the headless /usage command; jq parses the three lines.
  # Top-line percentages are the real server-side windows; the "what's contributing"
  # breakdown printed underneath is local-machine-only and deliberately ignored.
  local raw
  raw=$(claude -p "/usage" </dev/null 2>/dev/null) || {
    claude_burn
    return
  }
  [[ -z "$raw" ]] && {
    claude_burn
    return
  }
  printf '%s\n' "$raw" | jq -R -s '
    def pick(rx): [split("\n")[] | select(test(rx))][0] // "";
    def pct(s): (s | capture("(?<p>[0-9]+)% used") | .p | tonumber) // null;
    def rst(s): (s | capture("resets (?<r>.*)$") | .r) // null;
    (pick("Current session:")) as $s |
    (pick("Current week \\(all models\\)")) as $w |
    ([split("\n")[] | select(test("Current week \\(") and (test("all models") | not))][0] // "") as $m |
    {source: "claude -p /usage", exact: true,
     session_5h: {used_percent: pct($s), resets: rst($s)},
     weekly:     {used_percent: pct($w), resets: rst($w)},
     weekly_current_model: (if $m == "" then null else
        {model: ($m | capture("Current week \\((?<n>[^)]+)\\)") | .n),
         used_percent: pct($m), resets: rst($m)} end)}
  ' 2>/dev/null || {
    claude_burn
    return
  }
}

claude_burn() {
  # FALLBACK only (used when `claude -p "/usage"` is unavailable or unparseable).
  # Tokens summed from transcript entries in the last 5h / 1h across all projects.
  # File mtime pre-filters; jq walks each line for message.usage. Input+output only:
  # cache reads dominate raw counts but weigh least against the plan window.
  local since_5h since_1h
  since_5h=$(date -u -v-5H +%Y-%m-%dT%H:%M 2>/dev/null || date -u -d '5 hours ago' +%Y-%m-%dT%H:%M)
  since_1h=$(date -u -v-1H +%Y-%m-%dT%H:%M 2>/dev/null || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M)
  find "$HOME/.claude/projects" -name '*.jsonl' -mmin -300 2>/dev/null | head -60 | while read -r f; do
    jq -r 'select(.timestamp? and .message?.usage?) |
           [.timestamp[0:16], (.message.usage.input_tokens // 0), (.message.usage.output_tokens // 0)] | @tsv' "$f" 2>/dev/null
  done | awk -F'\t' -v h5="$since_5h" -v h1="$since_1h" '
    $1 >= h5 { in5+=$2; out5+=$3; n5++ }
    $1 >= h1 { in1+=$2; out1+=$3; n1++ }
    END { printf "{\"source\":\"transcript burn-rate (fallback)\",\"exact\":false,\"five_hour_burn\":{\"input_tokens\":%d,\"output_tokens\":%d,\"messages\":%d},\"one_hour_burn\":{\"input_tokens\":%d,\"output_tokens\":%d,\"messages\":%d}}\n", in5, out5, n5, in1, out1, n1 }'
}

parked_lanes() {
  # Shared park-file: presidents write observed limit-hits here so other projects'
  # presidents see a parked lane without probing. Expired entries are dropped (and
  # pruned back to the file so it self-cleans).
  local f="$HOME/.claude/orchestrator/parked-lanes.json"
  [[ -f "$f" ]] || {
    echo '{}'
    return
  }
  local live
  live=$(jq -c 'with_entries(select(.value.until | sub("\\.[0-9]+Z$"; "Z") | fromdate > now))' "$f" 2>/dev/null) || {
    echo '{}'
    return
  }
  printf '%s' "$live" >"$f"
  echo "$live"
}

case "${1:-all}" in
claude) claude_usage ;;
burn) claude_burn ;;
parked) parked_lanes ;;
all) jq -n --argjson claude "$(claude_usage)" --argjson parked "$(parked_lanes)" \
  '{claude_code: $claude, parked: $parked, note: "claude_code from `claude -p /usage`; claude_code.exact=false means the /usage read failed and it fell back to burn-rate; parked = lanes other presidents observed limit-hit"}' ;;
*)
  echo "usage: limits.sh [claude|burn|parked|all]" >&2
  exit 2
  ;;
esac
