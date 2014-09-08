#!/bin/bash
${1?"Usage: $0 VERSION"}
version=$1
echo "Building vdebug version $version"
echo
echo " -> Running tests"
if python vdebugtests.py
then
    echo " -> OK."
    echo " -> Creating tar from working directory..."
    if tar -cvzf vdebug-$version.tar.gz doc/Vdebug.txt plugin syntax tests HISTORY LICENCE README.md requirements.txt vdebugtests.py VERSION
    then
        echo " -> OK, created tar at vdebug-$version.tar.gz."
    else
        echo " -> ERROR: failed to build tar, exiting"
        exit 1
    fi
else
    echo " -> ERROR: tests failed, exiting"
    exit 1
fi
