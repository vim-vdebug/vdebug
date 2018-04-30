#!/bin/bash
version=`cat VERSION`
echo "Building vdebug version $version"
tar -cvzf vdebug-$version.tar.gz doc plugin pythonx syntax CHANGELOG LICENCE README.md VERSION
