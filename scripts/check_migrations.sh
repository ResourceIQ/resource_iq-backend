#!/bin/bash
# check_migrations.sh

echo "Checking for multiple Alembic heads..."

# Get the number of lines returned by 'alembic heads'
# We strip whitespace and count the lines
HEADS_COUNT=$(alembic heads | wc -l)

if [ "$HEADS_COUNT" -gt 1 ]; then
    echo "ERROR: Multiple Alembic heads detected!"
    alembic heads
    echo "Please run 'alembic merge' locally to fix the branch in your migrations."
    exit 1
fi

echo "Success: Only one Alembic head found."
exit 0
