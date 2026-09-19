#!/usr/bin/env bash
# Run a build step and, if it fails, repeat its output as a GitHub annotation.
#
# GitHub's REST API serves a run's annotations to anyone who can read the
# repository, but job *logs* need a token this project does not hand out. So a
# failing step's output is invisible to everything except a browser, and the
# first thing anyone does with a red build is go and read it. This puts the
# tail of the output where the API can reach it.
#
#     tools/ci_run.sh "Lay out the board" make layout
#
# The output still goes to the log as well: the annotation is a copy, not a
# replacement, and it is the tail because an annotation has a size limit.
set -uo pipefail

title=$1
shift

log=$(mktemp)
"$@" > "$log" 2>&1
status=$?
cat "$log"

if [ "$status" -ne 0 ]; then
    # %0A is how a workflow command carries a newline; without it the
    # annotation is one line and the traceback is unreadable.
    body=$(tail -c 3000 "$log" | sed -e 's/%/%25/g' -e 's/\r/%0D/g' | awk '{printf "%s%%0A", $0}')
    echo "::error title=${title} (exit ${status})::${body}"
fi

rm -f "$log"
exit "$status"
