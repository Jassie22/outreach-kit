#!/usr/bin/env bash
# UserPromptSubmit hook: nudge Claude Code to load the cold-outreach skill
# whenever a prompt looks like recruiter or hiring outreach.
#
# A hook cannot force a skill to load, it can only inject a reminder into the
# turn. That turns out to be enough in practice: the failure mode without one
# is drafting from memory of a skill read earlier in the session, which quietly
# drops the rules you added most recently.
#
# Install: copy to ~/scripts/, chmod +x, then in ~/.claude/settings.json:
#
#   "hooks": {
#     "UserPromptSubmit": [
#       { "hooks": [ { "type": "command",
#                      "command": "$HOME/scripts/outreach-skill-reminder.sh" } ] }
#     ]
#   }

prompt="$(cat)"

if ! grep -qiE 'recruiter|outreach|cold email|cold-email|hiring manager|talent (partner|team)|follow.?up|chase|founder email|reach out|job (search|hunt)|applicant' <<<"$prompt"; then
  exit 0
fi

cat <<'REMINDER'
<system-reminder>
This prompt looks like recruiter / hiring outreach.

Before writing ANY message, invoke the `cold-outreach` skill and follow it.
Do not draft from memory: it carries hard limits that are easy to get wrong.

- 90-150 words per email
- first sentence must carry a recipient-specific trigger
- exactly one ask, as a question, on the final line
- no years of experience, no location as a constraint, no "available immediately"
- zero em dashes
- every claim traceable to your applicant reference file

Create drafts; never send without explicit per-message approval.
</system-reminder>
REMINDER
