#!/bin/sh
# Custom CrashMin oracle. Exit 0 iff the response is still the failure.
# See docs/oracles.md.
test "$CRASHMIN_STATUS" = 500 || exit 1
grep -q 'panic: nil pointer' "$CRASHMIN_BODY_FILE"
